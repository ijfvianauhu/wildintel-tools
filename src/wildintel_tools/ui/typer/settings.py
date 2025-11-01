"""
Settings management module.

This module provides functionality to manage project-specific configuration files
based on the `Dynaconf` library. It includes utilities for:

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
import subprocess
from pathlib import Path
from typing import List, Optional

from dynaconf import Dynaconf
from dynaconf import loaders
from dynaconf.validator import Validator


SETTINGS_ORDER = {
    "LOGGER": ["loglevel", "filename"],
    "GENERAL": [
        "host", "login", "password", "project_id", "verify_ssl",
        "ffmpeg", "exiftool", "data_dir",
    ],
    "WILDINTEL": [
        "rp_name", "coverage", "publisher", "owner", "tolerance_hours",
        "resize_img", "resize_img_size", "overwrite", "output_dir",
    ],
}

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
        """
        Load settings from a Python dictionary into a :class:`Dynaconf` object.

        :param settings: Dictionary containing configuration keys and values.
        :type settings: dict
        :return: A Dynaconf object populated with the provided settings.
        :rtype: Dynaconf
        """
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

    def get_validators(self) -> List[Validator]:
        """
        Define and return Dynaconf validators for settings integrity checks.

        :return: A list of :class:`dynaconf.validator.Validator` objects.
        :rtype: List[Validator]
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
        """
        Export the given settings dictionary to a TOML file, preserving key order.

        :param settings_data: Settings data as a nested dictionary.
        :type settings_data: dict
        :param setting_path: Path to write the TOML file.
        :type setting_path: str
        :return: None
        :rtype: None
        """
        # Restore the original settings order as Dynaconf does not guarantee order
        settings_dict = {}
        for group in SETTINGS_ORDER:
            settings_dict[group] = {}
            for key in SETTINGS_ORDER[group]:
                settings_dict[group][key] = settings_data[group][key]

        loaders.toml_loader.write(str(setting_path), settings_dict, merge=False)

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
        # Usamos getattr de Dynaconf
        value = settings.get(param)
        if value is None:
            raise KeyError(f"Parameter '{param}' not found in project '{project_name}'")
        return value

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
        settings = self.load_settings(project_name)

        # Actualizamos el valor
        settings.update({param: value}, validate=False)  # no validar aún
        # Guardamos cambios en el fichero
        self.export_settings(settings.to_dict(), settings_file)

        if validate:
            # Validamos usando los validators registrados
            settings.validators.validate()