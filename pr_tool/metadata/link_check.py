"""Ask an http(s) address whether it responds.

Used when a brand URL or a video link is entered.

* Brand URLs and video links on other hosts: a HEAD request is enough when the
  server allows it. Servers that reject HEAD are asked again with GET, without
  reading the body.
* YouTube and Vimeo video links: a plain request is not enough, because YouTube
  answers HTTP 200 for a video that does not exist. The provider's oEmbed
  endpoint is asked instead. It answers with an error for a video that is not
  there. A YouTube reply that names the video is remembered, so the video
  recap can show that title.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.parse
import urllib.request

import constants


def ensure_https_scheme(value: str) -> str:
    """Add ``https://`` when an address has no scheme.

    ``http://`` and ``https://`` are left as typed.
    """
    text = value.strip()
    if not text or '://' in text:
        return text
    return f'https://{text}'


_TIMEOUT_SECONDS = 10
_DEADLINE_SECONDS = 15
_USER_AGENT = 'DEEPCRAFT-PR-Tool'
_RETRY_GET = frozenset({400, 403, 405, 501})
_UNREACHABLE = (
    'This link did not respond. Check the address and your connection, then try again.'
)
_VIDEO_UNREACHABLE = (
    'This video could not be checked. Check the link and your connection, then try again.'
)
_OEMBED = (
    ('YouTube', ('youtube.com', 'youtu.be'), 'https://www.youtube.com/oembed?url='),
    ('Vimeo', ('vimeo.com',), 'https://vimeo.com/api/oembed.json?url='),
)


def link_response_error(url: str) -> str | None:
    """Return a message when *url* does not answer. ``None`` means it did."""
    _print_checking('Checking that the link responds...')
    try:
        status = _status(url, 'HEAD')
        if status in _RETRY_GET:
            status = _status(url, 'GET')
    except (urllib.error.URLError, TimeoutError, OSError):
        return _UNREACHABLE
    if status < 400:
        _print_approved('Link approved, the address responds.')
        return None
    return (
        f'This link did not respond (HTTP {status}). '
        'Check the address and try again.'
    )


def video_link_response_error(url: str) -> str | None:
    """Return a message when a video link does not point at a video. ``None`` means it does.

    YouTube and Vimeo are asked through their oEmbed endpoints. Other hosts
    fall back to :func:`link_response_error`. A YouTube title in the reply is
    kept for the video recap.
    """
    provider = _oembed_provider(url)
    if provider is None:
        return link_response_error(url)
    name, endpoint = provider
    _print_checking(f'Checking that the {name} video exists...')
    try:
        status, body = _exchange(
            endpoint + urllib.parse.quote(url, safe=''),
            'GET',
            read_body=True,
        )
    except (urllib.error.URLError, TimeoutError, OSError):
        return _VIDEO_UNREACHABLE
    if status < 400:
        if name == 'YouTube':
            _remember_youtube_title(url, body)
        _print_approved(f'Video approved, the {name} video exists.')
        return None
    return (
        f'The {name} video was not found (HTTP {status}). '
        'Check the link and try again.'
    )


# Titles YouTube has already reported, keyed by :func:`video_link_key`.
_youtube_titles: dict[str, str | None] = {}


def clear_youtube_titles() -> None:
    """Drop remembered YouTube titles. Tests use this to start from an empty cache."""
    _youtube_titles.clear()


def youtube_video_title(url: str) -> str | None:
    """The title YouTube reports for *url*, or None for another host or a failed lookup.

    A title read while approving the link is reused. A saved video that has not
    been checked in this run is looked up once.
    """
    provider = _oembed_provider(url)
    if provider is None or provider[0] != 'YouTube':
        return None
    from metadata.video_link import video_link_key

    key = video_link_key(url)
    if key in _youtube_titles:
        return _youtube_titles[key]
    _print_checking('Reading the YouTube title...')
    _name, endpoint = provider
    try:
        status, body = _exchange(
            endpoint + urllib.parse.quote(url, safe=''),
            'GET',
            read_body=True,
        )
    except (urllib.error.URLError, TimeoutError, OSError):
        _youtube_titles[key] = None
        return None
    title = _oembed_title(body) if status < 400 else None
    _youtube_titles[key] = title
    return title


def _remember_youtube_title(url: str, body: bytes) -> None:
    title = _oembed_title(body)
    if not title:
        return
    from metadata.video_link import video_link_key

    _youtube_titles[video_link_key(url)] = title


def _oembed_title(body: bytes) -> str | None:
    if not body:
        return None
    try:
        payload = json.loads(body.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    title = payload.get('title') if isinstance(payload, dict) else None
    if not isinstance(title, str):
        return None
    title = ' '.join(title.split())
    return title or None


def _oembed_provider(url: str) -> tuple[str, str] | None:
    host = (urllib.parse.urlparse(url).hostname or '').lower()
    for name, domains, endpoint in _OEMBED:
        if any(host == domain or host.endswith('.' + domain) for domain in domains):
            return name, endpoint
    return None


def _print_checking(message: str) -> None:
    print(f'{constants.ICON_INFO} {message}')


def _print_approved(message: str) -> None:
    print(f'{constants.ICON_SUCCESS} {message}')


def _status(url: str, method: str) -> int:
    status, _body = _exchange(url, method)
    return status


def _exchange(url: str, method: str, *, read_body: bool = False) -> tuple[int, bytes]:
    """One request, given up after ``_DEADLINE_SECONDS`` in total.

    The socket timeout applies to each address on its own. A name that resolves
    to several unreachable addresses would otherwise wait for every one of them.
    """
    outcome: dict = {}

    def run() -> None:
        try:
            outcome['reply'] = _exchange_once(url, method, read_body=read_body)
        except BaseException as exc:  # handed back to the caller below
            outcome['error'] = exc

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(_DEADLINE_SECONDS)
    if worker.is_alive():
        raise TimeoutError(f'No answer from {url} within {_DEADLINE_SECONDS} seconds.')
    if 'error' in outcome:
        raise outcome['error']
    return outcome['reply']


def _exchange_once(url: str, method: str, *, read_body: bool = False) -> tuple[int, bytes]:
    request = urllib.request.Request(
        url,
        method=method,
        headers={'User-Agent': _USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            body = _read_body(response) if read_body else b''
            return int(response.status), body
    except urllib.error.HTTPError as exc:
        return int(exc.code), b''


def _read_body(response) -> bytes:
    read = getattr(response, 'read', None)
    if not callable(read):
        return b''
    data = read()
    return data if isinstance(data, bytes) else b''
