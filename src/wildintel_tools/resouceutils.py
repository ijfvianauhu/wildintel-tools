import hashlib
import io
import os
import string
import tempfile
from datetime import datetime
from enum import unique, Enum
from pathlib import Path
from typing import List

import exiftool
import filetype
from PIL import Image, ExifTags

@unique
class ResourceMymeTypeDTO(Enum):
    image_png = "image/png"
    image_jpeg = "image/jpeg"
    image_gig = "image/gif"
    image_webp = "image/webp"
    video_mp4 = "video/mp4"
    video_mpeg = "video/mpeg"
    video_quicktime = "video/quicktime"
    video_x_msvideo = "video/x-msvideo"

    def __str__(self):
        return self.value

@unique
class ResourceExtensionDTO(Enum):
    png = ".png"
    jpg = ".jpg"
    jpeg = ".jpeg"
    gif = ".gif"
    webp = ".webp"
    mp4 = ".mp4"
    mpeg = ".mpeg"
    mov = ".mov"
    avi = ".avi"

    def __str__(self):
        return self.value

class ResourceEntityDTO():
    contenthash : str
    pathnamehash : str
    filesize : int
    mimetype : ResourceMymeTypeDTO
    filename: str
    content: bytes
    recordered_at: datetime
    deployment_id: string
    sortorder: int | None = None
    content: bytes | None = None


class ResourceUtils:
    @staticmethod
    def calculate_hash(content: bytes) -> tuple[str, str]:
        """Calculates the SHA-1 hash of the given content and returns the hash and its path.

        Args:
            content: Bytes content to hash

        Returns:
            Tuple containing (hash_string, hash_path) where:
            - hash_string: SHA-1 hex digest of the content
            - hash_path: Path structure based on the hash (format: /XX/YY/XXXX...)
        """
        hash_obj = hashlib.sha1(content)
        contenthash: str = hash_obj.hexdigest()
        contentpath: str = f"/{contenthash[:2]}/{contenthash[2:4]}/{contenthash}"
        return (contenthash, contentpath)

    @staticmethod
    def hash_image_pixel_data(raw_bytes: bytes) -> tuple[str, str]:
        """Calculates the SHA-1 hash of the pixel data of an image from raw bytes.

        Args:
            raw_bytes: Image file in bytes format

        Returns:
            Tuple with (hash_string, hash_path) of the pixel data
        """
        img = Image.open(io.BytesIO(raw_bytes)).convert('RGB')
        data = img.tobytes()
        return ResourceUtils.calculate_hash(data)

    @staticmethod
    def get_exif_from_bytes(image_bytes: bytes) -> dict:
        """Extracts EXIF data from image bytes.

        Args:
            image_bytes: Image file in bytes format

        Returns:
            Dictionary containing all EXIF tags found in the image
        """
        image = Image.open(io.BytesIO(image_bytes))
        exif_data = image.getexif()
        return {
            ExifTags.TAGS.get(tag_id, tag_id): value
            for tag_id, value in exif_data.items()
            if tag_id in exif_data
        }

    @staticmethod
    def get_exif_tag(image_bytes: bytes, tag_name_to_find: str):
        """Gets a specific EXIF tag from image bytes.

        Args:
            image_bytes: Image file in bytes format
            tag_name_to_find: Name of the EXIF tag to retrieve

        Returns:
            Value of the requested EXIF tag, or None if not found
        """
        exif_data = ResourceUtils.get_exif_from_bytes(image_bytes)
        return exif_data.get(tag_name_to_find)  # Simplified with .get()

    @staticmethod
    def normalize_jpeg(image_bytes: bytes) -> bytes:
        """Ensure JPEG is valid and compatible with XMP writing."""
        img = Image.open(io.BytesIO(image_bytes))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        return buf.getvalue()

    @staticmethod
    def add_xmp_dublin_core(image_bytes: bytes):
        pass

    @staticmethod
    def add_xmp_metadata(images: List[Path], xmp_info:dict) -> bytes:
        """Adds metadata to an image file using ExifTool.

        Args:
            image_bytes: Original image in bytes format
            resource: Resource object containing metadata to add

        Returns:
            New image bytes with added metadata
        """


        try:

            # Escribir metadatos con ExifTool
            with exiftool.ExifToolHelper() as et:
                et.set_tags(images, tags=xmp_info, params=["-overwrite_original"])

        except Exception as e:
            raise e

        return None

    @staticmethod
    def add_metadata(image_bytes: bytes, resource) -> bytes:
        """Adds metadata to an image file using ExifTool.

        Args:
            image_bytes: Original image in bytes format
            resource: Resource object containing metadata to add

        Returns:
            New image bytes with added metadata
        """

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
            tmp_file.write(image_bytes)
            tmp_file.flush()
            tmp_file_path = tmp_file.name

        try:
            make = ResourceUtils.get_exif_tag(image_bytes, "Make")
            model = ResourceUtils.get_exif_tag(image_bytes, "Model")
            location = resource.deployment.location
            owner = resource.deployment.owner
            publisher = resource.deployment.publisher

            resource_dc_creator = f"CT ({make} {model} {location.name})" if make and model else f"CT (Unknown Make and Model) {location.name}"
            where = location.description if location.description else "Unknown Location"
            resource_photoshop_AuthorsPosition = f"This image was taken in {where}, as part of the WildINTEL project. https://wildintel.eu/"
            year = datetime.datetime.now().year
            resource_dc_rights = f"© {owner}, {year}. All rights reserved."
            resource_xmpRights_Marked = True
            resource_xmpRights_WebStatement = "https://creativecommons.org/licenses/by/4.0/"

            # Creamos el diccionario de etiquetas XMP
            # tags = {
            # Dublin Core
            #    "XMP-dc:Creator": resource.dc_creator,
            #    "XMP-dc:Date": resource.recordered_at.isoformat(),
            #    "XMP-dc:Format": resource.mimetype,
            #    "XMP-dc:Identifier": f"WildINTEL:{resource.contenthash}",
            #    "XMP-dc:Source": f"WildINTEL:{resource.parentcontenthash}",
            #    "XMP-dc:Publisher": publisher,
            #    "XMP-dc:Rights": resource.dc_rights,
            #    "XMP-dc:Coverage": resource.photoshop_AuthorsPosition,

            # XMP Rights
            #    "XMP-xmpRights:Marked": str(resource.xmpRights_Marked).lower(),
            #    "XMP-xmpRights:Owner": owner,
            #    "XMP-xmpRights:WebStatement": resource.xmpRights_WebStatement,
            # }

            tags = {
                # Dublin Core
                "XMP-dc:Creator": resource_dc_creator,
                "XMP-dc:Date": resource.recordered_at.isoformat(),
                "XMP-dc:Format": resource.mimetype,
                "XMP-dc:Identifier": f"WildINTEL:{resource.contenthash}",
                "XMP-dc:Source": f"WildINTEL:{resource.parentcontenthash}",
                "XMP-dc:Publisher": publisher,
                "XMP-dc:Rights": resource_dc_rights,
                "XMP-dc:Coverage": resource_photoshop_AuthorsPosition,

                # XMP Rights
                "XMP-xmpRights:Marked": str(resource_xmpRights_Marked).lower(),
                "XMP-xmpRights:Owner": owner,
                "XMP-xmpRights:WebStatement": resource_xmpRights_WebStatement,
            }

            # Escribir metadatos con ExifTool
            with exiftool.ExifToolHelper() as et:
                et.set_tags([tmp_file_path], tags=tags, params=["-overwrite_original"])

            # Leer el archivo con metadatos actualizados
            with open(tmp_file_path, "rb") as f:
                updated_bytes = f.read()

        finally:
            os.remove(tmp_file_path)

        return updated_bytes

    @staticmethod
    def resize(img: Image.Image, basewidth: int = 2400) -> tuple[bool, Image.Image]:
        """Resizes an image while maintaining aspect ratio.

        Args:
            img: PIL Image object
            basewidth: Target width in pixels

        Returns:
            Tuple of (error_flag, resized_image) where:
            - error_flag: True if resize failed, False otherwise
            - resized_image: Resized PIL Image object or None if failed
        """
        try:
            wpercent = (basewidth / float(img.size[0]))
            hsize = int((float(img.size[1]) * float(wpercent)))
            img_new = img.resize((basewidth, hsize), Image.LANCZOS)
            return (False, img_new)
        except Exception:
            return (True, None)

    @staticmethod
    # def validate_mime_type(image_bytes: bytes) -> tuple[bool, str]:
    #    mime = magic.Magic(mime=True)
    #    detected_type = mime.from_buffer(image_bytes)

    # Verificar si el tipo detectado es permitido
    #    if detected_type not in {mime.value for mime in ResourceMymeTypeDTO}:
    #        return False, detected_type
    #    return True, detected_type

    @staticmethod
    def validate_mime_type(image_bytes: bytes, valid_types: Enum = None) -> tuple[bool, str]:
        if valid_types == None:
            valid_types = ResourceMymeTypeDTO

        detected_type = ResourceUtils.get_mime_type(image_bytes)

        if detected_type not in {mime.value for mime in valid_types}:
            return False, detected_type
        return True, detected_type

    @staticmethod
    def get_mime_type(image_bytes: bytes) -> str:
        kind = filetype.guess(image_bytes)

        if kind is None:
            detected_type = "application/octet-stream"
        else:
            detected_type = kind.mime

        return detected_type
