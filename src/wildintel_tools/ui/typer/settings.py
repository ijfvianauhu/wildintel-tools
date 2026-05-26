"""
Settings models module.

Pydantic models for all wildintel-tools configuration sections:
LOGGER, GENERAL, WILDINTEL, EPICOLLECT, ZOONIVERSE, ZOONIVERSE_CONNECTOR.

The default settings directory is platform-specific:
- Linux:   ``~/.config/wildintel-tools/``
- macOS:   ``~/Library/Application Support/wildintel-tools/``
- Windows: ``%LOCALAPPDATA%\\wildintel-tools\\``
"""

import typer
import platformdirs
from pathlib import Path
from typing import Dict, Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, EmailStr, SecretStr, \
    field_validator, field_serializer

APP_NAME = "wildintel-tools"
DEFAULT_SETTINGS_DIR = Path(typer.get_app_dir(APP_NAME))


def get_documents_dir() -> Path:
    """Return the user's Documents directory using :mod:`platformdirs`."""
    return Path(platformdirs.user_documents_dir())


def get_app_documents_dir() -> Path:
    """Return the application's documents directory (``<Documents>/wildintel-tools``)."""
    return get_documents_dir() / APP_NAME


class LoggerSettings(BaseModel):
    loglevel: int = Field(
        default=1, ge=0, le=2,
        description="Logging verbosity level: 0 = ERROR, 1 = INFO, 2 = DEBUG.",
    )
    filename: str = Field(
        default="",
        description="Path to the log file. Leave empty to log to stdout only. Must end with '.log' if set.",
        pattern=r"(^$|^.*\.log$)",
    )


class GeneralSettings(BaseModel):
    model_config = ConfigDict(validate_default=True)

    host: HttpUrl = Field(
        default="https://wildintel-trap.uhu.es/",
        description="Base URL of the Trapper server (must include trailing slash).",
    )
    login: EmailStr = Field(
        default="user@example.com",
        description="Email address used to authenticate against the Trapper server.",
    )
    password: SecretStr = Field(
        default=SecretStr("secret"),
        description="Password for the Trapper account. Stored as a secret value.",
    )
    project_id: int = Field(
        default=123, ge=1,
        description="Numeric ID of the Trapper research project to work with.",
    )
    verify_ssl: bool = Field(
        default=True,
        description="Whether to verify the SSL certificate of the Trapper server. Set to False only for development.",
    )
    ffmpeg: str = Field(
        default="ffmpeg",
        description="Path or command name of the ffmpeg binary used for video processing.",
    )
    exiftool: str = Field(
        default="exiftool",
        description="Path or command name of the exiftool binary used for reading image metadata.",
    )
    data_dir: Path = Field(
        default_factory=lambda: get_documents_dir() / "wildintel-tools" / "collections",
        description=(
            "Local directory where downloaded Trapper collections are stored. "
            "Defaults to the user's Documents folder. Created automatically if it does not exist."
        ),
    )

    @field_serializer("host")
    def serialize_host(self, value: HttpUrl) -> str:
        return str(value)

    @field_validator("data_dir", mode="before")
    @classmethod
    def create_data_dir(cls, v: Any) -> Path:
        p = Path(v)
        p.mkdir(parents=True, exist_ok=True)
        return p


class WildIntelSettings(BaseModel):
    model_config = ConfigDict(validate_default=True)

    rp_name: str = Field(
        default="WildINTEL",
        description="Name of the WildINTEL research project used as a label in generated outputs.",
    )
    coverage: str = Field(
        default="Doñana National Park",
        description="Geographic area covered by the camera-trap deployment (used in metadata exports).",
    )
    publisher: str = Field(
        default="University of Huelva",
        description="Organisation responsible for publishing the dataset (used in metadata exports).",
    )
    owner: str = Field(
        default="University of Huelva",
        description="Organisation or individual that owns the dataset (used in metadata exports).",
    )
    tolerance_hours: int = Field(
        default=1,
        description="Maximum time difference in hours allowed when matching camera-trap records across sources.",
    )
    resize_img: bool = Field(
        default=False,
        description="Whether to resize images before uploading them to Zooniverse.",
    )
    resize_img_size: list[int] = Field(
        default_factory=lambda: [1024, 768],
        description="Target [width, height] in pixels when resize_img is True.",
    )
    overwrite: bool = Field(
        default=False,
        description="If True, existing output files will be overwritten without prompting.",
    )
    timezone: str | None = Field(
        default="UTC",
        description="IANA timezone name (e.g. 'Europe/Madrid') used to interpret camera-trap timestamps.",
    )
    ignore_dst: bool | None = Field(
        default=False,
        description="If True, Daylight Saving Time transitions are ignored when parsing timestamps.",
    )
    convert_to_utc: bool | None = Field(
        default=True,
        description="If True, all timestamps are converted to UTC before being stored or exported.",
    )
    remove_zip: bool | None = Field(
        default=True,
        description="If True, ZIP archives are deleted after being successfully extracted.",
    )
    trigger: bool | None = Field(
        default=True,
        description="If True, only triggered (motion-detected) images are processed; continuous captures are skipped.",
    )
    output_dir: Path = Field(
        default_factory=lambda: get_documents_dir() / "wildintel-tools" / "readycollections",
        description=(
            "Local directory where processed collections ready for upload are saved. "
            "Defaults to the user's Documents folder. Created automatically if it does not exist."
        ),
    )

    @field_validator("timezone")
    def validate_timezone(cls, v):
        try:
            ZoneInfo(v)
        except Exception:
            raise ValueError(f"Invalid timezone: {v}")
        return v

    @field_validator("output_dir", mode="before")
    @classmethod
    def create_output_dir(cls, v: Any) -> Path:
        p = Path(v)
        p.mkdir(parents=True, exist_ok=True)
        return p


class EpiCollectSettings(BaseModel):
    client_id: int = Field(default=0, description="EpiCollect5 OAuth2 client ID for API authentication.")
    client_secret: SecretStr = Field(default=SecretStr("secret"), description="EpiCollect5 OAuth2 client secret. Stored as a secret value.")
    app_slug: str = Field(default="default", description="EpiCollect5 application slug (project identifier in the URL).")
    site_alias: Dict[str, str] = Field(default_factory=dict, description="Mapping of EpiCollect5 site names to Trapper deployment IDs.")
    release_alias: Dict[str, str] = Field(default_factory=dict, description="Mapping of EpiCollect5 release names to internal identifiers.")

    site_field: str = Field(default="", description="Name of the EpiCollect5 form field that contains the site identifier.")
    release_field: str = Field(default="", description="Name of the EpiCollect5 form field that contains the release/session identifier.")
    start_date_field: str = Field(default="", description="Name of the EpiCollect5 form field for the deployment start date.")
    end_date_field: str = Field(default="", description="Name of the EpiCollect5 form field for the deployment end date.")
    correct_setup_field: str = Field(default="", description="Name of the EpiCollect5 form field indicating whether the setup was correct.")
    correct_tstamp_field: str = Field(default="", description="Name of the EpiCollect5 form field indicating whether the timestamp is correct.")
    view_quality_field: str = Field(default="", description="Name of the EpiCollect5 form field for the camera view quality assessment.")
    tags_field: str = Field(default="", description="Name of the EpiCollect5 form field for free-text tags.")
    comments_field: str = Field(default="", description="Name of the EpiCollect5 form field for free-text comments.")
    managers_field: str = Field(default="", description="Name of the EpiCollect5 form field listing the deployment managers.")
    setup_by_field: str = Field(default="", description="Name of the EpiCollect5 form field recording who set up the camera.")
    camera_id_field: str = Field(default="", description="Name of the EpiCollect5 form field for the camera unit identifier.")
    camera_model_field: str = Field(default="", description="Name of the EpiCollect5 form field for the camera model name.")
    camera_interval_field: str = Field(default="", description="Name of the EpiCollect5 form field for the camera trigger interval (seconds).")
    camera_height_field: str = Field(default="", description="Name of the EpiCollect5 form field for the camera mounting height (metres).")
    camera_depth_field: str = Field(default="", description="Name of the EpiCollect5 form field for the camera depth/distance setting.")
    camera_tilt_field: str = Field(default="", description="Name of the EpiCollect5 form field for the camera tilt angle (degrees).")
    camera_heading_field: str = Field(default="", description="Name of the EpiCollect5 form field for the compass heading the camera faces.")
    session_field: str = Field(default="", description="Name of the EpiCollect5 form field for the session or survey identifier.")
    array_field: str = Field(default="", description="Name of the EpiCollect5 form field for the camera array identifier.")
    feature_type_field: str = Field(default="", description="Name of the EpiCollect5 form field for the habitat feature type.")
    habitat_field: str = Field(default="", description="Name of the EpiCollect5 form field for the habitat classification.")
    capture_method_field: str = Field(default="", description="Name of the EpiCollect5 form field for the capture method (e.g. motion, time-lapse).")
    bait_type_field: str = Field(default="", description="Name of the EpiCollect5 form field for the type of bait used, if any.")


class ZooniverseSettings(BaseModel):
    zooniverse_username: str | None = Field(
        default="myuser",
        description="Zooniverse account username used for API authentication.",
    )
    zooniverse_password: SecretStr | None = Field(
        default=SecretStr("mypassword"),
        description="Zooniverse account password. Stored as a secret value.",
    )
    zooniverse_project_id: str | None = Field(
        default="myprojectid",
        description="Zooniverse project identifier (numeric ID or 'owner/project-slug').",
    )


class ZooniverseConnectorSettings(BaseModel):
    upload_collection_n_images_seq: int | None = Field(
        default=5,
        description="Number of images grouped into a single Zooniverse subject (sequence length).",
    )
    upload_collection_max_interval: int | None = Field(
        default=90,
        description="Maximum time gap in seconds between consecutive images in the same sequence.",
    )
    upload_collection_download_attempts: int | None = Field(
        default=5,
        description="Maximum number of retry attempts when downloading a media file from Trapper.",
    )
    upload_collection_download_delay: int | None = Field(
        default=15,
        description="Delay in seconds between download retry attempts from Trapper.",
    )
    upload_collection_max_attempts_per_subject: int | None = Field(
        default=5,
        description="Maximum number of retry attempts when uploading a single subject to Zooniverse.",
    )
    upload_collection_delay_seconds_per_subject: int | None = Field(
        default=30,
        description="Delay in seconds between upload retry attempts for a single subject.",
    )
    upload_collection_max_workers: int | None = Field(
        default=4,
        description="Number of parallel workers for concurrent image download and upload.",
    )
    annotations_classified_by: str | None = Field(
        default="zooniverse@wildintel-project.org",
        description="Trapper username attributed as the classifier when uploading Zooniverse observations.",
    )
    annotations_max_file_size_mb: float | None = Field(
        default=1.5,
        description=(
            "Maximum CSV file size in MB for annotation exports. "
            "If the output exceeds this limit it is automatically split into "
            "multiple _part001.csv, _part002.csv … files."
        ),
    )


class Settings(BaseModel):
    LOGGER: LoggerSettings = Field(default_factory=LoggerSettings)
    GENERAL: GeneralSettings = Field(default_factory=GeneralSettings)
    WILDINTEL: WildIntelSettings = Field(default_factory=WildIntelSettings)
    EPICOLLECT: EpiCollectSettings = Field(default_factory=EpiCollectSettings)
    ZOONIVERSE: ZooniverseSettings = Field(default_factory=ZooniverseSettings)
    ZOONIVERSE_CONNECTOR: ZooniverseConnectorSettings = Field(
        default_factory=ZooniverseConnectorSettings
    )
