import os
import platform
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Dict, get_origin, Union, get_args, Any

from dynaconf import Dynaconf
from dynaconf import loaders
from pydantic import BaseModel, SecretStr, TypeAdapter, ValidationError, HttpUrl

from wildintel_tools.ui.typer.settings import (
    DEFAULT_SETTINGS_DIR,
    Settings,
)


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
        self.settings_dir = Path(settings_dir) if settings_dir else DEFAULT_SETTINGS_DIR
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
        :param template: Optional custom template file path. Defaults to the internal template.
        :param env_file: Whether to load environment variables using Dynaconf.
        :param validate: Whether to validate settings upon loading.
        :raises FileNotFoundError: If the template file does not exist.
        :return: Path to the newly created settings file.
        """
        settings_file = self.settings_dir / f"{project_name}.toml"
        template = template or self._default_template_file()

        if not template.exists():
            raise FileNotFoundError(f"Settings template not found: {template}")

        settings = Dynaconf(
            settings_files=[str(template)],
            load_dotenv=env_file,
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
        create: bool = True,
    ) -> Settings:
        """
        Load settings for a given project.

        :param project_name: Name of the project.
        :param validate: Whether to validate settings upon loading.
        :param create: Automatically create settings file if it does not exist.
        :raises FileNotFoundError: If the settings file does not exist and creation is disabled.
        :return: A Settings object containing loaded settings.
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
        """List all available project configuration files."""
        return [f.stem for f in self.settings_dir.glob("*.toml")]

    def get_settings_path(self, project_name: str) -> Path:
        """Get the absolute path to a project's settings file."""
        return self.settings_dir / f"{project_name}.toml"

    def export_settings(self, settings_data: Settings, setting_path: Path) -> None:
        """Export the given settings to a TOML file, preserving key order."""
        path = Path(setting_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        current = SettingsManager.to_plain_dict(settings_data)
        ordered: dict = {}

        for group in self.SETTINGS_ORDER:
            ordered[group] = {}
            for key in self.SETTINGS_ORDER[group]:
                if group in current and key in current[group]:
                    ordered[group][key] = current[group][key]

        for g, kv in current.items():
            if g not in ordered:
                ordered[g] = {}
            for k, v in kv.items():
                if k not in ordered[g]:
                    ordered[g][k] = v

        loaders.toml_loader.write(str(setting_path), ordered, merge=False)

    def settings_to_string(self, settings_data: Settings) -> str:
        """Convert settings to a TOML-like string, preserving order."""
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
        :param editor: Command-line editor to use (default: ``nano``).
        :raises ValueError: If the project does not exist.
        :raises RuntimeError: If the editor command fails.
        """
        settings_file = self.get_settings_path(project_name)
        if not settings_file.exists():
            raise ValueError(f"Project '{project_name}' not found")

        if platform.system() == "Windows":
            default_editor = "notepad"
        else:
            default_editor = "nano"

        editor = os.environ.get("EDITOR") or default_editor

        temp_settings_file = settings_file.with_suffix(".tmp")
        temp_settings_file.write_text(settings_file.read_text())

        while True:
            try:
                result = subprocess.run([editor, str(settings_file)], check=True)
                if result.returncode != 0:
                    raise RuntimeError(f"Editor {editor} exited with error")
            except subprocess.CalledProcessError as e:
                raise RuntimeError(f"Failed to open editor: {e}")

            try:
                self.load_settings(project_name, validate=True)
                print("✓ Settings validated successfully!")
                temp_settings_file.unlink(missing_ok=True)
                break
            except Exception as e:
                print(f"✕ Settings validation failed: {e}")
                retry = input("Would you like to retry editing? [y/n]: ").lower()
                if retry != "y":
                    settings_file.write_text(temp_settings_file.read_text())
                    temp_settings_file.unlink(missing_ok=True)
                    print("Settings restored to original state.")
                    raise ValueError("Settings validation failed")

    def get_param(self, project_name: str, param: str):
        """
        Retrieve the value of a specific configuration parameter.

        :param project_name: Name of the project.
        :param param: Parameter key in the format ``SECTION.KEY``, e.g. ``GENERAL.host``.
        :raises KeyError: If the parameter is not found.
        """
        settings = self.load_settings(project_name)
        section, key = self._split_param(param)
        data = settings.model_dump()
        return data[section][key]

    def _split_param(self, param: str) -> tuple[str, str]:
        """Split SECTION.KEY into (section, key)."""
        try:
            section, key = param.split(".", 1)
        except ValueError:
            raise ValueError("Parameter must have format SECTION.KEY (e.g., GENERAL.host)")
        return section, key

    def _get_section_model(self, settings: Settings, section: str, key: str):
        if not hasattr(settings, section):
            raise ValueError(f"Invalid section: {section}")
        section_model = getattr(settings, section)
        if key not in section_model.model_fields:
            raise ValueError(f"Invalid parameter: {section}.{key}")
        return section_model

    def _parse_value(self, section_model: BaseModel, key: str, value: Any):
        field_info = section_model.model_fields[key]
        adapter = TypeAdapter(field_info.annotation)
        try:
            return adapter.validate_python(value)
        except ValidationError as e:
            raise ValueError(f"Invalid value for {section_model.__class__.__name__}.{key}: {e}")

    def set_value(self, project_name: str, section: str, key: str, value, validate: bool = True):
        """Set a single setting using explicit section/key arguments."""
        settings_file = self.get_settings_path(project_name)
        settings: Settings = self.load_settings(project_name)

        section_model = self._get_section_model(settings, section, key)
        parsed_value = self._parse_value(section_model, key, value)

        new_section = section_model.model_copy(update={key: parsed_value})
        new_settings = settings.model_copy(update={section: new_section})

        if validate:
            new_settings = Settings.model_validate(new_settings.model_dump())

        self.export_settings(new_settings, settings_file)
        return new_settings

    def set_param(self, project_name: str, param: str, value, validate: bool = True):
        """
        Assign a new value to a specific configuration parameter.

        :param param: Parameter key in the format ``SECTION.KEY``.
        """
        section, key = self._split_param(param)
        return self.set_value(project_name, section, key, value, validate)

    def update_settings(self, project_name: str, updates: Dict[str, Any], validate: bool = True) -> Settings:
        """Apply multiple updates in one pass. Keys must be in ``SECTION.KEY`` format."""
        settings_file = self.get_settings_path(project_name)
        settings: Settings = self.load_settings(project_name)
        new_settings = settings

        for param, value in updates.items():
            section, key = self._split_param(param)
            section_model = self._get_section_model(new_settings, section, key)
            parsed_value = self._parse_value(section_model, key, value)
            updated_section = section_model.model_copy(update={key: parsed_value})
            new_settings = new_settings.model_copy(update={section: updated_section})

        if validate:
            new_settings = Settings.model_validate(new_settings.model_dump())

        self.export_settings(new_settings, settings_file)
        return new_settings

    @staticmethod
    def load_from_dict(settings: dict, validate: bool = True) -> Settings:
        """Load settings from a Python dictionary into a :class:`Settings` object."""
        return Settings.model_validate(settings) if validate else SettingsManager._construct_recursive(Settings, settings)

    @staticmethod
    def from_dict(data: dict, validate: bool = True) -> Settings:
        return SettingsManager.load_from_dict(data, validate)

    @staticmethod
    def to_plain_dict(settings: Settings, plain_secrets: bool = True) -> Any:
        """Convert recursively BaseModel/SecretStr/Path/HttpUrl to serialisable Python types."""
        if isinstance(settings, SecretStr):
            return settings.get_secret_value() if plain_secrets else "**********"
        if isinstance(settings, Path):
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
        """Generate settings order dictionary from the Settings model field definitions."""

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
                try:
                    mf = getattr(Settings, "model_fields", None)
                    if mf and top_name in mf:
                        ann = mf[top_name].annotation if hasattr(mf[top_name], "annotation") else None
                        submodel = _unwrap_model_from_annotation(ann)
                except Exception:
                    pass

            if not submodel:
                continue

            if hasattr(submodel, "model_fields"):
                sub_keys = list(submodel.model_fields.keys())
            else:
                sub_keys = list(getattr(submodel, "__fields__", {}).keys())

            order[top_name] = sub_keys

        return order

    def _default_template_file(self) -> Path:
        """Create a temporary TOML file with default settings and return its path."""
        default_settings = Settings()
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".toml") as tmp:
            tmp_path = Path(tmp.name)
            self.export_settings(default_settings, tmp_path)
        return tmp_path

    @staticmethod
    def _construct_recursive(model_cls: type[BaseModel], data: dict) -> BaseModel:
        """Build a model using model_construct() applied recursively to sub-models."""
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
            sub = None
            origin = get_origin(ann)
            if origin is Union:
                for a in get_args(ann):
                    if isinstance(a, type) and issubclass(a, BaseModel):
                        sub = a
                        break
            elif isinstance(ann, type) and issubclass(ann, BaseModel):
                sub = ann

            if origin in (list, list.__class__) or getattr(ann, "__origin__", None) in (list,):
                args = get_args(ann)
                if args:
                    elem = args[0]
                    if isinstance(elem, type) and issubclass(elem, BaseModel) and isinstance(value, list):
                        converted[name] = [
                            SettingsManager._construct_recursive(elem, v) if isinstance(v, dict) else v
                            for v in value
                        ]
                        continue

            if sub and isinstance(value, dict):
                converted[name] = SettingsManager._construct_recursive(sub, value)
            else:
                converted[name] = value

        return model_cls.model_construct(**converted)
