import csv
import hashlib
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
import shutil
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
import logging
from typing import List, Callable, Dict
from zoneinfo import ZoneInfo

from wildintel_tools.helpers import (
        get_trapper_locations
    )

from PIL import Image
logger = logging.getLogger(__name__)


METADATA_EXIF_TAGS = [
    "DateTimeOriginal",
    "CreateDate",
    "FileModifyDate",
    "MIMEType",
    "ImageWidth",
    "ImageHeight",
    "ModifyDate",
    "Duration",
    "VideoFrameRate",
    "Make",
    "Model",
]


from wildintel_tools.reports import Report
from wildintel_tools.resouceutils import ResourceExtensionDTO, ResourceUtils
from natsort import natsorted

# same as django.utils.text.slugify
def slugify(value: str, allow_unicode: bool = False):
    """
    Convert to ASCII if 'allow_unicode' is False. Convert spaces or repeated
    dashes to single dashes. Remove characters that aren't alphanumerics,
    underscores, or hyphens. Convert to lowercase. Also strip leading and
    trailing whitespace, dashes, and underscores.
    """
    value = str(value)
    if allow_unicode:
        value = unicodedata.normalize("NFKC", value)
    else:
        value = (
            unicodedata.normalize("NFKD", value)
            .encode("ascii", "ignore")
            .decode("ascii")
        )
    value = re.sub(r"[^\w\s-]", "", value.lower())
    return re.sub(r"[-\s]+", "-", value).strip("-_")


def _read_field_notes_log(filepath: Path) -> List[Dict]:
    """
    Read and validate the field notes log file.

    Validates that all required columns exist (and are not duplicated),
    and that each deployment has valid and consistent start/end timestamps.

    :param filepath: Path to the field notes log file.
    :type filepath: Path
    :return: A list of dictionaries with validated and parsed deployment data.
    :rtype: List[dict]
    :raises ValueError: If required columns are missing, duplicated, or data is invalid.
    """

    required_fields = {"Deployment", "StartDate", "StartTime", "EndDate", "EndTime"}
    deployments = []

    with open(filepath, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        # --- 1. Validate header ---
        if reader.fieldnames is None:
            raise ValueError(f"No header row found in {filepath.name}")

        header_fields = reader.fieldnames
        duplicates = {x for x in header_fields if header_fields.count(x) > 1}
        if duplicates:
            raise ValueError(
                f"Duplicated column names in {filepath.name}: {', '.join(duplicates)}"
            )

        header_set = set(header_fields)
        missing = required_fields - header_set
        if missing:
            raise ValueError(
                f"Missing required columns in {filepath.name}: {', '.join(missing)}"
            )

        seen_names = set()

        # --- 2. Parse and validate rows ---
        for row_num, row in enumerate(reader, start=2):  # start=2 = header line
            deployment_name = row.get("Deployment", "").strip()
            start_date = row.get("StartDate", "").strip()
            start_time = row.get("StartTime", "").strip()
            end_date = row.get("EndDate", "").strip()
            end_time = row.get("EndTime", "").strip()

            # --- 3. Check missing values ---
            if not all([deployment_name, start_date, start_time, end_date, end_time]):
                raise ValueError(
                    f"Row {row_num} in {filepath.name} is missing required values: {row}"
                )

            # --- 4. Check duplicate deployment names ---
            if deployment_name in seen_names:
                raise ValueError(
                    f"Duplicate deployment name '{deployment_name}' found in {filepath.name} (line {row_num})"
                )
            seen_names.add(deployment_name)

            # --- 5. Parse datetime fields ---
            try:
                expected_start = datetime.strptime(
                    f"{start_date} {start_time}", "%Y:%m:%d %H:%M:%S"
                )
                expected_end = datetime.strptime(
                    f"{end_date} {end_time}", "%Y:%m:%d %H:%M:%S"
                )
            except ValueError as e:
                raise ValueError(
                    f"Invalid datetime format in row {row_num} ({deployment_name}): {e}"
                )

            # --- 6. Logical consistency ---
            if expected_start >= expected_end:
                raise ValueError(
                    f"Deployment '{deployment_name}' has start >= end "
                    f"({expected_start} vs {expected_end})"
                )

            deployments.append({
                "name": deployment_name,
                "expected_start": expected_start,
                "expected_end": expected_end,
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
    progress_callback: Callable[[str,int], None] = None,

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
    :type progress_callback: Callable[[str,int], None], optional
    :return: A report object containing the results of the collection checks.
    :rtype: Report
    """
    report = Report("Validate collection and deployments names")

    locs = get_trapper_locations(url, user, password, None)
    locs_id = {cp.model_dump()["location_id"] for cp in locs.results}

    if not collections:
        collections = [entry.name for entry in data_path.iterdir() if entry.is_dir()]
    else:
        collections = [entry.name for entry in data_path.iterdir() if entry.is_dir() and entry.name in collections]

    # Helper function to check a single deployment
    def check_deployment(col: str, deployment: Path):
        results = []

        if progress_callback:
            progress_callback(f"deployment_start:{col}:{deployment.name}", 1)

        if not any(deployment.iterdir()):
            return results

        if not re.fullmatch(r"^[Rr][0-9]{4}-([0-9A-Za-z_-]+)(_.+)?$", deployment.name):
            results.append(("error", f"{col}:{deployment.name}", "validate_deployment_names",
                            "Name format is incorrect. It should follow the <CODE>-<NAME>_<SUFFIX> format."))
        elif deployment.name.split("-")[0].lower() != str(col).lower():
            results.append(("error", f"{col}:{deployment.name}", "validate_deployment_names",
                            f"The deployment name must not include the collection name. It must include {str(col)}"))
        elif validate_locations and deployment.name.split("-")[1].lower() not in locs_id:
            invalid_loc_name = deployment.name.split("-")[1].lower()
            results.append(("error", f"{col}:{deployment.name}", "validate_deployment_names",
                            f"The deployment name must include a valid location id, not '{invalid_loc_name}'."))
        else:
            results.append(("success", f"{col}:{deployment.name}", "validate_deployment_names", "Deployment name is valid."))

        # Check that collection prefix matches folder name
        collection_name, _ = deployment.name.split("-", 1)
        if collection_name.lower() != col.lower():
            results.append(("error", deployment.name, "validate_deployment_names",
                            f"Deployment '{deployment.name}' collection prefix ({collection_name}) does not match"
                            f" collection folder name '{col}'."))

        if progress_callback:
            progress_callback(f"file_progress:{col}:{deployment.name}:xxx", 1)

        if progress_callback:
            progress_callback(f"deployment_complete:{col}:{deployment.name}", 1)

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

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(check_deployment, col, d): d for d in deployments}

            for future in as_completed(futures):
                results = future.result()
                for status, name, section, msg in results:
                    if status == "error":
                        report.add_error(name, section, msg)
                    else:
                        report.add_success(name, section)

    report.finish()
    return report

def check_deployments(
        data_path: Path,
        collections: List[str] = None,
        deployments: List[str] = None,
        extensions: List[ResourceExtensionDTO] = None,
        progress_callback: Callable[[str,int], None] = None,
        tolerance_hours: int = 1,
        max_workers:int =4
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
    :type progress_callback: Callable[[str,int], None], optional
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
            if progress_callback:
                progress_callback(f"collection_start:{col}", 0)

            report.add_error(str(col), "check filetimestamplog",
                             f"No FileTimestampLog {col}_FileTimestampLog.csv found in {col_path}")
            continue

        deployments_csv = _read_field_notes_log(log_file)

        if deployments:
            deployments_csv = [d for d in deployments_csv if d["name"] in deployments]

        if progress_callback:
            progress_callback(f"collection_start:{col}", len(deployments_csv))

        for deployment in deployments_csv:

            expected_start = deployment.get("expected_start")
            expected_end = deployment.get("expected_end")

            # check deployment dates
            if not expected_start or not expected_end or expected_start >= expected_end:
                report.add_error(f"{str(col)}:{deployment["name"]}", "invalid date", f"Expected start date {expected_start} and/or expected end date {expected_end} are invalid")
                progress_callback(f"deployment_start:{col}:{deployment["name"]}", 0)
                progress_callback(f"deployment_complete:{col}:{deployment["name"]}", 1)
                continue

            # check deployment folder exists
            deployment_path = col_path / deployment["name"]

            if not deployment_path.exists():
                report.add_error(f"{str(col)}:{deployment["name"]}", "missing deployment",
                                 f"Deployment folder '{deployment_path}' not found")

                if progress_callback:
                    progress_callback(f"deployment_start:{col}:{deployment["name"]}",0)
                    progress_callback(f"deployment_complete:{col}:{deployment["name"]}", 1)
                continue

            all_files = [p for p in deployment_path.rglob("*") if p.is_file()]
            image_files = [f for f in all_files if f.suffix.lower() in valid_exts]
            image_files = natsorted(image_files)

            if progress_callback:
                progress_callback(f"deployment_start:{col}:{deployment["name"]}", len(image_files))

            sha1 = hashlib.sha1()
            date_list = []
            error = False

            def process_image(img_path, idx):
                try:
                    img_bytes = img_path.read_bytes()
                    exif = ResourceUtils.get_exif_from_bytes(img_bytes)
                    date_str = exif.get("DateTimeOriginal") or exif.get("DateTime")
                    date_taken = datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S") if date_str else None
                    img_hash, _ = ResourceUtils.calculate_hash(img_bytes)
                    return idx, date_taken, img_hash, None
                except Exception as e:
                    return idx, None, None, str(e)

            results = []

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_img = {
                    executor.submit(process_image, img_path, idx): (idx, img_path)
                    for idx, img_path in enumerate(image_files, start=1)
                }
                for future in as_completed(future_to_img):
                    idx, img_path = future_to_img[future]
                    if progress_callback:
                        progress_callback(f"file_progress:{col}:{deployment['name']}:{img_path}", 1)
                    try:
                        result = future.result()
                        results.append(result)
                    except Exception as e:
                        report.add_error(str(img_path), "thread_error", str(e))

            # Ordenamos los resultados por índice para mantener la secuencia original
            results.sort(key=lambda x: x[0])

            tolerance = timedelta(hours=tolerance_hours)
            previous_date = None
            sha1 = hashlib.sha1()
            error = False

            for idx, (date_taken, img_hash, err) in enumerate(
                        [(r[1], r[2], r[3]) for r in results], start=1):
                img_path = image_files[idx - 1]

                img_id = f"{col}:{deployment['name']}:{img_path.name}"

                # check metadata
                if err:
                    report.add_error(img_id, "gather_metadata", f"Failed to process image: {err}")
                    error = True
                    continue

                # check chronological order
                if previous_date and date_taken and date_taken < previous_date:
                    report.add_error(
                        img_id,
                        "date order",
                        f"Image '{img_path.name}' (order {idx}) has earlier date than previous image."
                    )
                    error = True
                #else:
                #    report.add_success(
                #        img_id,
                #        "date order",
                #        f"Image '{img_path.name}' (order {idx}) chronological order OK."
                #    )

                previous_date = date_taken

                # check datetime range
                if date_taken:
                    if idx == 1:  # Primera imagen
                        in_range = expected_start - tolerance <= date_taken <= expected_start + tolerance
                        context = f"expected start {expected_start} ±{tolerance_hours}h"
                    elif idx == len(results):  # Última imagen
                        in_range = expected_end - tolerance <= date_taken <= expected_end + tolerance
                        context = f"expected end {expected_end} ±{tolerance_hours}h"
                    else:  # Intermedias
                        in_range = expected_start - tolerance <= date_taken <= expected_end + tolerance
                        context = f"({expected_start} - {expected_end})"

                    if not in_range:
                        error = True
                        report.add_error(
                            img_id,
                            "image date out of range",
                            f"Image '{img_path.name}' date {date_taken} is outside allowed range {context}"
                        )
                    #else:
                    #    report.add_success(
                    #        img_id,
                    #        "image date in range",
                    #        f"Image '{img_path.name}' date {date_taken} is within allowed range {context}"
                    #    )
                    #    sha1.update(img_hash.encode())
            if not error:
                report.add_success(f"{col}:{deployment["name"]}", "deployment validated",
                                   f"Deployment '{deployment['name']}' validated successfully.")

            if progress_callback:
                progress_callback(f"deployment_complete:{col}:{deployment['name']}", 1)

    report.finish()
    return report

def prepare_collections_for_trapper(
    data_path: Path,
    output_dir: Path,
    collections: list[str] = None,
    deployments: list[str] = None,
    extensions: list[ResourceExtensionDTO] = None,
    progress_callback: Callable[[str,int], None] = None,
    max_workers: int = 4,
    xmp_info : dict = None,
    scale_images: bool = True,
    overwrite: bool = False,
    create_deployment_table: bool = True,
    timezone: ZoneInfo = ZoneInfo("UTC"),
    ignore_dst=True,
    convert_to_utc= True

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

    :param scale_images: Whether to scale images to a maximum size.
    :type scale_images: bool, optional

    :param overwrite: Whether to overwrite existing deployment directories
                        in the output directory.
    :type overwrite: bool, optional

    :return: A report summarizing the processed collections and deployments.
    :rtype: Report
    """

    if not data_path.is_dir():
        raise FileNotFoundError(f"Data path not found: {data_path}")

    if not collections:
        collections = [c.name for c in data_path.iterdir() if c.is_dir()]
    else:
        collections = [c.name for c in data_path.iterdir() if c.is_dir() and c.name in collections]

    if extensions is None:
        extensions = list(ResourceExtensionDTO)
    valid_extensions = [ext.value.lower() for ext in extensions]

    def process_file(col_name, dep_name, idx, img_path, trapper_deployment_path, scale_image):
        """
        Copy image, generate new name, add metadata, and return success/error info.
        """
        try:
            sha1_hash, _ = ResourceUtils.calculate_hash(img_path.read_bytes())
            mime = ResourceUtils.get_mime_type(img_path.read_bytes())
            exif = ResourceUtils.get_exif_from_path(img_path, tags=METADATA_EXIF_TAGS)

            date_taken : datetime = ResourceUtils.parse_date_recorded(exif,timezone=timezone, fallback= True,
                                                                     ignore_dst=ignore_dst, convert_to_utc= convert_to_utc)

            if not date_taken:
                raise Exception(f"No valid date found in EXIF metadata {exif}")

            # Placeholder info
            camera = ResourceUtils.get_camera_model(exif)
            rp_name =  xmp_info.get("rp_name", "Unknown")
            coverage =   xmp_info.get("coverage", "")
            publisher =   xmp_info.get("publisher", "Unknown")
            owner =   xmp_info.get("owner", "Unknown")
            year = datetime.now().year

            if scale_image:
                _, new_image = ResourceUtils.resize(Image.open(BytesIO(img_path.read_bytes())))
            else:
                new_image = Image.open(BytesIO(img_path.read_bytes()))

            new_hash, _ = ResourceUtils.calculate_hash(_pil_to_bytes(new_image))

            tags = {
                "XMP-dc:Creator": f"CT ({camera} {rp_name})",
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
            ext = img_path.suffix.lower()
            if ext == ".jpg":
                ext = ".jpeg"
            new_name = f"{dep_name}__{date_str_for_name}_{idx}{ext}".upper()
            dest_path = trapper_deployment_path / new_name
            shutil.copy2(img_path, dest_path)
            ResourceUtils.add_metadata([dest_path], tags)

            return True, None, date_taken, camera
        except Exception as e:
            return False, f"{img_path}: {e}", None, None

    report = Report(f"Preparing collections {",".join(collections)} for Trapper")

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

        # Prepare CSV if requested
        if create_deployment_table:
            csv_file = trapper_col_path / f"{col}_deployments.csv"
            csv_rows = []

        for deployment in all_deployments:
            dep_name = slugify(deployment.name)
            trapper_deployment_path = trapper_col_path / dep_name

            if trapper_deployment_path.exists():
                if not overwrite:
                    report.add_error(dep_name, "existing deployment",
                                     f"Trapper deployment path '{trapper_deployment_path}' already exists and overwrite is False.")
                    if progress_callback:
                        progress_callback(f"deployment_start:{col}:{dep_name}", 0)
                        progress_callback(f"deployment_complete:{col}:{dep_name}", 1)
                    continue
                else:
                    shutil.rmtree(trapper_deployment_path)
            trapper_deployment_path.mkdir(exist_ok=True)

            image_files = [f for f in deployment.rglob("*") if f.suffix.lower() in valid_extensions]
            image_files = natsorted(image_files)

            if progress_callback:
                progress_callback(f"deployment_start:{col}:{dep_name}", len(image_files))

            copied_count = 0
            deployment_dates = []
            futures = []
            cameras = []
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                for idx, img_path in enumerate(image_files, start=1):
                    futures.append(executor.submit(process_file, col, dep_name, idx, img_path, trapper_deployment_path, scale_images))

                for future in as_completed(futures):
                    success, error_msg, date_taken, camera = future.result()
                    if success:
                        copied_count += 1
                        if date_taken:
                            deployment_dates.append(date_taken)
                        if camera:
                            cameras.append(camera)
                    else:
                        report.add_error(dep_name, "copy error", error_msg)
                    if progress_callback:
                        progress_callback(f"file_progress:{col}:{dep_name}:{img_path}", 1)

            # Save deployment info for CSV
            if create_deployment_table and deployment_dates:
                min_date = min(deployment_dates).strftime("%Y-%m-%dT%H:%M:%S%z")
                max_date = max(deployment_dates).strftime("%Y-%m-%dT%H:%M:%S%z")

                try:
                    loc_id = dep_name.split("-", 1)[1]
                except (ValueError, IndexError):
                    loc_id = ""

                csv_rows.append([dep_name, loc_id,min_date, max_date, cameras[0]])

            if copied_count:
                report.add_success(dep_name, "deployment exported")

            if progress_callback:
                progress_callback(f"deployment_complete:{col}:{dep_name}", 1)

        # Write CSV for the collection
        if create_deployment_table and csv_rows:
            with csv_file.open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["deploymentID", "locationID", "deploymentStart", "deploymentEnd", "cameraModel"])
                writer.writerows(csv_rows)

    report.finish()
    return report