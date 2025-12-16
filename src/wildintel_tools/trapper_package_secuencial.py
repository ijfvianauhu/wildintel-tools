from collections import OrderedDict
import datetime
import logging
from pathlib import Path
import zipfile
from zoneinfo import ZoneInfo

#import tqdm
import yaml

from wildintel_tools.resouceutils import ResourceUtils

#from trapper_tools.utils import (
#    METADATA_EXIF_TAGS,
#    extract_metadata,
#    parse_date_recorded,
#    slugify,
#)

logger = logging.getLogger(__name__)


# YAML mapping extension
_mapping_tag = yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG


def dict_representer(dumper, data):
    return dumper.represent_dict(data.items())


def dict_constructor(loader, node):
    return OrderedDict(loader.construct_pairs(node))


yaml.add_representer(OrderedDict, dict_representer)
yaml.add_constructor(_mapping_tag, dict_constructor)


class YAMLDefinitionGenerator:
    """Generate YAML definitions for data packages.

    This class generates YAML definitions for collections of media files,
    organizing them into a hierarchical structure of collections, deployments,
    and resources with associated metadata.
    """

    def __init__(
        self,
        data_dir: Path,
        project_id: int,
        collections: list[str],
        timezone: ZoneInfo,
        image_ext: list[str],
        video_ext: list[str],
        timezone_ignore_dst: bool = False,
        exiftool: str = "exiftool",
    ):
        self.data_dir = Path(data_dir)
        self.collections = collections
        self.timezone = timezone
        self.timezone_ignore_dst = timezone_ignore_dst
        self.image_ext = image_ext
        self.video_ext = video_ext
        self.all_ext = image_ext + video_ext
        self.project_id = project_id
        self.exiftool = exiftool
        self.files: list[Path] = []

    def get_collection_def(self, name: str) -> OrderedDict:
        collection_def = OrderedDict()
        collection_def["name"] = name
        collection_def["project_id"] = self.project_id
        collection_def["timezone"] = str(self.timezone)
        collection_def["timezone_ignore_dst"] = self.timezone_ignore_dst
        collection_def["resources_dir"] = name
        collection_def["deployments"] = []
        return collection_def

    def get_deployment_def(self, deployment: str) -> OrderedDict:
        deployment_def = OrderedDict()
        # apply slugify to deployment (directory) names to be compatible with Trapper standards
        # and to avoid any special characters in the deployment names
        #deployment_def["deployment_id"] = slugify(deployment)
        deployment_def["deployment_id"] = deployment
        deployment_def["resources"] = []
        return deployment_def

    def get_metadata(self, file_path: Path) -> dict:
        """Extract metadata from a file using ExifTool."""
        if not self.exiftool:
            raise ValueError("ExifTool is not configured or available.")

        try:
            metadada= ResourceUtils.get_exif_from_path(file_path, ResourceUtils.METADATA_EXIF_TAGS)
            return metadada
        except Exception as e:
            logger.error(f"Failed to extract metadata for {file_path}: {str(e)}")
            return {}

    def get_date_recorded(self, filepath: Path, metadata: dict) -> str:
        """Extract the date recorded from the file metadata.

        Args:
            filepath: Path to the media file
            metadata: Metadata dictionary extracted from the file

        Returns:
            Formatted datetime string in ISO format with timezone
        """
        dt = ResourceUtils.parse_date_recorded(
            metadata,
            timezone=self.timezone,
            fallback=True,
            ignore_dst=self.timezone_ignore_dst,
        )
        dt = datetime.datetime.strftime(dt, "%Y-%m-%dT%H:%M:%S%z")
        return dt

    def get_resource_def(self, resource: str, resources_level: Path) -> OrderedDict:
        filepath = resources_level / resource
        metadata = self.get_metadata(filepath)
        resource_def = OrderedDict()
        resource_def["name"] = resource
        resource_def["file"] = resource
        resource_def["date_recorded"] = self.get_date_recorded(
            filepath, metadata=metadata
        )
        resource_def["mime_type"] = metadata.get("MIMEType")
        resource_def["file_width"] = metadata.get("ImageWidth")
        resource_def["file_height"] = metadata.get("ImageHeight")
        resource_def["file_size"] = filepath.stat().st_size
        resource_def["file_fps"] = metadata.get("VideoFrameRate")
        resource_def["file_duration"] = metadata.get("Duration")
        return resource_def

    def filter_files(self, files: list[str], src_ext: list[str]) -> list[str]:
        """Filter files by their extensions."""
        return [f for f in files if Path(f).suffix.lower() in src_ext]

    def build_data_dict(self) -> OrderedDict:
        data_dict = OrderedDict()
        data_dict["collections"] = []

        # Create progress bar for collections processing
        #for collection in tqdm.tqdm(
        #    self.collections, desc="[INFO] Processing collections", unit="collection"
        #):
        for collection in self.collections:
            # first create collection object
            collection_obj = self.get_collection_def(name=collection)
            deployments_level = self.data_dir / collection

            try:
                deployments = [
                    entry.name
                    for entry in deployments_level.iterdir()
                    if entry.is_dir()
                ]
            except FileNotFoundError:
                raise FileNotFoundError(
                    f"Collection directory not found: {deployments_level}"
                )

            for deployment in deployments:
                deployment_obj = self.get_deployment_def(deployment)
                resources_level = deployments_level / deployment

                try:
                    resources = [
                        entry.name
                        for entry in resources_level.iterdir()
                        if entry.is_file()
                    ]
                    # sort resources by name
                    resources.sort()

                except FileNotFoundError:
                    raise FileNotFoundError(
                        f"Deployment directory not found: {resources_level}"
                    )

                resources = self.filter_files(resources, self.all_ext)

                # Create progress bar for resources processing within each deployment
                for resource in resources:
                #for resource in tqdm.tqdm(
                #    resources,
                #    desc=f"[INFO] Processing {deployment} resources",
                #    unit="file",
                #    leave=False,
                #):
                    resource_obj = self.get_resource_def(resource, resources_level)
                    deployment_obj["resources"].append(resource_obj)

                    # add the full path to self.files list
                    self.files.append(resources_level / resource)

                collection_obj["deployments"].append(deployment_obj)

            data_dict["collections"].append(collection_obj)

        if not self.files:
            raise ValueError(
                "There is nothing to package. Please check your --data-path argument "
                "and the selected image and video extensions."
            )

        return data_dict

    def dump_yaml(self, yaml_path: Path) -> None:
        """Write the data dictionary to a YAML file.

        Args:
            yaml_path: Path where the YAML file will be written
        """
        with yaml_path.open("w") as f:
            yaml.dump(self.data_dict, f)

    def run(self, yaml_path: Path) -> None:
        """Run the YAML generation process and write to file.

        Args:
            yaml_path: Path where the YAML file will be written
        """
        self.data_dict = self.build_data_dict()
        self.dump_yaml(yaml_path)


class DataPackageGenerator:
    """Generate data packages for collections of media files.

    This class handles the creation of data packages including YAML definitions
    and ZIP archives of media files, with proper metadata and organization.
    """

    DEFAULT_EXTENSIONS_IMAGES = [".jpg", ".jpeg", ".png"]
    DEFAULT_EXTENSIONS_VIDEOS = [".mp4", ".avi", ".mov"]

    def __init__(
        self,
        data_path: Path,
        project_id: int,
        timezone: ZoneInfo | str,
        output_path: Path = None,
        collections: list[str] | None = None,
        timezone_ignore_dst: bool = False,
        image_ext: list[str] | None = None,
        video_ext: list[str] | None = None,
        package_name: str | None = None,
        exiftool: str = "exiftool",
    ):
        self.project_id = project_id
        self.package_name = package_name
        self.exiftool = exiftool

        # Validate paths
        self.data_path = Path(data_path)
        if not output_path:
            self.output_path = data_path
        else:
            self.output_path = Path(output_path)

        if not self.data_path.is_dir():
            raise ValueError(f"Directory does not exist: {self.data_path}")
        if not self.output_path.is_dir():
            self.output_path.mkdir(parents=True, exist_ok=True)

        self.image_ext = image_ext or self.DEFAULT_EXTENSIONS_IMAGES
        self.video_ext = video_ext or self.DEFAULT_EXTENSIONS_VIDEOS

        if not collections:
            self.collections = [
                entry.name for entry in data_path.iterdir() if entry.is_dir()
            ]
        else:

            # validate provided collection paths
            for collection in collections:
                collection_path = self.data_path / collection
                if not collection_path.is_dir():
                    raise ValueError(f"Directory does not exist: {collection_path}")
            self.collections = collections

        # validate provided timezone format
        tz_error_msg = (
            "You must specify a correct timezone. See:\n"
            "https://en.wikipedia.org/wiki/List_of_tz_database_time_zones"
        )
        if not isinstance(timezone, ZoneInfo):
            try:
                self.timezone = ZoneInfo(str(timezone))
            except Exception:
                raise ValueError(tz_error_msg)
        else:
            self.timezone = timezone
        self.timezone_ignore_dst = timezone_ignore_dst

        # build file paths
        self.timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        self.yaml_path = self.output_path / self.get_package_name(
            ".yaml", self.timestamp
        )
        self.zip_path = self.output_path / self.get_package_name(".zip", self.timestamp)

        self.yaml_generator = self.get_yaml_generator()

    def get_package_name(self, ext: str, timestamp: str) -> str:
        """Generate a package filename with proper naming convention."""
        if self.package_name:
            name = f"{self.package_name}_{self.project_id}_{timestamp}{ext}"
        else:
            name = f"package_{self.project_id}_{timestamp}{ext}"
        return name

    def get_yaml_generator(self) -> YAMLDefinitionGenerator:
        """Create and return a YAMLDefinitionGenerator instance."""
        return YAMLDefinitionGenerator(
            data_dir=self.data_path,
            collections=self.collections,
            image_ext=self.image_ext,
            video_ext=self.video_ext,
            timezone=self.timezone,
            timezone_ignore_dst=self.timezone_ignore_dst,
            project_id=self.project_id,
            exiftool=self.exiftool,
        )

    def make_zip(self, zip_path: Path, files: list[Path]) -> None:
        """Create a ZIP archive containing the specified files.

        Args:
            zip_path: Path where the ZIP file will be created
            files: List of files to include in the archive
        """
        with zipfile.ZipFile(zip_path, "w", allowZip64=True) as _zipfile:
            # Create progress bar for zip file creation
            for file_path in files:
            #for file_path in tqdm.tqdm(
            #    files, desc="[INFO] Creating ZIP archive", unit="file"
            #):
                # Get relative path from data directory
                f_archive = file_path.relative_to(self.data_path)

                # Get deployment name (second level of path after collection)
                deployment_name = f_archive.parts[1]

                # Create new path with slugified deployment name
                f_archive = (
                    #f_archive.parent.parent / slugify(deployment_name) / f_archive.name
                    f_archive.parent.parent / deployment_name / f_archive.name
                )
                _zipfile.write(file_path, str(f_archive))

    def run(self) -> None:
        """Execute the package generation process."""
        logger.info(f"Package generation started at {self.timestamp}")
        try:

            logger.info(f"Generating YAML definition at {self.yaml_path}")
            self.yaml_generator.run(self.yaml_path)
            logger.info("✓ YAML definition generated successfully!")

            logger.info(f"Creating ZIP archive at {self.zip_path}")
            self.make_zip(self.zip_path, self.yaml_generator.files)
            logger.info("✓ ZIP archive created successfully!")

        except Exception as e:
            # Clean up files in case of error
            for file_path in [self.yaml_path, self.zip_path]:
                file_path.unlink(missing_ok=True)
            raise e
