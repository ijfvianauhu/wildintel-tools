"""
Settings management module.

This module provides functionality to manage project-specific configuration files
based on the `Dynaconf` and "Pydantic" libraries. It includes utilities for:

- Creating new project settings from a default or custom template.
- Validating settings with type and value constraints.
- Editing settings interactively via a command-line editor.
- Managing multiple configuration environments.
- Accessing and updating individual parameters safely.

The configuration files are stored in TOML format (default location: ``~/.trapper-tools``)
and grouped into logical sections such as ``LOGGER``, ``GENERAL``, and ``WILDINTEL``.

Example:
    .. code-block:: python

        from wildintel_tools.config.settings_manager import SettingsManager

        sm = SettingsManager()
        sm.create_project_settings("my_project")
        settings = sm.load_settings("my_project", validate=True)
        print(settings.GENERAL.host)
"""

import os
import platform
import subprocess
from pathlib import Path
from typing import List, Optional, Dict, Type, get_origin, Union, get_args, Any
import tempfile
from zoneinfo import ZoneInfo

from dynaconf import Dynaconf
from dynaconf import loaders
from pydantic import BaseModel, Field, HttpUrl, EmailStr, FilePath, DirectoryPath, ValidationError, SecretStr, \
    TypeAdapter, field_validator


class LoggerSettings(BaseModel):
    loglevel: int = Field(ge=0, le=2)
    filename: str = Field(
        default="",
        description="Empty string or string ending in .log",
        pattern=r"(^$|^.*\.log$)",
    )

class GeneralSettings(BaseModel):
    host: HttpUrl
    login: EmailStr
    password: SecretStr
    project_id: int = Field(..., ge=1)
    verify_ssl: bool
    ffmpeg: str
    exiftool: str
    data_dir: DirectoryPath

class WildIntelSettings(BaseModel):
    rp_name: str
    coverage: str
    publisher: str
    owner: str
    tolerance_hours: int
    resize_img: bool
    resize_img_size: list[int]
    #resize_img_width: int
    #resize_img_height: int
    overwrite: bool
    timezone: str | None = "UTC"
    ignore_dst: bool | None = True
    convert_to_utc: bool | None = True
    remove_zip: bool | None = True
    trigger: bool | None = True
    output_dir: DirectoryPath

    @field_validator("timezone")
    def validate_timezone(cls, v):
        try:
            ZoneInfo(v)
        except Exception:
            raise ValueError(f"Invalid timezone: {v}")
        return v

class EpiCollectSettings(BaseModel):
    client_id: int
    client_secret: SecretStr
    app_slug: str
    site_alias: Dict[str, str] = {}
    release_alias: Dict[str, str] = {}

    site_field: str = ""
    release_field: str = ""
    start_date_field: str = ""
    end_date_field: str = ""
    correct_setup_field: str = ""
    correct_tstamp_field: str = ""
    view_quality_field: str = ""
    tags_field: str = ""
    comments_field: str = ""
    managers_field: str = ""
    setup_by_field: str = ""
    camera_id_field: str = ""
    camera_model_field: str = ""
    camera_interval_field: str = ""
    camera_height_field: str = ""
    camera_depth_field: str = ""
    camera_tilt_field: str = ""
    camera_heading_field: str = ""
    session_field: str = ""
    array_field: str = ""
    feature_type_field: str = ""
    habitat_field: str = ""
    capture_method_field: str = ""
    bait_type_field: str = ""

class Settings(BaseModel):
    LOGGER: LoggerSettings
    GENERAL: GeneralSettings
    WILDINTEL: WildIntelSettings
    EPICOLLECT: EpiCollectSettings

class SettingsManager:
    """
    Manages Trapper-Tools configuration files across multiple projects.

    This class wraps around :class:`dynaconf.Dynaconf` to provide:
    - Loading and validating TOML-based settings.
    - Creating new configuration files from a template.
    - Interactive editing and validation of configuration.
    - Parameter-level access and update utilities.

    :param settings_dir: Optional directory path where settings files are stored.
                         Defaults to ``~/.trapper-tools``.
    :type settings_dir: Optional[Path]
    """

    def __init__(self, settings_dir: Optional[Path] = None):
        """
        Initialize a :class:`SettingsManager` instance.

        :param settings_dir: Directory to store settings files. Defaults to ``~/.trapper-tools``.
        :type settings_dir: Optional[Path]
        """
        self.settings_dir = Path(settings_dir) if settings_dir else Path.home() / ".trapper-tools"
        self.settings_dir.mkdir(parents=True, exist_ok=True)
        self.SETTINGS_ORDER = SettingsManager._generate_settings_order()

    def create_project_settings(
        self,
        project_name: str,
        template: Optional[Path] = None,
        env_file: bool = False,
        validate: bool = True,
    ) -> Path:
        """
        Create a new project configuration file from a TOML template.

        :param project_name: Name of the project/environment.
        :type project_name: str
        :param template: Optional custom template file path. Defaults to the internal template.
        :type template: Optional[Path]
        :param env_file: Whether to load environment variables using Dynaconf.
        :type env_file: bool
        :raises FileNotFoundError: If the template file does not exist.
        :return: Path to the newly created settings file.
        :rtype: Path
        """
        settings_file = self.settings_dir / f"{project_name}.toml"
        template = template or self._default_template_file()

        if not template.exists():
            raise FileNotFoundError(f"Settings template not found: {template}")

        settings = Dynaconf(
            settings_files=[str(template)],
            load_dotenv=env_file,  # Load environment variables
            envvar_prefix=False,
            ignore_unknown_envvars=True,
            validate_on_update="all",
        )

        settings_model = SettingsManager.load_from_dict(settings.to_dict(), validate)
        self.export_settings(settings_model, settings_file)

        return settings_file

    def load_settings(
        self,
        project_name: str,
        validate: bool = True,
        create:bool = True,
    ) -> Settings:
        """
        Load settings for a given project.

        :param project_name: Name of the project.
        :type project_name: str
        :param validate: Whether to validate settings upon loading.
        :type validate: bool
        :param create: Automatically create settings file if it does not exist.
        :type create: bool
        :raises FileNotFoundError: If the settings file does not exist and creation is disabled.
        :return: A Dynaconf object containing loaded settings.
        :rtype: Dynaconf
        """
        settings_file = self.settings_dir / f"{project_name}.toml"

        if not settings_file.exists() and create:
            settings_file = self.create_project_settings(project_name)
        elif not settings_file.exists():
           raise FileNotFoundError(f"Settings file not found: {settings_file}")

        settings = Dynaconf(settings_files=[str(settings_file)])
        raw = settings.to_dict()

        return self.load_from_dict(raw, validate)

    def list_projects(self) -> list[str]:
        """
        List all available project configuration files.

        :return: List of project names (without the `.toml` extension).
        :rtype: list[str]
        """
        return [f.stem for f in self.settings_dir.glob("*.toml")]

    def get_settings_path(self, project_name: str) -> Path:
        """
        Get the absolute path to a project's settings file.

        :param project_name: Project/environment name.
        :type project_name: str
        :return: Path to the TOML settings file.
        :rtype: Path
        """
        return self.settings_dir / f"{project_name}.toml"

    def export_settings(self, settings_data: Settings, setting_path: Path) -> None:
        """
        Export the given settings dictionary to a TOML file, preserving key order.

        :param settings_data: Settings data as a nested dictionary.
        :type settings_data: dict
        :param setting_path: Path tosite_alias write the TOML file.
        :type setting_path: str
        :return: None
        :rtype: None
        """

        path = Path(setting_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        current = SettingsManager.to_plain_dict(settings_data)
        ordered: dict = {}

        for group in self.SETTINGS_ORDER:
            ordered[group] = {}
            for key in self.SETTINGS_ORDER[group]:
                if group in current and key in current[group]:
                    ordered[group][key] = current[group][key]

        #unknown keys (not in SETTINGS_ORDER) are appended at the end
        for g, kv in current.items():
            if g not in ordered:
                ordered[g] = {}
            for k, v in kv.items():
                if k not in ordered[g]:
                    ordered[g][k] = v

        loaders.toml_loader.write(str(setting_path), ordered, merge=False)

    def settings_to_string(self, settings_data: Settings) -> str:
        """
        Convert settings to a TOML-like string, preserving order and formatting cleanly.
        """
        settings_dict = settings_data.model_dump()
        ordered_settings = {}

        for group in self.SETTINGS_ORDER:
            ordered_settings[group] = {}
            for key in self.SETTINGS_ORDER[group]:
                if key in settings_dict.get(group, {}):
                    ordered_settings[group][key] = settings_dict[group][key]

        def format_value(value):
            if isinstance(value, Path):
                return f'"{value}"'
            if isinstance(value, SecretStr):
                return '"**********"'
            if isinstance(value, str):
                return f'"{value}"'
            if isinstance(value, bool):
                return str(value).lower()
            return value

        lines = []
        for group, values in ordered_settings.items():
            lines.append(f"[{group}]")
            for key, value in values.items():
                value = format_value(value)
                lines.append(f"{key} = {value}")
            lines.append("")

        return "\n".join(lines)

    def edit_settings(self, project_name: str, editor="nano") -> None:
        """
        Open the specified project's settings file in a text editor for manual editing.

        After editing, settings are validated. If validation fails, the user can retry
        or restore the previous version.

        :param project_name: Name of the project to edit.
        :type project_name: str
        :param editor: Command-line editor to use (default: ``nano``).
        :type editor: str
        :raises ValueError: If the project does not exist.
        :raises RuntimeError: If the editor command fails.
        """

        settings_file = self.get_settings_path(project_name)
        if not settings_file.exists():
            raise ValueError(f"Project '{project_name}' not found")

        # Get editor command - try EDITOR env var first, then default editor

        # Detect default editor depending on OS

        if platform.system() == "Windows":
            default_editor = "notepad"
        else:
            default_editor = "nano"

        editor = os.environ.get("EDITOR") or default_editor

        # Make a temporary copy of the settings file
        temp_settings_file = settings_file.with_suffix(".tmp")
        temp_settings_file.write_text(settings_file.read_text())

        while True:
            # Open editor and wait for user to finish
            try:
                result = subprocess.run([editor, str(settings_file)], check=True)
                if result.returncode != 0:
                    raise RuntimeError(f"Editor {editor} exited with error")
            except subprocess.CalledProcessError as e:
                raise RuntimeError(f"Failed to open editor: {e}")

            try:
                # Try to load and validate the edited settings
                self.load_settings(project_name, validate=True)
                print("✓ Settings validated successfully!")
                # Clean up temporary file
                temp_settings_file.unlink(missing_ok=True)
                break
            except Exception as e:
                print(f"✕ Settings validation failed: {e}")
                retry = input("Would you like to retry editing? [y/n]: ").lower()
                if retry != "y":
                    # Restore original settings file
                    settings_file.write_text(temp_settings_file.read_text())
                    temp_settings_file.unlink(missing_ok=True)
                    print("Settings restored to original state.")
                    # Raise an error to indicate failure
                    raise ValueError("Settings validation failed")

    def get_param(self, project_name: str, param: str):
        """
        Retrieve the value of a specific configuration parameter.

        :param project_name: Name of the project.
        :type project_name: str
        :param param: Parameter key in the format ``SECTION.KEY``, e.g. ``GENERAL.host``.
        :type param: str
        :raises KeyError: If the parameter is not found.
        :return: Value of the requested parameter.
        :rtype: Any
        """
        settings = self.load_settings(project_name)

        try:
            section, key = param.split(".", 1)
        except ValueError:
            raise ValueError("Parameter must have format SECTION.KEY (e.g., GENERAL.host)")

        if not hasattr(settings, section):
            raise ValueError(f"Invalid section: {section}")

        section_model = getattr(settings, section)

        if not hasattr(section_model, key):
            raise ValueError(f"Invalid parameter: {param}")

        data = settings.model_dump()
        return (data[section][key])

    def set_param(self, project_name: str, param: str, value, validate: bool = True):
        """
        Assign a new value to a specific configuration parameter.

        :param project_name: Name of the project.
        :type project_name: str
        :param param: Parameter key in the format ``SECTION.KEY``, e.g. ``GENERAL.host``.
        :type param: str
        :param value: New value for the parameter.
        :type value: Any
        :param validate: Whether to validate the settings after updating. Default is ``True``.
        :type validate: bool
        :raises ValueError: If settings validation fails.
        """

        settings_file = self.get_settings_path(project_name)
        settings: Settings = self.load_settings(project_name)

        try:
            section, key = param.split(".", 1)
        except ValueError:
            raise ValueError("Parameter must have format SECTION.KEY (e.g., GENERAL.host)")

        if not hasattr(settings, section):
            raise ValueError(f"Invalid section: {section}")

        section_model = getattr(settings, section)

        if key not in section_model.model_fields:
            raise ValueError(f"Invalid parameter: {param}")

        field_info = section_model.model_fields[key]
        adapter = TypeAdapter(field_info.annotation)

        try:
            parsed_value = adapter.validate_python(value)
        except ValidationError as e:
            raise ValueError(f"Invalid value for {param}: {e}")

        new_section = section_model.model_copy(update={key: parsed_value})
        new_settings = settings.model_copy(update={section: new_section})

        if validate:
            try:
                new_settings = Settings.model_validate(new_settings.model_dump())
            except ValidationError as e:
                raise ValueError(f"Settings validation failed:\n{e}")

        # Guardamos en fichero
        self.export_settings(new_settings, settings_file)

        return new_settings

    @staticmethod
    def load_from_dict(settings: dict, validate: bool = True) -> Settings:
        """
        Load settings from a Python dictionary into a :class:`Settings` object.

        :param settings: Dictionary containing configuration keys and values.
        :type settings: dict
        :param validate: Whether to validate settings upon loading.
        :type validate: bool
        :return: A Seettings object populated with the provided settings.
        :rtype: Settings
        """

        return Settings.model_validate(settings) if validate else SettingsManager._construct_recursive(Settings,settings)

    @staticmethod
    def from_dict(data: dict, validate: bool = True) -> Settings:
        """
        Construye un Settings desde dict:
        - Si validate True usa model_validate (pydantic v2).
        - Si validate False usa model_construct (sin validar).
        """
        return SettingsManager.load_from_dict(data, validate)

    @staticmethod
    def to_plain_dict(settings: Settings, plain_secrets: bool = True) -> Any:
        """
        Convierte recursivamente BaseModel/SecretStr/Path/HttpUrl a tipos serializables (python).
        Usa model_dump(mode="python") para pydantic v2.
        """
        if isinstance(settings, SecretStr):
            return settings.get_secret_value() if plain_secrets else "**********"
        if isinstance(settings, (Path,)):
            return str(settings)
        if isinstance(settings, HttpUrl):
            return str(settings)
        if isinstance(settings, BaseModel):
            raw = settings.model_dump(mode="python")
            return {k: SettingsManager.to_plain_dict(v) for k, v in raw.items()}
        if isinstance(settings, dict):
            return {k: SettingsManager.to_plain_dict(v) for k, v in settings.items()}
        if isinstance(settings, list):
            return [SettingsManager.to_plain_dict(v) for v in settings]

        return settings

    @staticmethod
    def _generate_settings_order() -> Dict[str, List[str]]:
        """
        Generate settings order dictionary rely on root_model definition. This inspects the Settings model and its
        submodels to extract field order.
        """

        def _unwrap_model_from_annotation(ann):
            if ann is None:
                return None
            origin = get_origin(ann)
            if origin is Union:
                for a in get_args(ann):
                    if isinstance(a, type) and issubclass(a, BaseModel):
                        return a
            if isinstance(ann, type) and issubclass(ann, BaseModel):
                return ann
            return None

        order: Dict[str, List[str]] = {}
        annotations = getattr(Settings, "__annotations__", {})

        for top_name in list(annotations.keys()):
            ann = annotations.get(top_name)
            submodel = _unwrap_model_from_annotation(ann)
            if not submodel:
                # intentar fallback por atributos de Pydantic (por si no hay __annotations__)
                try:
                    # v2: model_fields preserves order
                    mf = getattr(Settings, "model_fields", None)
                    if mf and top_name in mf:
                        ann = mf[top_name].annotation if hasattr(mf[top_name], "annotation") else None
                        submodel = _unwrap_model_from_annotation(ann)
                except Exception:
                    pass

            if not submodel:
                continue

            # Obtener campos en orden según versión de Pydantic
            if hasattr(submodel, "model_fields"):  # Pydantic v2
                sub_keys = list(submodel.model_fields.keys())
            else:  # Pydantic v1
                sub_keys = list(getattr(submodel, "__fields__", {}).keys())

            order[top_name] = sub_keys

        return order

    def _default_template_file(self) -> Path:
        """
        Create a temporary TOML file with default settings.

        Returns
        -------

        """
        default_settings = Settings(
            LOGGER=LoggerSettings(
                loglevel=1,
                filename="",
            ),
            GENERAL=GeneralSettings(
                host=HttpUrl("https://wildintel-trap.uhu.es/"),
                login="user@example.com",
                password=SecretStr("secret"),
                project_id=123,
                verify_ssl=True,
                ffmpeg="ffmpeg",
                exiftool="exiftool",
                data_dir=Path.home(),
            ),
            WILDINTEL=WildIntelSettings(
                rp_name="WildINTEL",
                coverage="Doñana National Park",
                publisher="University of Huelva",
                owner="University of Huelva",
                tolerance_hours=1,
                resize_img=False,
                resize_img_size=[1024, 768],
                overwrite=False,
                output_dir=Path.home(),
            ),
            EPICOLLECT=EpiCollectSettings(
                client_id=0,
                client_secret="secret",
                app_slug="default",
            ),
        )

        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".toml") as tmp:
            tmp_path = Path(tmp.name)
            self.export_settings(default_settings, tmp_path)

        return tmp_path

    @staticmethod
    def _construct_recursive(model_cls: type[BaseModel], data: dict) -> BaseModel:
        """
        Construye un modelo usando model_construct() y aplicándolo recursivamente
        a submodelos (y listas de submodelos).
        """
        if data is None:
            return model_cls.model_construct()
        converted = {}
        mf = getattr(model_cls, "model_fields", {})
        for name, value in (data.items() if isinstance(data, dict) else []):
            field_info = mf.get(name)
            if field_info is None:
                converted[name] = value
                continue

            ann = getattr(field_info, "annotation", None)
            # detectar submodel directo
            sub = None
            origin = get_origin(ann)
            if origin is Union:
                for a in get_args(ann):
                    if isinstance(a, type) and issubclass(a, BaseModel):
                        sub = a
                        break
            elif isinstance(ann, type) and issubclass(ann, BaseModel):
                sub = ann

            # lista de submodelos: List[SubModel] or list[SubModel]
            if origin in (list, list.__class__) or getattr(ann, "__origin__", None) in (list,):
                args = get_args(ann)
                if args:
                    elem = args[0]
                    if isinstance(elem, type) and issubclass(elem, BaseModel) and isinstance(value, list):
                        converted[name] = [construct_recursive(elem, v) if isinstance(v, dict) else v for v in value]
                        continue

            if sub and isinstance(value, dict):
                converted[name] = construct_recursive(sub, value)
            else:
                converted[name] = value

        # pasar el resto de campos no presentes en data (si hace falta)
        return model_cls.model_construct(**converted)