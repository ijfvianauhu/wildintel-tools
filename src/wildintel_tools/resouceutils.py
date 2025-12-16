import hashlib
import io
import os
import string
import tempfile
from datetime import datetime
from enum import unique, Enum
from pathlib import Path
from typing import List, Dict, Optional
from zoneinfo import ZoneInfo
from datetime import timezone as datetime_timezone

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
    METADATA_EXIF_TAGS = [
        "DateTimeOriginal",
        "CreateDate",
        "FileModifyDate",
        "MIMEType",
        "ImageWidth",
        "ImageHeight",
        "ModifyDate",
        "Duration",
        "VideoFrameRate",
        "Make",
        "Model",
    ]

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
    def get_exif_from_path(
            file_path: Path,
            tags: Optional[List[str]] = None,
            all_tags: bool = False,
            extra_args: Optional[List[str]] = None,
    ) -> Dict:
        """Extract metadata from a local image/video file using the python-exiftool wrapper.

        Args:
            file_path: Path object pointing to a local file.
            tags: List of specific tags to extract. If None and all_tags=False, returns basic metadata.
            all_tags: If True, extract ALL available tags (slower).
            extra_args: Additional raw ExifTool arguments (e.g. ["-G1"])

        Returns:
            Dict containing metadata from ExifTool.

        Raises:
            ExifToolError: If exiftool fails or returns invalid data.
            ValueError: If the file does not exist or path is invalid.
        """

        # Validate path
        if not isinstance(file_path, Path):
            raise ValueError(f"Unsupported file type: {type(file_path)}")

        if not file_path.is_file():
            raise ValueError(f"File does not exist: {file_path}")

        try:
            # Build parameters
            params = ["-n", "-j"]  # numeric values

            if all_tags:
                params.append("-a")  # allow duplicate tags
            elif tags:
                # Convert ["DateTimeOriginal", "Model"] → ["-DateTimeOriginal", "-Model"]
                params.extend([f"-{t}" for t in tags])

            # Extra arguments
            if extra_args:
                params.extend(extra_args)

            # Extract metadata
            with exiftool.ExifToolHelper() as et:
                results = et.get_metadata(str(file_path), params=params)

            if not results or not isinstance(results, list):
                raise Exception("ExifTool returned empty or invalid metadata structure")

            metadata = results[0].copy()

            # Clean up internal fields
            metadata.pop("SourceFile", None)
            metadata.pop("ExifToolVersion", None)

            return metadata
        except Exception as e:
            raise Exception(f"Metadata extraction failed for {file_path}: {e}")

    @staticmethod
    def add_metadata(images: List[Path], xmp_info: dict) -> bytes:
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
    def add_xmp_metadata(image_bytes: bytes, resource) -> bytes:
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

    @staticmethod
    def file_to_bytes(img_path: Path, valid_types: Enum = None) -> io.BytesIO:
        return (io.BytesIO(img_path.read_bytes()))

    @staticmethod
    def file_to_image(img_path: Path, valid_types: Enum = None) -> Image:
        return Image.open(io.BytesIO(img_path.read_bytes()))

    @staticmethod
    def image_to_bytes(pil_image: Image.Image, format: str = "JPEG") -> bytes:
        """
        Convert a PIL image to raw bytes.

        :param pil_image: The PIL Image object to convert.
        :type pil_image: Image.Image
        :param format: The output image format (e.g. "JPEG", "PNG").
                       Defaults to "JPEG".
        :type format: str
        :return: The image encoded as bytes.
        :rtype: bytes
        """
        buffer = io.BytesIO()
        pil_image.save(buffer, format=format)
        buffer.seek(0)
        return buffer.getvalue()

    @staticmethod
    def get_camera_model(metadata: Dict[str, str]) -> str:
        """Get deployment camera model based on extracted metadata."""
        camera_model = "(unknown) (unknown)"
        make = metadata.get("EXIF:Make")
        model = metadata.get("EXIF:Model")
        if make:
            make = make.strip().lower()
            if not model:
                model = "(unknown)"
            else:
                model = model.strip().lower()
            # Remove redundant make from model if present
            if model.startswith(make):
                camera_model = model
            else:
                camera_model = f"{make} {model}"
        return camera_model

    @staticmethod
    def parse_date_recorded(
            metadata: Dict,
            timezone: ZoneInfo,
            fallback: bool = True,
            ignore_dst: bool = False,
            convert_to_utc: bool = True,
    ) -> datetime:
        """
        Parse date recorded from metadata.
        Args:
            metadata: Metadata dictionary extracted from the resource
            fallback: Fallback to the last modified time if no valid date recorded found.
        Returns:
            Parsed date recorded as a naive datetime object in UTC timezone
        Raises:
            ValueError: If no valid date recorded found and no fallback provided
        """
        nodata_values = ["0000:00:00 00:00:00"]

        def localize_datetime_dst(
                dt: datetime, timezone: ZoneInfo, ignore_dst: bool = False
        ) -> datetime:
            """Convert naive datetime to a specific timezone optionally ignoring DST transitions.

            Args:
                dt: A naive or aware datetime object
                timezone: The target timezone as a ZoneInfo object

            Returns:
                datetime: A timezone-aware datetime in the target timezone,
                        using the standard (non-DST) offset
            """
            if not isinstance(timezone, ZoneInfo):
                raise TypeError(f"timezone must be a ZoneInfo object, got {type(timezone)}")

            if ignore_dst:
                # Get the total UTC offset and DST offset
                utc_offset = timezone.utcoffset(dt)
                dst_offset = timezone.dst(dt)

                if utc_offset is None or dst_offset is None:
                    raise ValueError(f"Invalid timezone information for {timezone}")

                # Calculate the standard offset by subtracting DST
                standard_offset = utc_offset - dst_offset

                # Attach the standard offset
                dt = dt.replace(tzinfo=datetime_timezone(standard_offset))
            else:
                dt = dt.replace(tzinfo=timezone)

            return dt

        UTC = ZoneInfo("UTC")
        # first try to get "DateTimeOriginal" and parse it
        date_recorded = metadata.get("EXIF:DateTimeOriginal")
        if not date_recorded or date_recorded in nodata_values:
            # if not found, try "CreateDate"
            date_recorded = metadata.get("EXIF:CreateDate")
            if not date_recorded or date_recorded in nodata_values:
                if fallback:
                    date_recorded = metadata.get("EXIF:FileModifyDate")
                else:
                    # can not find any date recorded tag
                    raise ValueError(
                        "No valid date recorded found in metadata and no fallback provided"
                    )

        # parse date_recorded to datetime
        # Try multiple possible datetime formats
        formats = [
            "%Y:%m:%d %H:%M:%S",  # EXIF standard
            "%Y:%m:%d %H:%M:%S%z",  # EXIF standard with timezone
        ]
        for fmt in formats:
            try:
                date_recorded = datetime.strptime(date_recorded, fmt)
                break
            except ValueError:
                continue
        else:
            raise ValueError(f"Invalid date recorded format: {date_recorded}")

        # If the datetime is naive (no timezone info), attach the specified timezone
        if date_recorded.tzinfo is None:
            date_recorded = localize_datetime_dst(
                date_recorded, timezone=timezone, ignore_dst=ignore_dst
            )

        if convert_to_utc:
            date_recorded = date_recorded.astimezone(UTC)

        return date_recorded
