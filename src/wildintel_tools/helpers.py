"""
Utility functions for validating external dependencies and connecting to the Trapper API.

This module provides helper routines to:
    - Verify the availability of external tools such as FFMPEG and ExifTool.
    - Check connectivity to a Trapper server instance.
    - Retrieve Trapper resources such as classification projects, research projects, and locations.

These functions are mainly intended for diagnostic or setup purposes before executing
more complex workflows that depend on these tools or services.

Example:
    .. code-block:: python

        from wildintel_tools.utils import (
            check_ffmpeg, check_exiftool,
            check_trapper_connection, get_trapper_classification_projects
        )

        check_ffmpeg("/usr/bin/ffmpeg")
        check_exiftool("/usr/bin/exiftool")

        check_trapper_connection(
            base_url="https://trapper.example.org",
            user_name="user@example.com",
            user_password="mypassword",
            access_token=None
        )

        projects = get_trapper_classification_projects(
            base_url="https://trapper.example.org",
            user_name="user@example.com",
            user_password="mypassword",
            access_token=None
        )
        print(projects)
"""

import logging
import subprocess
from trapper_client.TrapperClient import TrapperClient

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Various utility functions
# --------------------------------------------------------------------------- #

def check_ffmpeg(ffmpeg_path: str):
    """
    Checks if the FFMPEG executable is available and functional.

    :param ffmpeg_path: Path to the FFMPEG executable.
    :type ffmpeg_path: str
    :raises Exception: If the executable is not available or fails to respond.
    :return: None
    :rtype: None
    """
    try:
        p = subprocess.Popen(
            [ffmpeg_path, "-h"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        out, error = p.communicate()
        logger.info(
            "FFMPEG available: {v}".format(v=error.split(b"\n")[0].decode("utf-8"))
        )
    except Exception as e:
        logger.warning(f"FFMPEG not available: {e}")
        raise e

def check_exiftool(exiftool_path: str):
    """
    Checks if the ExifTool executable is available and retrieves its version.

    :param exiftool_path: Path to the ExifTool executable.
    :type exiftool_path: str
    :raises Exception: If ExifTool is not available or the version command fails.
    :return: None
    :rtype: None
    """
    try:
        p = subprocess.Popen(
            [exiftool_path, "-ver"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        out, error = p.communicate()
        logger.info(f"EXIFTOOL available: version {out.decode('utf-8')}")
    except Exception as e:
        logger.warning(f"exiftool not available: {e}")
        raise e

def check_trapper_connection(base_url:str, user_name:str, user_password: str, access_token: str):
    """
    Verifies the connection to the Trapper API using the provided credentials.

    :param base_url: Base URL of the Trapper API.
    :type base_url: str
    :param user_name: Username or email used for authentication.
    :type user_name: str
    :param user_password: User password for authentication.
    :type user_password: str
    :param access_token: Optional API access token (can be ``None``).
    :type access_token: str
    :raises Exception: If the connection fails or authentication is invalid.
    :return: None
    :rtype: None
    """
    try:
        trapper_client = TrapperClient(
            base_url=base_url,
            user_name=user_name,
            user_password=user_password,
            access_token=access_token
        )

        trapper_client.classification_projects.get_all()
    except Exception as e:
        msg = f"Failed to connect to Trapper API. Check your settings: {str(e)}"
        logger.error(msg)
        raise Exception(msg)

def get_trapper_classification_projects(base_url:str, user_name:str, user_password: str, access_token: str):
    """
    Retrieves all classification projects from the Trapper API.

    :param base_url: Base URL of the Trapper API.
    :type base_url: str
    :param user_name: Username or email used for authentication.
    :type user_name: str
    :param user_password: User password for authentication.
    :type user_password: str
    :param access_token: Optional API access token (can be ``None``).
    :type access_token: str
    :return: List of classification project objects retrieved from the API.
    :rtype: list
    :raises Exception: If the request fails due to connection or authentication errors.
    """
    trapper_client = TrapperClient(
        base_url=base_url,
        user_name=user_name,
        user_password=user_password,
        access_token=access_token
    )

    return trapper_client.classification_projects.get_all()

def get_trapper_research_projects(base_url:str, user_name:str, user_password: str, access_token: str):
    """
    Retrieves all research projects from the Trapper API.

    :param base_url: Base URL of the Trapper API.
    :type base_url: str
    :param user_name: Username or email used for authentication.
    :type user_name: str
    :param user_password: User password for authentication.
    :type user_password: str
    :param access_token: Optional API access token (can be ``None``).
    :type access_token: str
    :return: List of research project objects retrieved from the API.
    :rtype: list
    :raises Exception: If the request fails due to connection or authentication errors.
    """
    trapper_client = TrapperClient(
        base_url=base_url,
        user_name=user_name,
        user_password=user_password,
        access_token=access_token
    )

    return trapper_client.research_projects.get_all()

def get_trapper_locations(base_url:str, user_name:str, user_password: str, access_token: str):
    """
    Retrieves all locations from the Trapper API.

    :param base_url: Base URL of the Trapper API.
    :type base_url: str
    :param user_name: Username or email used for authentication.
    :type user_name: str
    :param user_password: User password for authentication.
    :type user_password: str
    :param access_token: Optional API access token (can be ``None``).
    :type access_token: str
    :return: List of location objects retrieved from the API.
    :rtype: list
    :raises Exception: If the request fails due to connection or authentication errors.
    """
    trapper_client = TrapperClient(
        base_url=base_url,
        user_name=user_name,
        user_password=user_password,
        access_token=access_token
    )

    return trapper_client.locations.get_all()

def get_trapper_deployments(base_url:str, user_name:str, user_password: str, access_token: str):
    """
    Retrieves all deployments from the Trapper API.

    :param base_url: Base URL of the Trapper API.
    :type base_url: str
    :param user_name: Username or email used for authentication.
    :type user_name: str
    :param user_password: User password for authentication.
    :type user_password: str
    :param access_token: Optional API access token (can be ``None``).
    :type access_token: str
    :return: List of location objects retrieved from the API.
    :rtype: list
    :raises Exception: If the request fails due to connection or authentication errors.
    """
    trapper_client = TrapperClient(
        base_url=base_url,
        user_name=user_name,
        user_password=user_password,
        access_token=access_token
    )

    return trapper_client.deployments.get_all()