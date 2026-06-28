"""Helpers for sending local files as Responses API content parts."""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any

MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024
MAX_INLINE_TEXT_BYTES = 512 * 1024

TEXT_EXTENSIONS = {
    ".c",
    ".cc",
    ".cfg",
    ".conf",
    ".cpp",
    ".css",
    ".csv",
    ".go",
    ".h",
    ".hpp",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}


def build_content_parts(prompt: str, files: list[Path]) -> list[dict[str, Any]]:
    """Build a multimodal user content array from text and local files."""
    parts: list[dict[str, Any]] = [{"type": "input_text", "text": prompt}]
    for file_path in files:
        parts.append(file_to_content_part(file_path))
    return parts


def file_to_content_part(file_path: Path) -> dict[str, Any]:
    """Encode a local file as an image or generic file content part."""
    path = file_path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Attachment is not a file: {file_path}")

    size = path.stat().st_size
    if size > MAX_ATTACHMENT_BYTES:
        limit_mb = MAX_ATTACHMENT_BYTES // (1024 * 1024)
        raise ValueError(f"Attachment is larger than {limit_mb} MB: {file_path}")

    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"

    if _should_inline_text(path, media_type, size):
        return {
            "type": "input_text",
            "text": f"Attached file: {path.name}\n```\n{path.read_text(encoding='utf-8')}\n```",
        }

    data_uri = _data_uri(path, media_type)

    if media_type.startswith("image/"):
        return {
            "type": "input_image",
            "image_url": data_uri,
        }

    return {
        "type": "input_file",
        "filename": path.name,
        "file_data": data_uri,
    }


def _data_uri(path: Path, media_type: str) -> str:
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{media_type};base64,{data}"


def _should_inline_text(path: Path, media_type: str, size: int) -> bool:
    if size > MAX_INLINE_TEXT_BYTES:
        return False
    if media_type.startswith("text/") or path.suffix.lower() in TEXT_EXTENSIONS:
        try:
            path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return False
        return True
    return False
