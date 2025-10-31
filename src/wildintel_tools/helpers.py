import logging
import subprocess
from trapper_client.TrapperClient import TrapperClient

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Various utility functions
# --------------------------------------------------------------------------- #

def check_ffmpeg(ffmpeg_path: str):
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

    trapper_client = TrapperClient(
        base_url=base_url,
        user_name=user_name,
        user_password=user_password,
        access_token=access_token
    )

    return trapper_client.classification_projects.get_all()

def get_trapper_research_projects(base_url:str, user_name:str, user_password: str, access_token: str):

    trapper_client = TrapperClient(
        base_url=base_url,
        user_name=user_name,
        user_password=user_password,
        access_token=access_token
    )

    return trapper_client.research_projects.get_all()

def get_trapper_locations(base_url:str, user_name:str, user_password: str, access_token: str):

    trapper_client = TrapperClient(
        base_url=base_url,
        user_name=user_name,
        user_password=user_password,
        access_token=access_token
    )

    return trapper_client.locations.get_all()
