import hashlib
import json
import os
import re
import struct
import tempfile
import zlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from fastapi import UploadFile
from pydantic import ValidationError

from app.schemas.uploads import AllowedUploadType, UploadPolicy

CHUNK_SIZE = 64 * 1024
GENERIC_MEDIA_TYPE = "application/octet-stream"
STORAGE_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


class UploadPolicyError(Exception):
    """The configured local upload policy could not be read or validated."""


class StorageConfigurationError(Exception):
    """The configured private storage location is unsafe or unavailable."""


class UploadRejected(Exception):
    pass


class UploadTooLarge(UploadRejected):
    pass


class StorageUnavailable(Exception):
    pass


@dataclass(frozen=True)
class StoredUpload:
    storage_id: str
    original_filename: str
    media_type: str
    byte_size: int
    sha256_digest: str


class UploadPolicyLoader:
    def __init__(self, policy_path: Path):
        self.policy_path = policy_path

    def load(self) -> UploadPolicy:
        path = self.policy_path
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[2] / path
        try:
            return UploadPolicy.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError) as exc:
            raise UploadPolicyError("Upload policy is unavailable or invalid; no file was stored.") from exc

    @staticmethod
    def digest(policy: UploadPolicy) -> str:
        canonical = json.dumps(
            policy.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class PrivateLocalStorage:
    def __init__(self, storage_root: Path):
        repository_root = Path(__file__).resolve().parents[3]
        root = storage_root
        if not root.is_absolute():
            root = Path(__file__).resolve().parents[2] / root
        root = root.resolve()
        frontend_root = (repository_root / "frontend").resolve()
        if root == frontend_root or root.is_relative_to(frontend_root):
            raise StorageConfigurationError("Private storage must be outside the frontend directory tree.")
        self.root = root

    @staticmethod
    def _display_filename(filename: str | None) -> str:
        if not filename:
            raise UploadRejected("A filename is required.")
        normalized = filename.replace("\\", "/")
        name = PurePosixPath(normalized).name
        if not name or name in {".", ".."} or any(ord(char) < 32 or ord(char) == 127 for char in name):
            raise UploadRejected("The filename is invalid.")
        if len(name) > 255:
            raise UploadRejected("The filename is too long.")
        return name

    @staticmethod
    def _configured_type(filename: str, supplied_type: str | None, policy: UploadPolicy) -> AllowedUploadType:
        extension = Path(filename).suffix.lower()
        candidate = next(
            (item for item in policy.allowed_file_types if extension in item.extensions),
            None,
        )
        if candidate is None:
            raise UploadRejected("This file extension is not allowed by the active upload policy.")
        declared_type = (supplied_type or GENERIC_MEDIA_TYPE).split(";", 1)[0].strip().lower()
        if declared_type not in {candidate.media_type, GENERIC_MEDIA_TYPE}:
            raise UploadRejected("The supplied media type does not match the configured file type.")
        return candidate

    @staticmethod
    def _validate_pdf(path: Path, size: int) -> bool:
        if size < 12:
            return False
        with path.open("rb") as source:
            header = source.read(8)
            source.seek(max(size - 2048, 0))
            trailer = source.read()
        return header.startswith(b"%PDF-") and b"%%EOF" in trailer

    @staticmethod
    def _validate_png(path: Path, size: int) -> bool:
        signature = b"\x89PNG\r\n\x1a\n"
        if size < 45:
            return False
        with path.open("rb") as source:
            if source.read(8) != signature:
                return False
            first_chunk = True
            saw_data = False
            while source.tell() < size:
                header = source.read(8)
                if len(header) != 8:
                    return False
                chunk_length = struct.unpack(">I", header[:4])[0]
                chunk_type = header[4:]
                if chunk_length > size - source.tell() - 4:
                    return False
                if first_chunk and (chunk_type != b"IHDR" or chunk_length != 13):
                    return False
                first_chunk = False
                crc = zlib.crc32(chunk_type)
                remaining = chunk_length
                ihdr_data = bytearray() if chunk_type == b"IHDR" else None
                while remaining:
                    part = source.read(min(remaining, CHUNK_SIZE))
                    if not part:
                        return False
                    crc = zlib.crc32(part, crc)
                    if ihdr_data is not None:
                        ihdr_data.extend(part)
                    remaining -= len(part)
                crc_bytes = source.read(4)
                if len(crc_bytes) != 4 or struct.unpack(">I", crc_bytes)[0] != crc & 0xFFFFFFFF:
                    return False
                if chunk_type == b"IHDR":
                    if ihdr_data is None or len(ihdr_data) != 13:
                        return False
                    width, height = struct.unpack(">II", ihdr_data[:8])
                    if width == 0 or height == 0:
                        return False
                elif chunk_type == b"IDAT":
                    saw_data = True
                elif chunk_type == b"IEND":
                    return chunk_length == 0 and saw_data and source.tell() == size
        return False

    @staticmethod
    def _validate_jpeg(path: Path, size: int) -> bool:
        if size < 20:
            return False
        frame_markers = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
        with path.open("rb") as source:
            if source.read(2) != b"\xff\xd8":
                return False
            saw_frame = False
            saw_scan = False
            while source.tell() < size:
                if source.read(1) != b"\xff":
                    return False
                marker_byte = source.read(1)
                while marker_byte == b"\xff":
                    marker_byte = source.read(1)
                if not marker_byte:
                    return False
                marker = marker_byte[0]
                if marker == 0xD9:
                    return saw_frame and saw_scan and source.tell() == size
                if marker in {0xD8, 0x01} or 0xD0 <= marker <= 0xD7:
                    continue
                length_bytes = source.read(2)
                if len(length_bytes) != 2:
                    return False
                segment_length = struct.unpack(">H", length_bytes)[0]
                if segment_length < 2 or source.tell() + segment_length - 2 > size:
                    return False
                if marker in frame_markers:
                    if segment_length < 8:
                        return False
                    frame_data = source.read(5)
                    if len(frame_data) != 5:
                        return False
                    height, width = struct.unpack(">HH", frame_data[1:5])
                    if width == 0 or height == 0:
                        return False
                    saw_frame = True
                    source.seek(source.tell() + segment_length - 7)
                elif marker == 0xDA:
                    if segment_length < 6:
                        return False
                    source.seek(source.tell() + segment_length - 2)
                    saw_scan = True
                    break
                else:
                    source.seek(source.tell() + segment_length - 2)
            if not saw_scan or not saw_frame:
                return False
            source.seek(size - 2)
            return source.read(2) == b"\xff\xd9"

    @classmethod
    def _validate_content(cls, path: Path, size: int, file_format: str) -> bool:
        if file_format == "pdf":
            return cls._validate_pdf(path, size)
        if file_format == "png":
            return cls._validate_png(path, size)
        if file_format == "jpeg":
            return cls._validate_jpeg(path, size)
        return False

    def _safe_path(self, storage_id: str) -> Path:
        if not STORAGE_ID_PATTERN.fullmatch(storage_id):
            raise StorageUnavailable("Stored file reference is invalid.")
        candidate = self.root / storage_id[:2] / storage_id
        resolved = candidate.resolve()
        if not resolved.is_relative_to(self.root) or candidate.is_symlink() or candidate.parent.is_symlink():
            raise StorageUnavailable("Stored file reference is invalid.")
        return resolved

    async def store_upload(
        self,
        upload: UploadFile,
        policy: UploadPolicy,
    ) -> StoredUpload:
        display_name = self._display_filename(upload.filename)
        configured_type = self._configured_type(display_name, upload.content_type, policy)
        temporary_path: Path | None = None
        final_path: Path | None = None
        final_created = False
        storage_id = os.urandom(16).hex()
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            staging_dir = self.root / ".staging"
            staging_dir.mkdir(mode=0o700, exist_ok=True)
            if os.name != "nt":
                self.root.chmod(0o700)
                staging_dir.chmod(0o700)
            temporary_path = staging_dir / f"{storage_id}.part"
            byte_size = 0
            with temporary_path.open("xb") as destination:
                while chunk := await upload.read(CHUNK_SIZE):
                    byte_size += len(chunk)
                    if byte_size > policy.max_file_size_bytes:
                        raise UploadTooLarge("The uploaded file exceeds the configured size limit.")
                    destination.write(chunk)
                destination.flush()
                os.fsync(destination.fileno())
            if byte_size == 0:
                raise UploadRejected("Empty files are not allowed.")
            if not self._validate_content(temporary_path, byte_size, configured_type.file_format):
                raise UploadRejected("The file content is malformed or does not match its configured type.")

            final_dir = self.root / storage_id[:2]
            final_dir.mkdir(mode=0o700, exist_ok=True)
            final_path = self._safe_path(storage_id)
            os.link(temporary_path, final_path)
            final_created = True
            temporary_path.unlink()
            temporary_path = None
            digest = self.sha256_digest(storage_id)
            return StoredUpload(
                storage_id=storage_id,
                original_filename=display_name,
                media_type=configured_type.media_type,
                byte_size=byte_size,
                sha256_digest=digest,
            )
        except (UploadRejected, UploadTooLarge, StorageUnavailable):
            self._cleanup(temporary_path)
            self._cleanup(final_path if final_created else None)
            self._cleanup_empty_directories(storage_id)
            raise
        except Exception as exc:
            self._cleanup(temporary_path)
            self._cleanup(final_path if final_created else None)
            self._cleanup_empty_directories(storage_id)
            raise StorageUnavailable("Private file storage could not complete the operation.") from exc

    def sha256_digest(self, storage_id: str) -> str:
        path = self._safe_path(storage_id)
        digest = hashlib.sha256()
        with path.open("rb") as source:
            while chunk := source.read(CHUNK_SIZE):
                digest.update(chunk)
        return digest.hexdigest()

    def remove(self, storage_id: str) -> None:
        try:
            self._safe_path(storage_id).unlink(missing_ok=True)
        except OSError as exc:
            raise StorageUnavailable("Private file cleanup could not complete.") from exc

    @staticmethod
    def _cleanup(path: Path | None) -> None:
        if path is not None:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    def _cleanup_empty_directories(self, storage_id: str) -> None:
        for directory in (self.root / storage_id[:2], self.root / ".staging", self.root):
            try:
                directory.rmdir()
            except OSError:
                pass
