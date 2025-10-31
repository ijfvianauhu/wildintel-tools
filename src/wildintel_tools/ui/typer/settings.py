"""Settings management for trapper-tools."""

import os
import subprocess
from pathlib import Path
from typing import List, Optional

from dynaconf import Dynaconf
from dynaconf import loaders
from dynaconf.validator import Validator

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

def is_valid_timezone(tz_str):
    try:
        ZoneInfo(tz_str)
        return True
    except ZoneInfoNotFoundError:
        return False

SETTINGS_ORDER = {
    "LOGGER": [
        "loglevel",
        "filename",
    ],

    "GENERAL": [
        "host",
        "login",
        "password",
        "project_id",
        "verify_ssl",
        "ffmpeg",
        "exiftool",
        "data_dir",
    ],

    "WILDINTEL": [
        "rp_name",
        "coverage",
        "publisher",
        "owner",
        "tolerance_hours",
        "resize_img",
        "resize_img_size",
        "overwrite",
        "output_dir"
    ],
}


class SettingsManager:
    """Manage trapper-tools settings across different projects.

    This class handles:
    - Loading settings from TOML files
    - Creating new project settings from template
    - Managing multiple project configurations
    - Loading environment variables
    """

    def __init__(self, settings_dir: Optional[Path] = None):
        """Initialize settings manager.

        Args:
            settings_dir: Directory to store settings files. Defaults to ~/.trapper-tools
        """
        self.settings_dir = (
            Path(settings_dir) if settings_dir else Path.home() / ".trapper-tools"
        )
        self.settings_dir.mkdir(parents=True, exist_ok=True)

        # Path to default settings template in package
        self.default_template = Path(__file__).parent / "default_settings.toml"

    def create_project_settings(
        self,
        project_name: str,
        template: Optional[Path] = None,
        env_file: bool = False,
    ) -> Path:
        """Create new project settings from template.

        Args:
            project_name: Name of the project/environment
            template: Optional custom template file path
            env_file: Load .env file with environment variables using Dynaconf

        Returns:
            Path to the created settings file

        Raises:
            FileNotFoundError: If template doesn't exist
        """
        settings_file = self.settings_dir / f"{project_name}.toml"
        template = template or self.default_template

        if not template.exists():
            raise FileNotFoundError(f"Settings template not found: {template}")

        settings = Dynaconf(
            settings_files=[str(template)],
            load_dotenv=env_file,  # Load environment variables
            envvar_prefix=False,
            ignore_unknown_envvars=True,
            validate_on_update="all",
        )

        # Save settings back to file
        self.export_settings(settings.to_dict(), settings_file)

        return settings_file

    @staticmethod
    def load_from_array(settings:dict) -> Dynaconf:
        settings_dyn = Dynaconf(environments=False, settings_files=None)

        for k, v in settings.items():
            setattr(settings_dyn, k, v)
        return settings_dyn

    def load_settings(
        self,
        project_name: str,
        validate: bool = False,
        create:bool = True,
    ) -> Dynaconf:
        """Load settings for a specific project.

        Args:
            project_name: Name of the project
            validate: Validate settings

        Returns:
            Dynaconf settings object
        """
        settings_file = self.settings_dir / f"{project_name}.toml"
        if not settings_file.exists() and create:
            settings_file = self.create_project_settings(project_name)
        elif not settings_file.exists():
           raise FileNotFoundError(f"Settings file not found: {settings_file}")

        settings_files = [str(settings_file)]
        settings = Dynaconf(settings_files=settings_files)

        # get validators
        validators = self.get_validators()

        # Register validators
        settings.validators.register(*validators)

        if validate:
            # Validate settings
            settings.validators.validate()

        return settings

    def list_projects(self) -> list[str]:
        """List all available project settings.

        Returns:
            List of project names (without .toml extension)
        """
        return [f.stem for f in self.settings_dir.glob("*.toml")]

    def get_settings_path(self, project_name: str) -> Path:
        """Get path to a project's settings file.

        Args:
            project_name: Name of the project/environment

        Returns:
            Path to the settings file
        """
        return self.settings_dir / f"{project_name}.toml"

    def get_validators(self) -> List[Validator]:
        """
        Get DynaConf validators.
        """
        validators = [
            # LOGGER section
            Validator(
                "LOGGER.loglevel",
                must_exist=True,
                condition=lambda v: isinstance(v, int) and 0 <= v <= 2,
                messages={
                    "condition": "LOGGER.loglevel must be an integer between 0 and 2"
                },
            ),

            Validator(
                "LOGGER.filename",
                must_exist=True,
                condition=lambda v: (
                        isinstance(v, str)
                        and (
                                v.strip() == "" or v.strip().endswith(".log")
                        )
                ),
                messages={
                    "condition": "LOGGER.filename must be an empty string or a non-empty string ending with '.log'",
                },
            ),

            # GENERAL section
            Validator(
                "GENERAL.host",
                must_exist=True,
                cast=str,
                condition=lambda v: v.startswith("http://") or v.startswith("https://"),
                messages={"condition": "GENERAL.host must be a valid URL"},
            ),
            Validator(
                "GENERAL.login",  # must be an email-like string
                must_exist=True,
                cast=str,
                condition=lambda v: "@" in v and "." in v.split("@")[-1],
                messages={"condition": "GENERAL.login must be a valid email address."},
            ),
            Validator("GENERAL.project_id", must_exist=True, is_type_of=int, gte=1),
            Validator("GENERAL.verify_ssl", is_type_of=bool),
            Validator("GENERAL.ffmpeg", must_exist=True, cast=str, cont="ffmpeg"),
            Validator("GENERAL.exiftool", must_exist=True, cast=str, cont="exiftool"),
            Validator(
                "GENERAL.data_dir",
                condition=lambda value: not value or Path(value).is_dir(),
                must_exist=True,
                messages={
                    "condition": "The path specified in GENERAL.data_dir must be an existing directory."
                },
            ),
            Validator(
                "WILDINTEL.output_dir",
                condition=lambda value: Path(value).is_dir(),
                must_exist=True,
                messages={
                    "condition": "The path specified in WILDINTEL.output_dir must be an existing directory."
                },
            ),
        ]
        return validators

    def export_settings(self, settings_data: dict, setting_path: str) -> None:
        """Export settings to a file."""
        # Restore the original settings order as Dynaconf does not guarantee order
        settings_dict = {}
        for group in SETTINGS_ORDER:
            settings_dict[group] = {}
            for key in SETTINGS_ORDER[group]:
                settings_dict[group][key] = settings_data[group][key]

        loaders.toml_loader.write(str(setting_path), settings_dict, merge=False)

    def edit_settings(self, project_name: str, editor="nano") -> None:
        """Open settings in the default command line editor.

        This method will:
        1. Open the settings file in the system's default editor (from EDITOR env var)
        2. Wait for the user to make changes and exit the editor
        3. Validate the settings after changes
        4. If validation fails, show errors and ask to retry editing

        Args:
            project_name: Name of the project to edit settings for
            editor: Command line editor to use (default is 'nano')

        Raises:
            ValueError: If project doesn't exist
            RuntimeError: If no suitable editor is found
        """
        settings_file = self.get_settings_path(project_name)
        if not settings_file.exists():
            raise ValueError(f"Project '{project_name}' not found")

        # Get editor command - try EDITOR env var first, then default editor
        editor = os.environ.get("EDITOR") or editor

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
        Obtener el valor de un parámetro específico.

        Args:
            project_name: Nombre del proyecto
            param: Nombre del parámetro con formato 'SECCION.CLAVE', ej. 'GENERAL.host'

        Returns:
            Valor del parámetro
        """
        settings = self.load_settings(project_name)
        # Usamos getattr de Dynaconf
        value = settings.get(param)
        if value is None:
            raise KeyError(f"Parameter '{param}' not found in project '{project_name}'")
        return value

    def set_param(self, project_name: str, param: str, value, validate: bool = True):
        """
        Asignar un valor a un parámetro específico.

        Args:
            project_name: Nombre del proyecto
            param: Nombre del parámetro con formato 'SECCION.CLAVE', ej. 'GENERAL.host'
            value: Nuevo valor para el parámetro
            validate: Validar los settings después de asignar (por defecto True)

        Raises:
            ValueError: Si la validación falla
        """
        settings_file = self.get_settings_path(project_name)
        settings = self.load_settings(project_name)

        # Actualizamos el valor
        settings.update({param: value}, validate=False)  # no validar aún
        # Guardamos cambios en el fichero
        self.export_settings(settings.to_dict(), settings_file)

        if validate:
            # Validamos usando los validators registrados
            settings.validators.validate()