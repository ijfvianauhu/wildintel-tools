import csv
import hashlib
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import shutil
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from queue import Queue, Empty
from typing import List, Callable

from wildintel_tools.helpers import (
        get_trapper_locations
    )

import yaml
from PIL import Image

from wildintel_tools.reports import Report
from wildintel_tools.resouceutils import ResourceExtensionDTO, ResourceUtils
from natsort import natsorted

def _read_field_notes_log(filepath: Path) -> List[dict]:
    """
    Read and parse the field notes log file.

    :param filepath: Path to the field notes log file.
    :type filepath: Path
    :return: A list of dictionaries with the parsed log data.
    :rtype: List[dict]
    """

    deployments = []

    with open(filepath, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            deployment_name = row.get("Deployment")
            start_date = row.get("StartDate")
            start_time = row.get("StartTime")
            end_date = row.get("EndDate")
            end_time = row.get("EndTime")

            if deployment_name and start_date and end_date:
                expected_start = datetime.strptime(f"{start_date} {start_time}", "%Y:%m:%d %H:%M:%S")
                expected_end = datetime.strptime(f"{end_date} {end_time}", "%Y:%m:%d %H:%M:%S")
                deployments.append({
                    "name": deployment_name,
                    "expected_start": expected_start,
                    "expected_end": expected_end
                })

    return deployments

def _pil_to_bytes(pil_image: Image.Image, format: str = "JPEG") -> bytes:
    """
    Convert a PIL image to raw bytes.

    :param pil_image: The PIL Image object to convert.
    :type pil_image: Image.Image
    :param format: The output image format (e.g. "JPEG", "PNG").
                   Defaults to "JPEG".
    :type format: str
    :return: The image encoded as bytes.
    :rtype: bytes
    """
    buffer = BytesIO()
    pil_image.save(buffer, format=format)
    buffer.seek(0)
    return buffer.getvalue()

def check_collections(
    data_path: Path,
    url:str,
    user:str,
    password:str,
    collections: List[str] = [],
    validate_locations: bool = True,
    max_workers: int = 4,
    progress_callback: Callable[[str], None] = None,

) -> Report:
    """
    Check the collection names and their associated deployments.  For each deployment, verify that the linked location
    exists.

    :param data_path: Path to the local data directory containing the collections.
    :type data_path: Path
    :param url: Base URL of the remote Trapper instance.
    :type url: str
    :param user: Username for authentication.
    :type user: str
    :param password: Password for authentication.
    :type password: str
    :param collections: List of collection names to check. If empty, all available
                        collections will be checked.
    :type collections: List[str]
    param validate_locations: If set to true, it will check that the locations are created in Trapper.
    :type validate_locations: bool
    :param progress_callback: Optional callable used to report progress messages
                              during the process.
    :type progress_callback: Callable[[str], None], optional
    :return: A report object containing the results of the collection checks.
    :rtype: Report
    """
    report = Report("Validate collection and deployments names")

    locs = get_trapper_locations(url, user, password, None)
    locs_id = {cp.model_dump()["locationID"] for cp in locs.results}

    if not collections:
        collections = [entry.name for entry in data_path.iterdir() if entry.is_dir()]
    else:
        collections = [entry.name for entry in data_path.iterdir() if entry.is_dir() and entry.name in collections]

    # Helper function to check a single deployment
    def check_deployment(col: str, deployment: Path, queue: Queue):
        results = []
        if not any(deployment.iterdir()):
            return results

        if not re.fullmatch(r"^R[0-9]{4}-([0-9A-Za-z_-]+)(_.+)?$", deployment.name):
            results.append(("error", deployment.name, "validate_deployment_names",
                            "Name format is incorrect. It should follow the <CODE>-<NAME>_<SUFFIX> format."))
        elif deployment.name.split("-")[0] != str(col):
            results.append(("error", deployment.name, "validate_deployment_names",
                            f"The deployment name must not include the collection name. It must include {str(col)}"))
        elif validate_locations and deployment.name.split("-")[1].lower() not in locs_id:
            invalid_loc_name = deployment.name.split("-")[1].lower()
            results.append(("error", deployment.name, "validate_deployment_names",
                            f"The deployment name must include a valid location id, not '{invalid_loc_name}'."))
        else:
            results.append(("success", deployment.name, "validate_deployment_names", "Deployment name is valid."))

        # Check that collection prefix matches folder name
        collection_name, _ = deployment.name.split("-", 1)
        if collection_name != col:
            results.append(("error", deployment.name, "validate_deployment_names",
                            f"Deployment '{deployment.name}' collection prefix ({collection_name}) does not match"
                            f" collection folder name '{col}'."))
        queue.put(("progress", col, deployment.name))
        return results

    for col in collections:
        col_path = data_path / col
        deployments = [d for d in col_path.iterdir() if d.is_dir()]

        if progress_callback:
            progress_callback(f"collection_start:{col}", len(deployments))

        if not re.fullmatch(r"^R[0-9]{4}(_.+)?$", str(col)):
            report.add_error(str(col), "validate_collection_names",
                             f"Collection name '{str(col)}' does not follow the RNNNN format.")
        else:
            report.add_success(str(col), "validate_collection_names")

        # Check deployments in parallel
        completed = 0
        total = len(deployments)
        q = Queue()


        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(check_deployment, col, d, q): d for d in deployments}

            def progress_listener():
                nonlocal completed
                while completed < total:
                    try:
                        msg_type, ccol, dep_name = q.get(timeout=0.1)
                        if msg_type == "progress":
                            completed += 1
                            if progress_callback:
                                progress_callback(f"collection_progress:{ccol}", completed / total)
                    except Empty:
                        continue

            listener = threading.Thread(target=progress_listener, daemon=True)
            listener.start()

            for future in as_completed(futures):
                results = future.result()
                for status, name, section, msg in results:
                    if status == "error":
                        report.add_error(name, section, msg)
                    else:
                        report.add_success(name, section)
                listener.join(timeout=1)

        if progress_callback:
            progress_callback(f"collection_end:{col}", len(deployments))

        """for deployment in deployments:
            if not any(deployment.iterdir()):
                continue

            if not re.fullmatch(r"^R[0-9]{4}-([0-9A-Za-z_-]+)(_.+)?$", deployment.name):
                report.add_error(deployment.name, "validate_deployment_names",
                         "Name format is incorrect. It should follow the <CODE>-<NAME>_<SUFFIX> format.")
            elif deployment.name.split("-")[0] != str(col):
                report.add_error(deployment.name,
                         "validate_deployment_names",
                         f"The deployment name must not include the collection name. It must include {str(col)}")
            elif validate_locations and deployment.name.split("-")[1].lower() not in locs_id:
                invalid_loc_name = deployment.name.split("-")[1].lower()
                report.add_error(deployment.name, "validate_deployment_names",
                         f"The deployment name must not include a valid location id, not {invalid_loc_name}.")
            else:
                report.add_success(deployment.name, "validate_deployment_names")

            collection_name, location = deployment.name.split("-",1)

            if collection_name != col:
                report.add_error(deployment.name, "validate_deployment_names",
                         f"Deployment '{deployment.name}' collection prefix ({collection_name}) does not match"
                                 f" collection folder name '{col}'.")
        """
    report.finish()
    return report

def check_deployments(
        data_path: Path,
        collections: List[str] = None,
        extensions: List[ResourceExtensionDTO] = None,
        progress_callback: Callable[[str], None] = None,
        tolerance_hours: int = 1,
) -> Report:
    """
    Check the integrity of each deployment. The checks include verifying the chronological sequence of images and
    ensuring that all images were captured within a predefined date range. A tolerance window is allowed between the
    first and last photo in each deployment.

    :param data_path: Path to the local data directory containing the deployments.
    :type data_path: Path
    :param collections: List of collection names to include in the check. If None,
                        all collections will be processed.
    :type collections: List[str], optional
    :param extensions: Optional list of resource extensions used for additional
                       validation or metadata enrichment.
    :type extensions: List[ResourceExtensionDTO], optional
    :param progress_callback: Optional callable used to report progress messages
                              during the process.
    :type progress_callback: Callable[[str], None], optional
    :param tolerance_hours: Number of hours of tolerance allowed between the first
                            and last image of a deployment.
    :type tolerance_hours: int, optional
    :return: A report object containing the results of the deployment integrity checks.
    :rtype: Report
    """

    report = Report("Validating deployments")

    if not collections:
        collections = [entry.name for entry in data_path.iterdir() if entry.is_dir()]
    else:
        collections = [entry.name for entry in data_path.iterdir() if entry.is_dir() and entry.name in collections]

    if extensions is None:
        extensions = list(ResourceExtensionDTO)

    valid_exts = [ext.value.lower() for ext in extensions]

    for col in collections:
        col_path = data_path / col

        log_file = col_path / f"{col}_FileTimestampLog.csv"

        if not log_file.exists():
            report.add_error(str(col), "check filetimestamplog",
                             f"No FileTimestampLog {col}_FileTimestampLog.csv found in {col_path}")

        deployments = _read_field_notes_log(log_file)

        if progress_callback:
            progress_callback(f"collection_start:{col}", len(deployments))

        for deployment in deployments:

            deployment_path = col_path / deployment["name"]

            if not deployment_path.exists():
                report.add_error(str(col), "missing deployment", f"Deployment folder '{deployment["name"]
                }' not found in {col_path}")

                if progress_callback:
                    progress_callback(f"deployment_start:{col}:{deployment["name"]}:0",
                                     0)
                    progress_callback(f"deployment_complete:{col}:{deployment["name"]}", 1)

                continue

            validated_file = deployment_path / ".validated"
            if validated_file.exists():
                # TODO validar el sha1 del .validated ??
                if progress_callback:
                    progress_callback(f"deployment_complete:{col}:{deployment["name"]}", 1)

                continue

            all_files = [p for p in deployment_path.rglob("*") if p.is_file()]
            image_files = [f for f in all_files if f.suffix.lower() in valid_exts]
            image_files = natsorted(image_files)

            sha1 = hashlib.sha1()
            previous_date = None
            date_list = []
            error = False

            if progress_callback:
                progress_callback(f"deployment_start:{col}:{deployment["name"]}:{len(image_files)}", {len(image_files)})

            for idx, img_path in enumerate(image_files, start=1):
                try:
                    if progress_callback:
                        progress_callback(f"file_progress:{col}:{deployment["name"]}", 1)

                    date_taken = None
                    img_bytes = img_path.read_bytes()
                    exif = ResourceUtils.get_exif_from_bytes(img_bytes)

                    date_str = exif.get("DateTimeOriginal") or exif.get("DateTime")
                    if date_str:
                        try:
                            date_taken = datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
                        except ValueError:
                            date_taken = None

                    if previous_date and date_taken and date_taken < previous_date:
                        error = True
                        report.add_error(
                            img_path,
                            "date order",
                            f"Image '{img_path.name}' (order {idx}) has earlier date "
                                    f"than previous image {str(image_files[idx - 1])}."
                        )
                        continue

                    img_hash, _ = ResourceUtils.calculate_hash(img_bytes)
                    sha1.update(img_hash.encode())

                    if date_taken:
                        previous_date = date_taken
                        date_list.append(date_taken)

                except Exception as e:
                    report.add_error(str(img_path), "gather_metadata", f"Failed to process image: {e}")
                    continue

            # Validar primera y última imagen respecto al rango esperado
            if deployment["expected_start"] and deployment["expected_end"] and date_list:
                tolerance = timedelta(hours=tolerance_hours)
                first_date = date_list[0]
                last_date = date_list[-1]

                if first_date < deployment["expected_start"] - tolerance or first_date > deployment[
                    "expected_start"] + tolerance:
                    error = True
                    report.add_error(
                        deployment["name"],
                        "deployment start date",
                        f"First image '{image_files[0].name}' date {first_date} is outside expected start " 
                                f"{deployment["expected_start"]} ±{tolerance_hours}h"
                    )

                if last_date < deployment["expected_end"] - tolerance or last_date > deployment[
                    "expected_end"] + tolerance:
                    error = True
                    report.add_error(
                        deployment["name"],
                        "deployment end date",
                        f"Last image '{image_files[-1].name}' date {last_date} is outside expected "
                                f" end {deployment["expected_end"]} ±{tolerance_hours}h"
                    )
            if not error:
                try:
                    combined_hash = sha1.hexdigest()

                    # Creamos el contenido del archivo de validación
                    validation_info = {
                        "validated_at": datetime.now().isoformat(),
                        "collection": col,
                        "deployment": deployment["name"],
                        "hash": combined_hash,
                    }

                    # Guardamos el fichero oculto `.validated` en el deployment
                    validation_file = deployment_path / ".validated"
                    with open(validation_file, "w", encoding="utf-8") as f:
                        yaml.dump(validation_info, f, indent=2)

                    report.add_success(
                        deployment["name"],
                        "deployment validated",
                        f"Deployment '{deployment['name']}' validated successfully at "
                                f"{validation_info['validated_at']}"
                    )

                except Exception as e:
                    report.add_error(
                        deployment["name"],
                        "validation record error",
                        f"Failed to create .validated file for deployment {deployment['name']}: {e}"
                    )
            if progress_callback:
                progress_callback(f"deployment_complete:{col}:{deployment["name"]}", 1)

    report.finish()
    return report

def prepare_collections_for_trapper(
    data_path: Path,
    output_dir: Path,
    collections: list[str] = None,
    deployments: list[str] = None,
    extensions: list[ResourceExtensionDTO] = None,
    progress_callback: Callable[[str], None] = None,
    max_workers: int = 4,
    xmp_info : dict = None
) -> Report:
    """
    Prepare validated collections for upload them to Trapper. Each deployment's images are copied and flattened
    in parallel, with XMP metadata added. Progress callbacks are invoked for collections, deployments, and individual
    files.

    :param data_path: Root directory containing the collections.
    :type data_path: Path
    :param output_dir: Destination directory for the flattened collections.
    :type output_dir: Path
    :param collections: List of collection names to process. If not provided,
                        all collections will be included.
    :type collections: list[str], optional
    :param deployments: Specific deployments to process. If not provided,
                        all deployments will be included.
    :type deployments: list[str], optional
    :param extensions: File extensions or resource types to include.
    :type extensions: list[ResourceExtensionDTO], optional
    :param progress_callback: Optional callable used to report progress events
                              for collections, deployments, and individual files.
    :type progress_callback: Callable, optional
    :param max_workers: Number of threads to use for parallel processing.
                        Defaults to 4.
    :type max_workers: int, optional
    :param xmp_info: XMP metadata information to be added to each image
    :type xmp_info: dict
    :return: A report summarizing the processed collections and deployments.
    :rtype: Report
    """
    report = Report("Preparing collections for Trapper")

    if not data_path.is_dir():
        raise FileNotFoundError(f"Data path not found: {data_path}")

    if not collections:
        collections = [c.name for c in data_path.iterdir() if c.is_dir()]
    else:
        collections = [c.name for c in data_path.iterdir() if c.is_dir() and c.name in collections]

    if extensions is None:
        extensions = list(ResourceExtensionDTO)
    valid_extensions = [ext.value.lower() for ext in extensions]

    def process_file(col_name, dep_name, idx, img_path, trapper_deployment_path):
        """
        Copy image, generate new name, add metadata, and return success/error info.
        """
        try:
            sha1_hash, _ = ResourceUtils.calculate_hash(img_path.read_bytes())
            date_taken = None
            mime = ResourceUtils.get_mime_type(img_path.read_bytes())
            exif = ResourceUtils.get_exif_from_bytes(img_path.read_bytes())

            date_str = exif.get("DateTimeOriginal") or exif.get("DateTime")
            if date_str:
                try:
                    date_taken = datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
                except Exception:
                    pass

            # Placeholder info
            make = exif.get("Make", "Unknown")
            model = exif.get("Model", "Unknown")
            rp_name =  xmp_info.get("rp_name", "Unknown")
            coverage =   xmp_info.get("coverage", "")
            publisher =   xmp_info.get("publisher", "Unknown")
            owner =   xmp_info.get("owner", "Unknown")
            year = datetime.now().year

            _, new_image = ResourceUtils.resize(Image.open(BytesIO(img_path.read_bytes())))
            new_hash, _ = ResourceUtils.calculate_hash(_pil_to_bytes(new_image))

            tags = {
                "XMP-dc:Creator": f"CT ({make} {model} {rp_name})",
                "XMP-dc:Date": date_taken.isoformat() if date_taken else "",
                "XMP-dc:Format": mime,
                "XMP-dc:Identifier": f"WildINTEL:{new_hash}",
                "XMP-dc:Source": f"WildINTEL:{sha1_hash}",
                "XMP-dc:Publisher": publisher,
                "XMP-dc:Rights": f"© {owner}, {year}. All rights reserved.",
                "XMP-dc:Coverage": f"This image was taken at {coverage}, as part of the WildINTEL project."
                                   " https://wildintel.eu/",
                "XMP-xmpRights:Marked": "true",
                "XMP-xmpRights:Owner": owner,
                "XMP-xmpRights:WebStatement": "https://creativecommons.org/licenses/by-nc/4.0/",
            }

            date_str_for_name = date_taken.strftime("%Y%m%d") if date_taken else "unknown_date"
            new_name = f"{col_name}-{dep_name}__{date_str_for_name}_{idx:04d}{img_path.suffix.lower()}"
            dest_path = trapper_deployment_path / new_name
            shutil.copy2(img_path, dest_path)
            ResourceUtils.add_xmp_metadata([dest_path], tags)

            return True, None
        except Exception as e:
            return False, f"{img_path}: {e}"

    for col in collections:
        col_path = data_path / col
        trapper_col_path = output_dir / col
        trapper_col_path.mkdir(exist_ok=True)

        if not deployments:
            all_deployments = [d for d in col_path.iterdir() if d.is_dir()]
        else:
            all_deployments = [d for d in col_path.iterdir() if d.is_dir() and d.name in deployments]

        if progress_callback:
            progress_callback(f"collection_start:{col}", len(all_deployments))

        for deployment in all_deployments:
            dep_name = deployment.name
            trapper_deployment_path = trapper_col_path / dep_name
            trapper_deployment_path.mkdir(exist_ok=True)

            image_files = [f for f in deployment.rglob("*") if f.suffix.lower() in valid_extensions]
            image_files = natsorted(image_files)

            if progress_callback:
                progress_callback(f"deployment_start:{col}:{dep_name}:{len(image_files)}", len(image_files))

            copied_count = 0
            futures = []
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                for idx, img_path in enumerate(image_files, start=1):
                    futures.append(executor.submit(process_file, col, dep_name, idx, img_path, trapper_deployment_path))

                for future in as_completed(futures):
                    success, error_msg = future.result()
                    if success:
                        copied_count += 1
                    else:
                        report.add_error(dep_name, "copy error", error_msg)
                    if progress_callback:
                        progress_callback(f"file_progress:{col}:{dep_name}", 1)

            if copied_count:
                report.add_success(dep_name, "deployment exported")

            if progress_callback:
                progress_callback(f"deployment_complete:{col}:{dep_name}", 1)

    report.finish()
    return report