"""Automatic selection of a project image based on user-selected tags.

Reads the image catalog from GitHub (``REMOTE_IMAGES_URL``) and falls back
to a local copy shipped alongside this module (``LOCAL_IMAGES_FILE``) if
the remote copy cannot be fetched. Returns the image whose tags best match
a given list of input tags.

The catalog is a JSON array of objects, each with at least a ``name`` and a
``tags`` array, for example::

    [
        {
            "name": "Audio.png",
            "tags": ["audio", "microphone", "voice"],
            "link": "https://.../Audio.png"
        },
        ...
    ]
"""

import json
from functools import cache
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import constants

LOCAL_IMAGES_FILE = Path(__file__).resolve().parent / 'images.json'
REMOTE_IMAGES_URL = (
    constants.IMAGES_BROWSE_URL
    .replace('https://github.com/', 'https://raw.githubusercontent.com/')
    .rstrip('/')
    + '/main/images.json'
)
REMOTE_FETCH_TIMEOUT = 5  # seconds
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


def _sync_local_with_remote(remote_payload: str) -> None:
    """Mirror the remote payload into ``LOCAL_IMAGES_FILE`` if it differs.

    The remote catalog is the source of truth: any accidental local edits
    are overwritten so that image selection always works against an
    up-to-date copy. Failures are reported but never raise.
    """
    local_exists = LOCAL_IMAGES_FILE.exists()
    try:
        local_payload = (
            LOCAL_IMAGES_FILE.read_text(encoding='utf-8') if local_exists else None
        )
    except OSError as exc:
        print(f'{constants.ICON_WARNING} Warning: could not read local images file at {LOCAL_IMAGES_FILE} '
              f'while checking sync with {REMOTE_IMAGES_URL}: {exc}.')
        return
    if local_payload == remote_payload:
        return
    try:
        LOCAL_IMAGES_FILE.parent.mkdir(parents=True, exist_ok=True)
        LOCAL_IMAGES_FILE.write_text(remote_payload, encoding='utf-8')
    except OSError as exc:
        print(f'{constants.ICON_WARNING} Warning: could not update local images file at {LOCAL_IMAGES_FILE} '
              f'from {REMOTE_IMAGES_URL}: {exc}.')
        return
    if local_exists:
        print(f'{constants.ICON_INFO} Local images file at {LOCAL_IMAGES_FILE} was out of sync with '
              f'{REMOTE_IMAGES_URL} and has been refreshed.')
    else:
        print(f'{constants.ICON_INFO} Local images file at {LOCAL_IMAGES_FILE} created from {REMOTE_IMAGES_URL}.')


def _fetch_remote_images() -> list[dict] | None:
    """Try to fetch the catalog from ``REMOTE_IMAGES_URL``. Returns ``None``
    on any network, HTTP, decoding, parse, or shape error.

    On a successful fetch + parse, the raw payload is mirrored to
    ``LOCAL_IMAGES_FILE`` so the local copy stays in sync with the remote.
    """
    try:
        with urlopen(REMOTE_IMAGES_URL, timeout=REMOTE_FETCH_TIMEOUT) as response:
            payload = response.read().decode('utf-8')
    except (URLError, TimeoutError, OSError) as exc:
        print(f'{constants.ICON_WARNING} Warning: could not fetch images file from {REMOTE_IMAGES_URL}: {exc}.')
        return None
    parsed = _parse_images(payload, REMOTE_IMAGES_URL)
    if parsed is not None:
        _sync_local_with_remote(payload)
    return parsed


def _load_local_images() -> list[dict] | None:
    """Load the catalog from ``LOCAL_IMAGES_FILE``. Returns ``None`` on any
    filesystem, decoding, parse, or shape error."""
    if not LOCAL_IMAGES_FILE.exists():
        print(f'{constants.ICON_WARNING} Warning: local images file not found at {LOCAL_IMAGES_FILE}.')
        return None
    try:
        payload = LOCAL_IMAGES_FILE.read_text(encoding='utf-8')
    except OSError as exc:
        print(f'{constants.ICON_WARNING} Warning: could not read local images file at {LOCAL_IMAGES_FILE}: {exc}.')
        return None
    return _parse_images(payload, str(LOCAL_IMAGES_FILE))


@cache
def _load_images() -> list[dict]:
    """Load the image catalog. Tries the remote copy first; falls back to the
    local file. Returns an empty list when neither source is available.

    The result is cached for the lifetime of the process, so the network
    fetch happens at most once per run.
    """
    remote = _fetch_remote_images()
    if remote is not None:
        return remote
    print(f'{constants.ICON_INFO} Falling back to local images file at {LOCAL_IMAGES_FILE}.')
    local = _load_local_images()
    if local is not None:
        return local
    print(f'{constants.ICON_WARNING} No image catalog available; default image "{DEFAULT_IMAGE}" will be used.')
    return []


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
