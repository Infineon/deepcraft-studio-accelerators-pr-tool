"""Interactive prompt for the optional videos field."""

import re
import unicodedata
from typing import Any

import constants
from metadata.prompts import (
    MODIFY_KEY,
    NEW_VALUE_KEY,
    _field_separator,
    _menu_choice,
    _separator,
    field_name,
    input_prefilled,
    paint_yellow,
)
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
    print(paint_yellow(f'{constants.ICON_WARNING} {message}'))


def _keep_lines(default: str) -> list[str]:
    """Enter row for a saved video field, in the same list as the other menus."""
    return [
        _separator('-'),
        f'  {constants.ICON_WARNING} {paint_yellow("Current value:")} {default}',
        _separator('-'),
        '  Choose an option:',
        _menu_choice('Enter', 'Keep the current value'),
        _menu_choice(MODIFY_KEY, 'Modify the current value'),
        _menu_choice(NEW_VALUE_KEY, 'Type a new value'),
    ]


def _collect_text(name: str, default: str | None, max_len: int) -> str:
    lines = _keep_lines(default) if default else []
    label = f'{field_name(name)} (max {max_len} characters)'
    while True:
        raw = _read_prompt(label, lines)
        if default and raw == MODIFY_KEY:
            raw = input_prefilled(': ', default, read=input).strip()
        elif default and raw == NEW_VALUE_KEY:
            raw = input(': ').strip()
        elif default and raw:
            _warn(
                'Press Enter to keep it, type 1 to modify it, '
                'or type 2 to type a new value. Please try again.'
            )
            continue
        elif not raw and default and len(default) <= max_len:
            return default
        value = normalize_video_text(raw)
        if not value:
            _warn('Value cannot be empty, please try again.')
            continue
        if len(value) > max_len:
            _warn(f'Value is more than {max_len} characters, please try again.')
            continue
        return value


_LINK_TRIES = 3
VIDEO_TITLE_MAX_LENGTH = 40
VIDEO_DESCRIPTION_MAX_LENGTH = 300
_VIDEO_RULES = (
    '  Use a single video URL (YouTube, Vimeo, Dailymotion, Wistia, Loom, etc.).',
    '  Links with a start time are allowed, such as https://youtu.be/...?t=42.',
    '  Video playlists and regular web pages are not allowed.',
)


def _link_lines(default: str | None, attempts: int) -> list[str]:
    lines = [*_VIDEO_RULES] if default else []
    lines.append(f'  Attempts: {attempts} of {_LINK_TRIES}')
    if default:
        lines.extend(_keep_lines(default))
    return lines


def _collect_video_link(default: str | None = None) -> str | None:
    """Return a video URL, or ``None`` to show the Videos prompt again.

    An empty entry and a rejected link each count as one attempt.
    Three attempts return to that prompt. Enter keeps a saved link.
    """
    attempts = 0
    while True:
        raw = _read_prompt(field_name('Video link'), _link_lines(default, attempts))
        if default and raw == MODIFY_KEY:
            link = input_prefilled(': ', default, read=input).strip()
        elif default and raw == NEW_VALUE_KEY:
            link = input(': ').strip()
        elif default and raw:
            _warn(
                'Press Enter to keep it, type 1 to modify it, '
                'or type 2 to type a new value. Please try again.'
            )
            continue
        elif not raw and default:
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


def _choice(key: str, text: str) -> str:
    """One menu row. Numbers use the same ``1.`` form as the other prompts."""
    return _menu_choice(key, text)


def _show_video_menu(details: list[str], options: list[str]) -> None:
    """Print the Videos block in the same frame as the long-description menu."""
    rule = _separator('-')
    print(_field_separator())
    print(field_name('Videos'))
    print(rule)
    for line in details:
        print(line)
    print(rule)
    print('  Choose an option:')
    for option in options:
        print(option)
    print(rule)


def _saved_video_is_too_long(video: dict) -> str | None:
    if len(video['title']) > VIDEO_TITLE_MAX_LENGTH:
        return (
            f'Video title is more than {VIDEO_TITLE_MAX_LENGTH} characters. '
            'Type 1 to modify it.'
        )
    if len(video['description']) > VIDEO_DESCRIPTION_MAX_LENGTH:
        return (
            f'Video description is more than {VIDEO_DESCRIPTION_MAX_LENGTH} characters. '
            'Type 1 to modify it.'
        )
    return None


def _choose_video(current: dict | None, *, several: bool) -> str:
    """Return ``keep``, ``add``, or ``remove``."""
    if current:
        details = [
            f'  Title: {current["title"]}',
            f'  Description: {current["description"]}',
            f'  Link: {current["link"]}',
        ]
        options = [
            _choice('Enter', 'Keep this video'),
            _choice('1', 'Modify the video'),
            _choice('2', 'Remove the video'),
        ]
        prompt = 'Choice (Enter, 1, or 2): '
        retry = 'Press Enter to keep it, type 1 to modify it, or type 2 to remove it.'
    else:
        details = ['  Only one video can be saved.'] if several else []
        details.extend(_VIDEO_RULES)
        options = [
            _choice('Enter', 'Leave this field empty'),
            _choice('1', 'Add a video'),
        ]
        prompt = 'Choice (Enter or 1): '
        retry = 'Press Enter to leave this field empty, or type 1 to add a video.'
    while True:
        _show_video_menu(details, options)
        raw = input(prompt).strip()
        if not raw:
            if current and (error := _saved_video_is_too_long(current)):
                _warn(error)
                continue
            return 'keep' if current else 'remove'
        if raw == '1':
            return 'add'
        if current and raw == '2':
            return 'remove'
        _warn(f'{retry} Please try again.')


def collect_videos(previous: dict) -> list[dict] | None:
    """Ask for one optional video, using the same prompt layout as other fields.

    Enter leaves the field empty when no video is saved, and keeps a saved video.
    ``1`` adds or modifies a video, and ``2`` removes a saved video.
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
        title = _collect_text(
            'Video title',
            current['title'] if current else None,
            VIDEO_TITLE_MAX_LENGTH,
        )
        description = _collect_text(
            'Video description',
            current['description'] if current else None,
            VIDEO_DESCRIPTION_MAX_LENGTH,
        )
        link = _collect_video_link(current['link'] if current else None)
        if link is None:
            continue
        return [{'title': title, 'description': description, 'link': link}]
