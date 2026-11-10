"""Ask an http(s) address whether it responds.

Used when a brand URL or a video link is entered.

* Brand URLs and video links on other hosts: a HEAD request is enough when the
  server allows it. Servers that reject HEAD are asked again with GET, without
  reading the body.
* YouTube and Vimeo video links: a plain request is not enough, because YouTube
  answers HTTP 200 for a video that does not exist. The provider's oEmbed
  endpoint is asked instead. It answers with an error for a video that is not
  there.
"""

from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request

import constants

_TIMEOUT_SECONDS = 10
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
    fall back to :func:`link_response_error`.
    """
    provider = _oembed_provider(url)
    if provider is None:
        return link_response_error(url)
    name, endpoint = provider
    _print_checking(f'Checking that the {name} video exists...')
    try:
        status = _status(endpoint + urllib.parse.quote(url, safe=''), 'GET')
    except (urllib.error.URLError, TimeoutError, OSError):
        return _VIDEO_UNREACHABLE
    if status < 400:
        _print_approved(f'Video approved, the {name} video exists.')
        return None
    return (
        f'The {name} video was not found (HTTP {status}). '
        'Check the link and try again.'
    )


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
    request = urllib.request.Request(
        url,
        method=method,
        headers={'User-Agent': _USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)
