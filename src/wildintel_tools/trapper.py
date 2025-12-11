import re
import unicodedata
from pathlib import Path
from typing import List
from zoneinfo import ZoneInfo
import logging
import csv

from src.wildintel_tools.resouceutils import ResourceUtils

logger = logging.getLogger(__name__)

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


def get_deployments_csv_template(
    data_path: Path,
    output_path: Path = None,
    collections: List[Path] = [],
    timezone: ZoneInfo = None,
    ignore_dst: bool = False,
    callback: callable = None,
) -> int:
    """Generate a CSV template with deployment metadata from image/video files.

    Args:
        data_path: Root directory containing collections
        output_path: Directory where the CSV template will be saved
        collections: List of collection paths to process
        timezone: Timezone to use for datetime operations (default: UTC)
        ignore_dst: If True, ignore DST transitions when parsing dates

    Returns:
        0 on success
    """
    logger.info('Generating "deployments.csv" template ...')

    if timezone is None:
        timezone = ZoneInfo("UTC")

    if not data_path.is_dir():
        logger.error(f"Directory does not exist: {data_path}")
        return 1

    if not output_path:
        output_path = data_path
    else:
        output_path.mkdir(parents=True, exist_ok=True)

    outfile = output_path / "deployments.csv"

    if not collections:
        collections = [entry.name for entry in data_path.iterdir() if entry.is_dir()]

    data = {
        "deploymentID": [],
        "locationID": [],
        "deploymentStart": [],
        "deploymentEnd": [],
        "cameraModel": [],
    }

    dt_format = "%Y-%m-%dT%H:%M:%S%z"

    #if callback:
    #    callback(action="Processing collections", status="start", total=len(collections))

    for col in collections:
        col_path = data_path / col
        deployments = [d for d in col_path.iterdir() if d.is_dir()]

        for deployment in deployments:

            if not any(deployment.iterdir()):
                continue

            camera_model = ""
            rdates = []

            for file_path in deployment.glob("*"):
                if file_path.is_file():
                    metadata=ResourceUtils.get_exif_tag()

                    if metadata:
                        rdate = ResourceUtils.parse_date_recorded(
                            metadata,
                            timezone=timezone,
                            fallback=True,
                            ignore_dst=ignore_dst,
                            convert_to_utc=False,
                        )
                        rdates.append(rdate)

                        if not camera_model:
                            camera_model = ResourceUtils.get_camera_model(metadata)

            if not rdates:
                continue

            min_rdate = min(rdates).strftime(dt_format)
            max_rdate = max(rdates).strftime(dt_format)

            data["deploymentStart"].append(min_rdate)
            data["deploymentEnd"].append(max_rdate)

            dep_id = slugify(deployment.name)
            data["deploymentID"].append(dep_id)

            try:
                loc_id = dep_id.split("-", 1)[1]
            except (ValueError, IndexError):
                loc_id = ""

            data["locationID"].append(loc_id)
            data["cameraModel"].append(camera_model)

    # Write CSV using standard library
    headers = [
        "deploymentID",
        "locationID",
        "deploymentStart",
        "deploymentEnd",
        "cameraModel",
    ]

    with outfile.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(headers)

        rows = zip(
            data["deploymentID"],
            data["locationID"],
            data["deploymentStart"],
            data["deploymentEnd"],
            data["cameraModel"],
        )

        for row in rows:
            writer.writerow(row)

    logger.info(
        f"✓ The template was successfully generated! You can find it here: {outfile}"
    )

    return 0