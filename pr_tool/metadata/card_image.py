"""Publish an optional local image next to a card's metadata.json.

A content type opts in by adding its schema key to ``CARD_IMAGES``. Its prompt
calls :func:`interpret_card_image` and :func:`remember_card_image`. Saving and
pushing then copy that file into the card folder. No other call site changes.

The file must be WebP, and its width and height must be 16:9. A plain file
name, with no local file, is stored as typed and nothing extra is pushed.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

_IMAGE_NAME = (
    'Enter an image file name ending in .webp, for example acme.webp, '
    'or a path to a local .webp file.'
)
# File name -> local WebP chosen during this run. A name with no file is absent.
_image_source: dict[str, Path] = {}


@dataclass(frozen=True)
class CardImageSpec:
    """Which metadata field names the image, and how the summary refers to it."""

    field: str
    label: str


# Schema key -> the image that content type can publish beside metadata.json.
# Add a key here, then call interpret_card_image from that card's prompt.
CARD_IMAGES: dict[str, CardImageSpec] = {
    'extra-content-partners': CardImageSpec('brand_image_id', 'brand image'),
}


def card_image_spec(repo_key: str | None) -> CardImageSpec | None:
    """The image this content type publishes, or None when it publishes none."""
    if repo_key is None:
        return None
    return CARD_IMAGES.get(repo_key)


def clear_card_image() -> None:
    """Drop a local image chosen earlier in this run."""
    _image_source.clear()


def remember_card_image(name: str, source: Path | None) -> None:
    """Remember *source* as the file to publish under *name*, or forget it."""
    if source is None:
        _image_source.pop(name, None)
        return
    _image_source.clear()
    _image_source[name] = source.resolve()


def _chunk_size(kind: bytes, payload: bytes) -> tuple[int, int] | None:
    """Width and height from one WebP chunk, or None when this chunk has neither."""
    if kind == b'VP8X' and len(payload) >= 10:
        width = 1 + int.from_bytes(payload[4:7], 'little')
        height = 1 + int.from_bytes(payload[7:10], 'little')
        return width, height
    if kind == b'VP8 ' and len(payload) >= 10 and payload[3:6] == b'\x9d\x01\x2a':
        width = int.from_bytes(payload[6:8], 'little') & 0x3fff
        height = int.from_bytes(payload[8:10], 'little') & 0x3fff
        return width, height
    if kind == b'VP8L' and len(payload) >= 5 and payload[0] == 0x2f:
        bits = int.from_bytes(payload[1:5], 'little')
        width = (bits & 0x3fff) + 1
        height = ((bits >> 14) & 0x3fff) + 1
        return width, height
    return None


def webp_dimensions(data: bytes) -> tuple[int, int] | None:
    """Canvas size of a WebP file, or None when *data* is not a readable WebP.

    *data* may be only the start of the file. The size sits in the first chunk,
    so the rest of a large image is not required.
    """
    if len(data) < 12 or data[:4] != b'RIFF' or data[8:12] != b'WEBP':
        return None
    offset = 12
    found: tuple[int, int] | None = None
    while offset + 8 <= len(data):
        kind = data[offset:offset + 4]
        size = int.from_bytes(data[offset + 4:offset + 8], 'little')
        start = offset + 8
        dims = _chunk_size(kind, data[start:start + size])
        if kind == b'VP8X' and dims is not None:
            return dims
        if dims is not None and found is None:
            found = dims
        if found is not None or start + size > len(data):
            break
        offset = start + size + (size & 1)
    return found


def image_file_error(path: Path) -> str | None:
    """Return an error unless *path* is a WebP image whose sides are 16:9."""
    name = path.name
    if not name.lower().endswith('.webp'):
        return f'{name} must be a .webp file, for example acme.webp.'
    try:
        with path.open('rb') as handle:
            data = handle.read(64)
    except OSError as exc:
        return f'Could not read {path}: {exc}'
    dims = webp_dimensions(data)
    if dims is None:
        return f'{name} is not a WebP image.'
    width, height = dims
    if width <= 0 or height <= 0 or width * 9 != height * 16:
        return (
            f'{name} is {width}x{height}, not 16:9. '
            'Use an image whose width and height are 16 to 9, such as 1920x1080.'
        )
    return None


def interpret_card_image(value: str) -> tuple[str, Path | None, str | None]:
    """Split an image answer into a metadata file name and an optional file.

    A plain file name is stored as typed and has no file to publish. A path, or
    a file name that exists in the working directory, is checked and the name
    stored in metadata is that file's name. The third item is an error message.
    """
    text = value.strip().strip('"').strip("'")
    path = Path(text)
    looks_like_path = (
        any(sep in text for sep in ('/', '\\')) or path.is_absolute() or path.is_file()
    )
    if not looks_like_path:
        if not text.lower().endswith('.webp') or Path(text).name != text:
            return '', None, _IMAGE_NAME
        return text, None, None
    if not path.is_file():
        return '', None, f'No image file at {path}.'
    error = image_file_error(path)
    if error is not None:
        return '', None, error
    return path.name, path, None


def image_for_publish(card_dir: Path, image_name: object) -> Path | None:
    """The image sitting next to metadata.json, when one should be pushed.

    None means the card only has a file name. A file that is present but is not
    a 16:9 WebP raises ValueError.
    """
    if not isinstance(image_name, str) or not image_name.strip():
        return None
    name = Path(image_name).name
    if name != image_name.strip():
        return None
    dest = card_dir / name
    if not dest.is_file():
        return None
    error = image_file_error(dest)
    if error is not None:
        raise ValueError(error)
    return dest


def place_card_image(card_dir: Path, metadata: dict, repo_key: str | None) -> Path | None:
    """Copy this card's chosen local image next to metadata.json.

    Returns that file when this content type publishes one. A content type that
    is not in ``CARD_IMAGES`` returns None.
    """
    spec = card_image_spec(repo_key)
    if spec is None:
        return None
    image_name = metadata.get(spec.field)
    if isinstance(image_name, str):
        source = _image_source.get(Path(image_name).name)
        if source is not None and source.is_file():
            error = image_file_error(source)
            if error is not None:
                raise ValueError(error)
            card_dir.mkdir(parents=True, exist_ok=True)
            dest = card_dir / source.name
            if source.resolve() != dest.resolve():
                shutil.copyfile(source, dest)
    return image_for_publish(card_dir, image_name)


def copy_card_image(
    local_dir: Path,
    checkout_dir: Path,
    image_name: str,
    repo_subpath: str,
) -> str:
    """Copy the image beside metadata.json into the checkout.

    Returns the repository path to ``git add``.
    """
    checkout_dir.mkdir(parents=True, exist_ok=True)
    source = local_dir / image_name
    dest = checkout_dir / image_name
    if source.resolve() != dest.resolve():
        shutil.copyfile(source, dest)
    return f'{repo_subpath}/{image_name}'
