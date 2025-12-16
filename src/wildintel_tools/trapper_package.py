from collections import OrderedDict
import datetime
import logging
from pathlib import Path
import zipfile
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Literal
import os

import yaml

from wildintel_tools.reports import Report
from wildintel_tools.resouceutils import ResourceUtils

logger = logging.getLogger(__name__)

# -------------------------
# YAML OrderedDict support
# -------------------------
_mapping_tag = yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG


def dict_representer(dumper, data):
    return dumper.represent_dict(data.items())


def dict_constructor(loader, node):
    return OrderedDict(loader.construct_pairs(node))


yaml.add_representer(OrderedDict, dict_representer)
yaml.add_constructor(_mapping_tag, dict_constructor)


# =========================
# YAML DEFINITION GENERATOR
# =========================
class YAMLDefinitionGeneratorParallel:
    """Parallel YAML definition generator.

    Parallelizes resource-level metadata extraction while preserving
    deterministic ordering in the resulting YAML structure.
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
        max_workers: int | None = None,
    ):
        self.data_dir = Path(data_dir)
        self.collections = collections
        self.project_id = project_id
        self.timezone = timezone
        self.timezone_ignore_dst = timezone_ignore_dst
        self.image_ext = image_ext
        self.video_ext = video_ext
        self.all_ext = image_ext + video_ext
        self.exiftool = exiftool
        self.max_workers = max_workers or min(32, (os.cpu_count() or 4) * 2)

        self.files: list[Path] = []
        self.data_dict: OrderedDict | None = None

    # ---------- helpers ----------
    def filter_files(self, files: list[str]) -> list[str]:
        return [f for f in files if Path(f).suffix.lower() in self.all_ext]

    def get_metadata(self, file_path: Path) -> dict:
        try:
            return ResourceUtils.get_exif_from_path(
                file_path, ResourceUtils.METADATA_EXIF_TAGS
            )
        except Exception as e:
            logger.error(f"EXIF failed for {file_path}: {e}")
            return {}

    def get_date_recorded(self, filepath: Path, metadata: dict) -> str:
        dt = ResourceUtils.parse_date_recorded(
            metadata,
            timezone=self.timezone,
            fallback=True,
            ignore_dst=self.timezone_ignore_dst,
        )
        return datetime.datetime.strftime(dt, "%Y-%m-%dT%H:%M:%S%z")

    def build_resource(self, resource: str, base: Path) -> OrderedDict:
        path = base / resource
        metadata = self.get_metadata(path)

        return OrderedDict(
            name=resource,
            file=resource,
            date_recorded=self.get_date_recorded(path, metadata),
            mime_type=metadata.get("MIMEType"),
            file_width=metadata.get("ImageWidth"),
            file_height=metadata.get("ImageHeight"),
            file_size=path.stat().st_size,
            file_fps=metadata.get("VideoFrameRate"),
            file_duration=metadata.get("Duration"),
        )

    # ---------- core ----------
    def build(self) -> OrderedDict:
        data = OrderedDict(collections=[])

        for col_name in self.collections:
            col_path = self.data_dir / col_name
            col = OrderedDict(
                name=col_name,
                project_id=self.project_id,
                timezone=str(self.timezone),
                timezone_ignore_dst=self.timezone_ignore_dst,
                resources_dir=col_name,
                deployments=[],
            )

            deployments = sorted(p.name for p in col_path.iterdir() if p.is_dir())

            for dep_name in deployments:
                dep_path = col_path / dep_name
                dep = OrderedDict(deployment_id=dep_name, resources=[])

                resources = self.filter_files(
                    sorted(p.name for p in dep_path.iterdir() if p.is_file())
                )

                with ThreadPoolExecutor(self.max_workers) as ex:
                    futures = [
                        ex.submit(self.build_resource, r, dep_path)
                        for r in resources
                    ]
                    for f in as_completed(futures):
                        dep["resources"].append(f.result())

                dep["resources"].sort(key=lambda r: r["name"])
                col["deployments"].append(dep)

                for r in resources:
                    self.files.append(dep_path / r)

            data["collections"].append(col)

        if not self.files:
            raise ValueError("No valid files found to package")

        self.data_dict = data
        return data


# =========================
# PACKAGE SPLITTING MODELS
# =========================
@dataclass
class PackagePart:
    index: int
    files: list[Path]


# =========================
# DATA PACKAGE GENERATOR
# =========================


class DataPackageGeneratorParallel:
    """Parallel data package generator with progress callbacks and reporting."""

    DEFAULT_EXTENSIONS_IMAGES = [".jpg", ".jpeg", ".png"]
    DEFAULT_EXTENSIONS_VIDEOS = [".mp4", ".avi", ".mov"]

    def __init__(
        self,
        data_path: Path,
        project_id: int,
        timezone: ZoneInfo | str,
        output_path: Path | None = None,
        collections: list[str] | None = None,
        timezone_ignore_dst: bool = False,
        image_ext: list[str] | None = None,
        video_ext: list[str] | None = None,
        package_name: str | None = None,
        max_zip_size: int | None = None,
        split_strategy: Literal["size", "deployment", "collection"] = "size",
        max_workers: int | None = None,
    ):
        self.data_path = Path(data_path)
        self.output_path = Path(output_path) if output_path else self.data_path
        self.output_path.mkdir(parents=True, exist_ok=True)

        self.project_id = project_id
        self.package_name = package_name or "package"
        self.max_zip_size = max_zip_size
        self.split_strategy = split_strategy

        self.image_ext = image_ext or self.DEFAULT_EXTENSIONS_IMAGES
        self.video_ext = video_ext or self.DEFAULT_EXTENSIONS_VIDEOS

        self.collections = (
            collections
            if collections
            else [p.name for p in self.data_path.iterdir() if p.is_dir()]
        )

        self.timezone = timezone if isinstance(timezone, ZoneInfo) else ZoneInfo(str(timezone))
        self.timezone_ignore_dst = timezone_ignore_dst

        self.timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")

        self.yaml_generator = YAMLDefinitionGeneratorParallel(
            data_dir=self.data_path,
            collections=self.collections,
            image_ext=self.image_ext,
            video_ext=self.video_ext,
            timezone=self.timezone,
            timezone_ignore_dst=self.timezone_ignore_dst,
            project_id=self.project_id,
            max_workers=max_workers,
        )

    # ---------- helpers ----------
    def resource_path(self, col, dep, res) -> Path:
        return self.data_path / col["name"] / dep["deployment_id"] / res["file"]

    def iter_collections(self, definition):
        for col in definition["collections"]:
            yield col

    # ---------- split logic ----------
    def split_by_size(self, files: list[Path]) -> list[list[Path]]:
        if not self.max_zip_size:
            return [files]
        chunks, current, size = [], [], 0
        for f in files:
            fs = f.stat().st_size
            if current and size + fs > self.max_zip_size:
                chunks.append(current)
                current, size = [], 0
            current.append(f)
            size += fs
        if current:
            chunks.append(current)
        return chunks

    def split(self, files: list[Path]) -> list[PackagePart]:
        chunks = self.split_by_size(files)
        return [PackagePart(i + 1, c) for i, c in enumerate(chunks)]

    # ---------- YAML filtering ----------
    def filter_definition(self, definition: OrderedDict, chunk: set[Path]) -> OrderedDict:
        out = OrderedDict(collections=[])
        for col in definition["collections"]:
            col_copy = OrderedDict(col, deployments=[])
            for dep in col["deployments"]:
                dep_copy = OrderedDict(dep, resources=[])
                for res in dep["resources"]:
                    if self.resource_path(col, dep, res).resolve() in chunk:
                        dep_copy["resources"].append(res)
                if dep_copy["resources"]:
                    col_copy["deployments"].append(dep_copy)
            if col_copy["deployments"]:
                out["collections"].append(col_copy)
        return out

    # ---------- writers ----------
    def write_yaml(self, path: Path, definition: OrderedDict) -> None:
        with path.open("w") as f:
            yaml.dump(definition, f)

    def write_zip(self, path: Path, files: list[Path]) -> None:
        with zipfile.ZipFile(path, "w", allowZip64=True) as z:
            for f in files:
                z.write(f, f.relative_to(self.data_path))

    # ---------- run ----------
    def run(self, progress_callback=None) -> Report:
        report = Report(f"Preparing packages  for Trapper")

        # Build full YAML once
        definition = self.yaml_generator.build()

        for col in definition["collections"]:
            col_name = col["name"]
            collection_output_dir = self.output_path / col_name
            collection_output_dir.mkdir(parents=True, exist_ok=True)

            deployments = col["deployments"]
            if progress_callback:
                progress_callback(f"collection_start:{col['name']}", len(deployments))

            for dep in deployments:
                dep_name = dep["deployment_id"]

                try:
                    # split and export per deployment
                    files = [
                        self.resource_path(col, dep, r)
                        for r in dep["resources"]
                    ]
                    if progress_callback:
                        progress_callback(f"deployment_start:{col['name']}:{dep_name}", len(files))

                    parts = self.split(files)

                    for part in parts:
                        yaml_path = collection_output_dir / (
                            f"{self.package_name}_{self.project_id}_"
                            f"{self.timestamp}_{col_name}_{dep_name}_"
                            f"part{part.index:03d}.yaml"
                        )

                        zip_path = yaml_path.with_suffix(".zip")

                        filtered = self.filter_definition(definition, {p.resolve() for p in part.files})

                        self.write_yaml(yaml_path, filtered)
                        self.write_zip(zip_path, part.files)

                    report.add_success(dep_name, "deployment exported")
                    if progress_callback:
                        progress_callback(f"file_progress:{col['name']}:{dep_name}:none", len(files))
                        progress_callback(f"deployment_complete:{col['name']}:{dep_name}", 1)

                except Exception as e:
                    report.add_error(dep_name, "deployment exported", str(e))
                    if progress_callback:
                        progress_callback(f"deployment_error:{dep_name}", 0)

            if progress_callback:
                progress_callback(f"collection_done:{col['name']}", len(deployments))

        if progress_callback:
            progress_callback("finished", 0)

        report.finish()
        return report
