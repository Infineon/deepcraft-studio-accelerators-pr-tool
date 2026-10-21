"""Validate that a metadata video link points at one video."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urlparse

_YOUTUBE_ID_RE = re.compile(r'^[A-Za-z0-9_-]{11}$')
_VIDEO_FILE_RE = re.compile(r'\.(?:mp4|webm|mov|m4v|ogv)$', re.IGNORECASE)
_YOUTUBE_VIDEO_PREFIXES = ('embed', 'shorts', 'live', 'v')

_NOT_URL = (
    'Link must be an http(s) URL to a single video '
    '(for example https://youtu.be/...).'
)
_NOT_VIDEO = (
    'Link must be a single video URL, not a regular web page '
    '(for example https://youtu.be/... or https://vimeo.com/123456789).'
)
_YOUTUBE_PLAYLIST = 'YouTube playlists are not allowed. Use a link to a single video.'
_YOUTUBE_NOT_VIDEO = (
    'Link must be a single YouTube video (for example https://youtu.be/...), '
    'not a channel or another page.'
)
_COLLECTION = 'Playlists and collections are not allowed. Use a link to a single video.'
_DUPLICATE = 'This video link already exists in the videos field. Please try again.'


def video_link_error(value: str) -> str | None:
    """Return an error when *value* is not a link to one video."""
    parsed = urlparse((value or '').strip())
    host = (parsed.hostname or '').lower()
    if parsed.scheme not in ('http', 'https') or not host:
        return _NOT_URL
    if _is_youtube_host(host):
        return _youtube_video_error(parsed, host)
    if _is_collection(parsed, host):
        return _COLLECTION
    if _is_single_video(parsed, host) or _is_direct_video_file(parsed):
        return None
    return _NOT_VIDEO


def duplicate_video_link_error(link: str, taken: list[str]) -> str | None:
    """Return an error when *link* is already one of *taken*."""
    key = video_link_key(link)
    if any(video_link_key(other) == key for other in taken):
        return _DUPLICATE
    return None


def video_link_key(value: str) -> str:
    """Identity of a video link, so equivalent URLs count as the same video."""
    parsed = urlparse((value or '').strip())
    host = (parsed.hostname or '').lower()
    if _is_youtube_host(host):
        video_id = _youtube_video_id(parsed, host)
        if video_id:
            return f'youtube:{video_id}'
    if parsed.scheme and host:
        path = parsed.path.rstrip('/')
        query = f'?{parsed.query}' if parsed.query else ''
        return f'{parsed.scheme.lower()}://{host}{path}{query}'
    return (value or '').strip().casefold().rstrip('/')


def _host_is(host: str, name: str) -> bool:
    return host == name or host.endswith('.' + name)


def _is_youtube_host(host: str) -> bool:
    return any(_host_is(host, name) for name in ('youtube.com', 'youtu.be', 'youtube-nocookie.com'))


def _path_parts(parsed) -> list[str]:
    return [part for part in parsed.path.split('/') if part]


def _youtube_video_id(parsed, host: str) -> str:
    if _path_has_youtube_playlist(parsed):
        return ''
    parts = _path_parts(parsed)
    query = parse_qs(parsed.query, keep_blank_values=True)
    video_id = ''
    if _host_is(host, 'youtu.be'):
        if len(parts) == 1:
            video_id = parts[0]
    elif parts[:1] == ['watch']:
        video_ids = query.get('v') or []
        video_id = video_ids[0] if video_ids else ''
    elif len(parts) >= 2 and parts[0] in _YOUTUBE_VIDEO_PREFIXES:
        video_id = parts[1]
    if _YOUTUBE_ID_RE.match(video_id):
        return video_id
    return ''


def _youtube_video_error(parsed, host: str) -> str | None:
    if _path_has_youtube_playlist(parsed):
        return _YOUTUBE_PLAYLIST
    if _youtube_video_id(parsed, host):
        return None
    return _YOUTUBE_NOT_VIDEO


def _path_has_youtube_playlist(parsed) -> bool:
    parts = _path_parts(parsed)
    query = parse_qs(parsed.query, keep_blank_values=True)
    return (
        'list' in query
        or (bool(parts) and parts[0] == 'playlist')
        or (len(parts) >= 2 and parts[0] == 'embed' and parts[1] == 'videoseries')
    )


def _is_collection(parsed, host: str) -> bool:
    parts = _path_parts(parsed)
    if not parts:
        return False
    if _host_is(host, 'vimeo.com') and parts[0] in ('showcase', 'channels', 'album', 'groups', 'ondemand'):
        return True
    if _host_is(host, 'dailymotion.com') and parts[0] == 'playlist':
        return True
    return _host_is(host, 'loom.com') and parts[:2] == ['share', 'folder']


def _is_single_video(parsed, host: str) -> bool:
    parts = _path_parts(parsed)
    if _host_is(host, 'vimeo.com'):
        if _host_is(host, 'player.vimeo.com'):
            return len(parts) >= 2 and parts[0] == 'video' and parts[1].isdigit()
        return bool(parts) and parts[0].isdigit()
    if _host_is(host, 'dailymotion.com'):
        return len(parts) >= 2 and parts[0] == 'video' and bool(parts[1])
    if host == 'dai.ly':
        return len(parts) == 1 and bool(parts[0])
    if _host_is(host, 'wistia.com') or _host_is(host, 'wistia.net'):
        if 'medias' in parts:
            index = parts.index('medias')
            return index + 1 < len(parts) and bool(parts[index + 1])
        return len(parts) >= 3 and parts[0] == 'embed' and parts[1] == 'iframe' and bool(parts[2])
    if _host_is(host, 'loom.com'):
        return len(parts) == 2 and parts[0] == 'share' and bool(parts[1])
    return False


def _is_direct_video_file(parsed) -> bool:
    return bool(_VIDEO_FILE_RE.search(unquote(parsed.path)))
