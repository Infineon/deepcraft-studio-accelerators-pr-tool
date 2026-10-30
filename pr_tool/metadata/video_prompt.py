"""Interactive prompt for the optional videos field."""

import re
import unicodedata
from typing import Any

import constants
from metadata.prompts import _separator
from metadata.video_link import video_link_error


def normalize_video_text(value: str) -> str:
    """Store one line of text that can sit inside ``metadata.json``.

    Accents and symbols stay. Line breaks become spaces, other control
    characters are dropped, and a straight ``"`` becomes “ or ”.
    """
    text = unicodedata.normalize('NFC', value or '')
    text = text.replace('\r\n', '\n').replace('\r', '\n').replace('\t', ' ')
    chars: list[str] = []
    opening_quote = True
    for char in text:
        if char == '"':
            chars.append('\u201c' if opening_quote else '\u201d')
            opening_quote = not opening_quote
        elif char == '\n':
            chars.append(' ')
        elif unicodedata.category(char).startswith('C'):
            continue
        else:
            chars.append(char)
    return re.sub(r' {2,}', ' ', ''.join(chars)).strip()


def _normalize_videos(value: Any) -> list[dict] | None:
    if not isinstance(value, list) or not value:
        return None
    videos: list[dict] = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        title = entry.get('title')
        description = entry.get('description')
        link = entry.get('link')
        if not all(isinstance(item, str) and item.strip() for item in (title, description, link)):
            continue
        title = normalize_video_text(title)
        description = normalize_video_text(description)
        if not title or not description:
            continue
        videos.append({
            'title': title,
            'description': description,
            'link': link.strip(),
        })
    return videos or None


def videos_are_empty(value: Any) -> bool:
    """True when ``videos`` is missing, blank, or has no complete entry."""
    return _normalize_videos(value) is None


def _read_prompt(name: str, lines: list[str]) -> str:
    top_sep = _separator('=')
    bottom_sep = _separator('-')
    body = ''.join(f'{line}\n' for line in lines)
    return input(f'{top_sep}\n{name}\n{body}{bottom_sep}\n: ').strip()


def _warn(message: str) -> None:
    print(f'{constants.ICON_WARNING} {message}')


def _collect_text(name: str, default: str | None) -> str:
    lines = [f'>>> Press Enter to keep: {default}'] if default else []
    while True:
        raw = _read_prompt(name, lines)
        if not raw and default:
            return default
        value = normalize_video_text(raw)
        if value:
            return value
        _warn('Value cannot be empty, please try again.')


_LINK_TRIES = 3


def _link_lines(default: str | None, attempts: int) -> list[str]:
    lines = [
        '  Single video URL only (for example https://youtu.be/...).',
        '  Playlists and regular web pages are not allowed.',
        f'  Attempts: {attempts} of {_LINK_TRIES}',
    ]
    if default:
        lines.append(f'>>> Press Enter to keep: {default}')
    return lines


def _collect_video_link(default: str | None = None) -> str | None:
    """Return a video URL, or ``None`` to show the Videos prompt again.

    An empty entry and a rejected link each count as one attempt.
    Three attempts return to that prompt. Enter keeps a saved link.
    """
    attempts = 0
    while True:
        raw = _read_prompt('Video link', _link_lines(default, attempts))
        if not raw and default:
            link = default
        elif not raw:
            link = ''
        else:
            link = raw
        if not link:
            error = 'Value cannot be empty, please try again.'
        else:
            error = video_link_error(link)
        if error is None:
            return link.strip()
        attempts += 1
        if attempts >= _LINK_TRIES:
            _warn(f'Returning to the Videos prompt. (attempt {attempts} of {_LINK_TRIES})')
            return None
        _warn(f'{error} ({attempts} of {_LINK_TRIES})')


def _saved_video_lines(video: dict) -> list[str]:
    return [
        '>>> Press Enter to keep:',
        f'  Title: {video["title"]}',
        f'  Description: {video["description"]}',
        f'  Link: {video["link"]}',
    ]


def _choose_video(current: dict | None, *, several: bool) -> str:
    """Return ``keep``, ``add``, or ``remove``."""
    if current:
        lines = [
            'Videos - press Enter to keep this video, type 1 to modify it, or type 2 to remove it',
            *_saved_video_lines(current),
            '  1. Modify the video',
            '  2. Remove the video',
        ]
        retry = 'Press Enter to keep it, type 1 to modify it, or type 2 to remove it.'
    else:
        note = 'Only one video can be saved. ' if several else ''
        lines = [
            f'Videos - {note}press Enter to leave this field empty, or type 1 to add a video',
            '  1. Add a video',
        ]
        retry = 'Press Enter to leave this field empty, or type 1 to add a video.'
    while True:
        raw = _read_prompt(lines[0], lines[1:])
        if not raw:
            return 'keep' if current else 'remove'
        if raw == '1':
            return 'add'
        if current and raw == '2':
            return 'remove'
        _warn(f'{retry} Please try again.')


def collect_videos(previous: dict) -> list[dict] | None:
    """Ask for one optional video, using the same prompt layout as other fields.

    Enter leaves the field empty when no video is saved, and keeps a saved video.
    ``1`` adds or modifies that video. ``2`` removes a saved video.
    Three attempts on the video link, empty or rejected, return to this prompt.
    ``None`` means ``videos`` is left out of ``metadata.json``.
    """
    saved = _normalize_videos(previous.get('videos'))
    current = saved[0] if saved and len(saved) == 1 else None
    while True:
        choice = _choose_video(current, several=bool(saved and len(saved) > 1))
        if choice == 'keep':
            return [current] if current else None
        if choice == 'remove':
            return None
        title = _collect_text('Video title', current['title'] if current else None)
        description = _collect_text('Video description', current['description'] if current else None)
        link = _collect_video_link(current['link'] if current else None)
        if link is None:
            continue
        return [{'title': title, 'description': description, 'link': link}]
