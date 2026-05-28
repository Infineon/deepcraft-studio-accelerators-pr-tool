"""Automatic selection of a project image based on user-selected tags.

Uses only the local catalog file ``images.json`` in this directory (no network
fetch). Returns the image whose tags best match a given list of input tags.

The catalog is a JSON array of objects, each with at least a ``name`` and a
``tags`` array, for example::

    [
        {
            "name": "Audio.png",
            "tags": ["audio", "microphone", "voice"]
        },
        ...
    ]
"""

import json
from functools import cache
from pathlib import Path

import constants

LOCAL_IMAGES_FILE = Path(__file__).resolve().parent / 'images.json'
DEFAULT_IMAGE = 'deepcraft.webp'


def _parse_images(payload: str, source: str) -> list[dict] | None:
    """Parse a JSON payload into a list of image entries. Returns ``None`` if
    the payload is not valid JSON or is not a JSON array."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        print(f'{constants.ICON_WARNING} Warning: images file at {source} is not valid JSON: {exc}.')
        return None
    if not isinstance(data, list):
        print(f'{constants.ICON_WARNING} Warning: images file at {source} is not a JSON array.')
        return None
    return data


@cache
def _load_images() -> list[dict]:
    """Load the catalog from local ``images.json`` only (cached per process)."""
    if not LOCAL_IMAGES_FILE.exists():
        print(f'{constants.ICON_WARNING} Warning: images catalog not found at {LOCAL_IMAGES_FILE}.')
        return []
    try:
        payload = LOCAL_IMAGES_FILE.read_text(encoding='utf-8')
    except OSError as exc:
        print(f'{constants.ICON_WARNING} Warning: could not read images catalog at {LOCAL_IMAGES_FILE}: {exc}.')
        return []
    parsed = _parse_images(payload, str(LOCAL_IMAGES_FILE))
    if parsed is None:
        return []
    return parsed


def get_available_tags() -> list[str]:
    """Return the unique, sorted list of tags present in the image catalog."""
    tags: set[str] = set()
    for img in _load_images():
        if not isinstance(img, dict):
            continue
        for t in img.get('tags', []):
            if isinstance(t, str) and t.strip():
                tags.add(t.strip())
    return sorted(tags)


def get_available_images() -> list[str]:
    """Return the sorted list of image names present in the image catalog."""
    names: list[str] = []
    for img in _load_images():
        if not isinstance(img, dict):
            continue
        name = img.get('name')
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return sorted(names)


def select_image(tags: list[str]) -> str:
    """Return the ``name`` of the image whose tags best match ``tags``.

    Tag comparison is case-insensitive. The image with the highest number of
    overlapping tags wins. On a tie, the image that appears first in the
    catalog is returned. When the catalog is unavailable, no tags are
    provided, or no image shares any tag with the input, the default image
    (``DEFAULT_IMAGE``) is returned instead.
    """
    images = _load_images()
    if not images:
        return DEFAULT_IMAGE
    user_tag_set = {t.strip().lower() for t in tags if isinstance(t, str) and t.strip()}
    if not user_tag_set:
        print(f'{constants.ICON_INFO} No tags provided; falling back to default image "{DEFAULT_IMAGE}".')
        return DEFAULT_IMAGE
    best_name = ''
    best_score = 0
    for img in images:
        if not isinstance(img, dict):
            continue
        name = img.get('name')
        image_tags = img.get('tags', [])
        if not isinstance(name, str) or not isinstance(image_tags, list):
            continue
        image_tag_set = {str(t).strip().lower() for t in image_tags if isinstance(t, str)}
        score = len(user_tag_set & image_tag_set)
        if score > best_score:
            best_score = score
            best_name = name
    if best_score == 0:
        print(f'{constants.ICON_WARNING} Warning: no image in the catalog shares any tag with '
              f'{sorted(user_tag_set)}; falling back to default image "{DEFAULT_IMAGE}".')
        return DEFAULT_IMAGE
    return best_name
