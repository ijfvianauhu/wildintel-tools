import os
import json
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable

import aiofiles
import httpx
from blake3 import blake3
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
from tqdm import tqdm

logger = logging.getLogger(__name__)

CHUNK_SIZE = 64 * 1024 * 1024  # 64 MB
READ_CHUNK_SIZE = 4 * 1024 * 1024  # 4 MB


class HTTPUploaderError(Exception):
    """Base exception for HTTP uploader errors."""

    pass


class HTTPUploader:
    """
    Async HTTP uploader with resumable chunk-based uploads.

    This uploader implements a robust, resumable file upload system using:
    - BLAKE3 hashing for integrity verification
    - Chunk-based uploads with configurable parallelism
    - Persistent metadata for resume support
    - Atomic file operations to prevent corruption
    - Thread-safe concurrent chunk uploads

    Compatible with the Django-FastAPI backend API.

    Example:
        >>> uploader = HTTPUploader(
        ...     server_url="https://example.com",
        ...     login="user",
        ...     password="pass"
        ... )
        >>> uploader.upload(Path("file.zip"), "/collections/file.zip")
    """

    def __init__(
        self,
        server_url: str,
        login: str,
        password: str,
        verify: bool = True,
        max_parallel: int = 4,
    ):
        """
        Initialize HTTP uploader.

        Args:
            server_url: Base URL of the server (e.g., 'https://example.com')
            login: Username for authentication
            password: Password for authentication
            verify: Whether to verify SSL certificates
            max_parallel: Maximum number of parallel chunk uploads
        """
        self.server = server_url.rstrip("/")
        self.login = login
        self.password = password
        self.verify = verify
        self.max_parallel = max_parallel
        self.session_id: Optional[str] = None
        self.meta: Dict[str, Any] = {}
        self.meta_path = ""
        self._meta_lock = asyncio.Lock()

    async def _login(self) -> str:
        """
        Authenticate with the server and obtain session ID.

        Returns:
            Session ID string

        Raises:
            HTTPUploaderError: If authentication fails
        """
        async with httpx.AsyncClient(verify=self.verify) as client:
            try:
                response = await client.post(
                    f"{self.server}/uploader/auth/login",
                    json={"username": self.login, "password": self.password},
                )
                response.raise_for_status()
                data = response.json()
                logger.info(f"Successfully authenticated as {data['username']}")
                return data["sessionid"]
            except httpx.HTTPStatusError as e:
                raise HTTPUploaderError(
                    f"Authentication failed: {e.response.status_code} - {e.response.text}"
                ) from e
            except Exception as e:
                raise HTTPUploaderError(f"Authentication error: {e}") from e

    async def _compute_hashes(self, path: str) -> tuple[str, List[str]]:
        """
        Compute full-file and per-chunk BLAKE3 hashes asynchronously.

        This method reads the file in chunks and computes:
        - A hash for the entire file (used for final verification)
        - Individual hashes for each chunk (used for per-chunk verification)

        Progress is displayed with a tqdm progress bar.

        Args:
            path: Path to the file

        Returns:
            Tuple of (file_hash, chunk_hashes) where file_hash is the BLAKE3
            hash of the entire file and chunk_hashes is a list of BLAKE3 hashes
            for each chunk
        """
        full_hasher = blake3()
        chunk_hashes = []
        total_size = os.path.getsize(path)
        total_chunks = (total_size + CHUNK_SIZE - 1) // CHUNK_SIZE

        logger.info(f"Computing hashes for {total_chunks} chunks...")

        # Create progress bar for hashing
        progress = tqdm(
            total=total_size,
            desc=f"[INFO] Hashing {Path(path).name}",
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
        )

        async with aiofiles.open(path, "rb") as f:
            for i in range(total_chunks):
                remaining = CHUNK_SIZE
                chunk_hasher = blake3()
                while remaining > 0:
                    buf = await f.read(min(READ_CHUNK_SIZE, remaining))
                    if not buf:
                        break
                    remaining -= len(buf)
                    full_hasher.update(buf)
                    chunk_hasher.update(buf)
                    progress.update(len(buf))
                chunk_hashes.append(chunk_hasher.hexdigest())

        progress.close()
        return full_hasher.hexdigest(), chunk_hashes

    async def _update_metadata(self, updater: Callable[[Dict[str, Any]], None]) -> None:
        """
        Thread-safe metadata update with atomic file write.

        This method ensures that all metadata updates are serialized using an asyncio lock
        and written atomically to disk to prevent corruption during concurrent access.

        Args:
            updater: Function that modifies the metadata dict in-place
        """
        async with self._meta_lock:
            updater(self.meta)
            tmp = self.meta_path + ".tmp"
            async with aiofiles.open(tmp, "w") as f:
                await f.write(json.dumps(self.meta, indent=2))
            await asyncio.to_thread(os.replace, tmp, self.meta_path)

    async def _create_metadata(
        self, file_path: Path, remote_path: str, file_hash: str, chunk_hashes: List[str]
    ) -> None:
        """
        Create and save fresh metadata for a new upload.

        Args:
            file_path: Local file path
            remote_path: Remote file path
            file_hash: BLAKE3 hash of the entire file
            chunk_hashes: List of BLAKE3 hashes for each chunk
        """

        def initialize_meta(meta: Dict[str, Any]) -> None:
            meta.clear()
            meta.update(
                {
                    "file": str(file_path),
                    "remote": remote_path,
                    "file_hash": file_hash,
                    "chunk_size": CHUNK_SIZE,
                    "total_chunks": len(chunk_hashes),
                    "chunk_hashes": chunk_hashes,
                    "completed": {},
                }
            )

        await self._update_metadata(initialize_meta)

    def _validate_metadata(self, file_path: Path, remote_path: str, size: int) -> bool:
        """
        Validate that existing metadata matches the current file and upload target.

        Args:
            file_path: Local file path
            remote_path: Remote file path
            size: File size in bytes

        Returns:
            True if metadata is valid, False otherwise
        """
        if self.meta.get("file") != str(file_path):
            return False
        if self.meta.get("remote") != remote_path:
            return False

        expected_size = sum(
            min(CHUNK_SIZE, size - i * CHUNK_SIZE)
            for i in range(self.meta.get("total_chunks", 0))
        )
        if size != expected_size:
            return False

        return True

    async def _load_or_create_metadata(
        self, file_path: Path, remote_path: str, size: int
    ) -> tuple[str, List[str]]:
        """
        Load existing metadata or create fresh metadata for the upload.

        If metadata exists but doesn't match the current file or target,
        it will be invalidated and recreated.

        Args:
            file_path: Local file path
            remote_path: Remote file path
            size: File size in bytes

        Returns:
            Tuple of (file_hash, chunk_hashes)
        """
        if os.path.exists(self.meta_path):
            logger.info(f"Loading existing upload metadata from {self.meta_path}")
            async with self._meta_lock:
                async with aiofiles.open(self.meta_path, "r") as f:
                    self.meta = json.loads(await f.read())

            if not self._validate_metadata(file_path, remote_path, size):
                logger.warning(
                    "Metadata mismatch detected (file changed or different target). "
                    "Recomputing hashes..."
                )
                os.remove(self.meta_path)
                file_hash, chunk_hashes = await self._compute_hashes(str(file_path))
                await self._create_metadata(
                    file_path, remote_path, file_hash, chunk_hashes
                )
            else:
                file_hash = self.meta["file_hash"]
                chunk_hashes = self.meta["chunk_hashes"]
        else:
            logger.info("Computing file and chunk hashes...")
            file_hash, chunk_hashes = await self._compute_hashes(str(file_path))
            await self._create_metadata(file_path, remote_path, file_hash, chunk_hashes)
            logger.info(f"Computed {len(chunk_hashes)} chunk hashes")

        return file_hash, chunk_hashes

    async def _init_upload(
        self, client: httpx.AsyncClient, path: str, size: int, file_hash: str
    ) -> Dict[str, Any]:
        """
        Initialize upload session on the server.

        Notifies the server about the upcoming upload and validates that
        the server is ready to receive chunks.

        Args:
            client: HTTP client instance
            path: Remote file path
            size: File size in bytes
            file_hash: BLAKE3 hash of the entire file

        Returns:
            Server response with upload session details

        Raises:
            HTTPUploaderError: If initialization fails
        """
        try:
            response = await client.post(
                f"{self.server}/uploader/upload/init",
                json={"path": path, "size": size, "file_hash": file_hash},
                cookies={"sessionid": self.session_id},
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise HTTPUploaderError(
                f"Failed to initialize upload: {e.response.status_code} - {e.response.text}"
            ) from e

    async def _mark_chunks_as_not_uploaded(self, chunks: List[int]) -> None:
        """
        Mark chunks as not uploaded.
        """

        def _updater(meta: Dict[str, Any]) -> None:
            meta["completed"] = {
                k: v for k, v in meta["completed"].items() if int(k) not in chunks
            }

        await self._update_metadata(_updater)

    async def _complete(
        self,
        client: httpx.AsyncClient,
        path: str,
        size: int,
        file_hash: str,
        chunk_hashes: List[str],
    ) -> Dict[str, Any]:
        """
        Finalize upload on the server.

        Instructs the server to verify all chunks and complete the upload process.

        Args:
            client: HTTP client instance
            path: Remote file path
            size: File size in bytes
            file_hash: BLAKE3 hash of the entire file
            chunk_hashes: List of BLAKE3 hashes for each chunk
        Returns:
            Server response confirming upload completion

        Raises:
            HTTPUploaderError: If finalization fails (e.g., hash mismatch)
        """
        try:
            response = await client.post(
                f"{self.server}/uploader/upload/complete",
                json={
                    "path": path,
                    "size": size,
                    "file_hash": file_hash,
                    "chunk_hashes": chunk_hashes,
                },
                cookies={"sessionid": self.session_id},
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            error_data = e.response.json()
            if error_data.get("detail", {}).get("error_code") == "final_hash_mismatch":
                mismatch_chunks = error_data.get("detail", {}).get(
                    "mismatch_chunks", []
                )
                await self._mark_chunks_as_not_uploaded(mismatch_chunks)
                logger.warning(
                    f"Hash mismatch detected during finalization. "
                    f"Marking chunks {mismatch_chunks} as not uploaded."
                    f"Please reupload the file with --resume flag."
                )

            raise HTTPUploaderError(
                f"Failed to complete upload: {e.response.status_code} - {e.response.text}"
            ) from e

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=15),
        stop=stop_after_attempt(5),
        reraise=True,
        retry=retry_if_exception_type(httpx.TransportError),
    )
    async def _upload_chunk(
        self,
        client: httpx.AsyncClient,
        file_path: str,
        remote_path: str,
        index: int,
        offset: int,
        size: int,
        chunk_hash: str,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> Dict[str, Any]:
        """
        Upload a single chunk with retry logic.

        Args:
            client: HTTP client
            file_path: Local file path
            remote_path: Remote file path
            index: Chunk index
            offset: Byte offset in file
            size: Chunk size in bytes
            chunk_hash: Expected BLAKE3 hash of chunk
            progress_callback: Optional callback to report upload progress

        Returns:
            Server response dict

        Raises:
            HTTPUploaderError: If upload fails
        """

        async def body_gen():
            async with aiofiles.open(file_path, "rb") as f:
                await f.seek(offset)
                remaining = size
                while remaining > 0:
                    buf = await f.read(min(READ_CHUNK_SIZE, remaining))
                    if not buf:
                        break
                    remaining -= len(buf)
                    yield buf
                    # Update progress after yielding data
                    if progress_callback:
                        progress_callback(len(buf))

        params = {
            "path": remote_path,
            "offset": str(offset),
            "size": str(size),
            "hash": chunk_hash,
        }
        url = f"{self.server}/uploader/upload/chunk/{index}"

        try:
            response = await client.put(
                url,
                params=params,
                cookies={"sessionid": self.session_id},
                content=body_gen(),
            )
            response.raise_for_status()
            result = response.json()
            if result.get("status") != "ok":
                raise HTTPUploaderError(f"Server rejected chunk {index}: {result}")
            return result
        except httpx.HTTPStatusError as e:
            raise HTTPUploaderError(
                f"Chunk {index} upload failed: {e.response.status_code} - {e.response.text}"
            ) from e

    async def _upload_chunks(
        self,
        client: httpx.AsyncClient,
        file_path: Path,
        remote_path: str,
        size: int,
        completed: set[int],
    ) -> None:
        """
        Upload all pending chunks in parallel with progress tracking.

        Args:
            client: HTTP client instance
            file_path: Local file path
            remote_path: Remote file path
            size: File size in bytes
            completed: Set of already completed chunk indices

        Raises:
            asyncio.CancelledError: If upload is cancelled by user
            HTTPUploaderError: If chunk upload fails
        """
        total_chunks = self.meta["total_chunks"]
        chunks_to_upload = [i for i in range(total_chunks) if i not in completed]

        if not chunks_to_upload:
            logger.info("All chunks already uploaded, finalizing...")
            return

        sem = asyncio.Semaphore(self.max_parallel)
        bytes_completed = sum(min(CHUNK_SIZE, size - i * CHUNK_SIZE) for i in completed)

        progress = tqdm(
            total=size,
            initial=bytes_completed,
            desc=f"[INFO] Uploading {file_path.name}",
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
        )

        async def worker(i: int):
            """Upload a single chunk with progress tracking."""
            async with sem:
                if i in completed:
                    return
                offset = i * CHUNK_SIZE
                size_i = min(CHUNK_SIZE, size - offset)
                h = self.meta["chunk_hashes"][i]

                def progress_callback(bytes_uploaded: int):
                    progress.update(bytes_uploaded)

                await self._upload_chunk(
                    client,
                    str(file_path),
                    remote_path,
                    i,
                    offset,
                    size_i,
                    h,
                    progress_callback=progress_callback,
                )

                def mark_completed(meta: Dict[str, Any]) -> None:
                    meta["completed"][str(i)] = h

                await self._update_metadata(mark_completed)
                completed.add(i)

        tasks = [worker(i) for i in chunks_to_upload]
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info("Upload cancelled by user. Progress has been saved.")
            raise
        finally:
            progress.close()

    async def _finalize_upload(
        self, client: httpx.AsyncClient, remote_path: str, size: int, file_hash: str
    ) -> None:
        """
        Finalize upload on server and clean up metadata.

        On hash mismatch, metadata is cleared to force a fresh upload on retry.

        Args:
            client: HTTP client instance
            remote_path: Remote file path
            size: File size in bytes
            file_hash: BLAKE3 hash of the entire file

        Raises:
            HTTPUploaderError: If finalization fails
        """
        logger.info("Finalizing upload...")
        chunk_hashes = self.meta["chunk_hashes"]
        finalize = await self._complete(
            client, remote_path, size, file_hash, chunk_hashes
        )
        logger.info(f"✓ Upload complete: {finalize}")

        try:
            os.remove(self.meta_path)
        except FileNotFoundError:
            pass

    async def upload_file(self, file_path: Path, remote_path: str) -> None:
        """
        Upload a file with resumability support.

        This is the main entry point for uploading files. It handles:
        - Metadata loading/creation and validation
        - Server initialization
        - Parallel chunk uploading with progress tracking
        - Upload finalization and cleanup

        Uploads can be safely cancelled and resumed. Progress is saved after each
        chunk completes, allowing the upload to continue from where it left off.

        Args:
            file_path: Local file path
            remote_path: Remote file path (relative to user root, e.g., '/collections/file.zip')

        Raises:
            HTTPUploaderError: If upload fails
            asyncio.CancelledError: If upload is cancelled by user
        """
        if not file_path.exists():
            raise HTTPUploaderError(f"File not found: {file_path}")

        size = os.path.getsize(file_path)
        self.meta_path = str(file_path) + ".uploadmeta.json"

        file_hash, chunk_hashes = await self._load_or_create_metadata(
            file_path, remote_path, size
        )

        completed = set(map(int, self.meta["completed"].keys()))

        async with httpx.AsyncClient(timeout=None, verify=self.verify) as client:
            if completed:
                logger.info(f"Resuming upload of {file_path.name}...")
            else:
                logger.info(f"Initializing upload of {file_path.name}...")
                info = await self._init_upload(client, remote_path, size, file_hash)
                logger.info(
                    f"Server ready: {info['total_chunks']} chunks of {info['chunk_size'] // 1024 // 1024} MB"
                )

            await self._upload_chunks(client, file_path, remote_path, size, completed)
            await self._finalize_upload(client, remote_path, size, file_hash)

    def upload(self, filepath: Path, remote_path: str) -> None:
        """
        Synchronous wrapper for upload_file.

        This is the main public API for uploading files synchronously.
        It handles authentication and delegates to the async upload_file method.

        Args:
            filepath: Local file path
            remote_path: Remote file path (relative to user root)

        Raises:
            HTTPUploaderError: If authentication or upload fails
        """
        self.session_id = asyncio.run(self._login())
        asyncio.run(self.upload_file(filepath, remote_path))
