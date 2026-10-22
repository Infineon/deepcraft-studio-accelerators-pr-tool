"""Interactive prompt for the optional videos field."""

import re
import unicodedata
from typing import Any

import constants
from metadata.prompts import _separator, confirm, input_str
from metadata.video_link import duplicate_video_link_error, video_link_error


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


def _collect_video_link(default: str | None = None, taken: list[str] | None = None) -> str:
    print(
        '  Single video URL only (for example https://youtu.be/...). '
        'Playlists and regular web pages are not allowed.',
    )
    already = list(taken or [])
    while True:
        link = input_str('Video link', default=default)
        error = video_link_error(link) or duplicate_video_link_error(link, already)
        if error is None:
            return link
        print(f'{constants.ICON_WARNING} {error}')


def _collect_video_text(name: str, default: str | None) -> str:
    while True:
        value = normalize_video_text(input_str(name, default=default))
        if value:
            return value
        print(f'{constants.ICON_WARNING} Value cannot be empty, please try again.')


def _collect_video(heading: str, defaults: dict, taken: list[str]) -> dict:
    print(f'\n{heading}')
    return {
        'title': _collect_video_text('Video title', defaults.get('title')),
        'description': _collect_video_text('Video description', defaults.get('description')),
        'link': _collect_video_link(defaults.get('link'), taken=taken),
    }


def _video_problems(videos: list[dict]) -> dict[int, str]:
    """Map list positions to the reason that video cannot be kept."""
    problems: dict[int, str] = {}
    seen: list[str] = []
    for position, video in enumerate(videos):
        error = video_link_error(video['link']) or duplicate_video_link_error(video['link'], seen)
        if error:
            problems[position] = error
        else:
            seen.append(video['link'])
    return problems


def _show_video_menu(videos: list[dict], problems: dict[int, str]) -> None:
    print(_separator('='))
    if videos:
        print('Videos')
        for index, video in enumerate(videos, start=1):
            print(f'  {index}. {video["title"]} — {video["link"]}')
            if index - 1 in problems:
                print(f'     {constants.ICON_WARNING} {problems[index - 1]}')
    else:
        print('Videos (none)')
    print(_separator('-'))
    if videos:
        print('  Enter   keep the videos listed above and continue')
        numbers = '1' if len(videos) == 1 else f'1-{len(videos)}'
        print(f'  {numbers:<8}edit that video')
        print('  d<N>    delete video N (for example d2)')
    else:
        print('  Enter   continue without videos')
    print('  a       add a new video')
    if videos:
        print('  n       erase all videos')
    print(_separator('-'))


def _video_number(raw: str, videos: list[dict]) -> int | None:
    if raw.isdigit() and 1 <= int(raw) <= len(videos):
        return int(raw) - 1
    return None


def _manage_videos(videos: list[dict]) -> list[dict] | None:
    while True:
        problems = _video_problems(videos)
        _show_video_menu(videos, problems)
        raw = input(': ').strip().lower()
        if not raw:
            if problems:
                print(
                    f'{constants.ICON_WARNING} Edit or delete the videos marked above '
                    'before continuing.',
                )
                continue
            return videos or None
        if raw == 'a':
            videos.append(_collect_video(
                f'Video {len(videos) + 1}',
                {},
                taken=[video['link'] for video in videos],
            ))
            continue
        if raw == 'n' and videos:
            if confirm(f'Erase all {len(videos)} video(s)?'):
                videos = []
            continue
        if raw.startswith('d') and (position := _video_number(raw[1:].strip(), videos)) is not None:
            removed = videos.pop(position)
            print(f'{constants.ICON_SUCCESS} Deleted video: {removed["title"]}')
            continue
        position = _video_number(raw, videos)
        if position is not None:
            videos[position] = _collect_video(
                f'Edit video {position + 1}',
                videos[position],
                taken=[video['link'] for index, video in enumerate(videos) if index != position],
            )
            continue
        print(f'{constants.ICON_WARNING} Unknown option {raw!r}. Choose one of the options listed.')


def _ask(question: str) -> bool:
    """Ask a yes/no question on its own, below the field that came before it."""
    print()
    print(_separator('-'))
    return confirm(question)


def collect_videos(previous: dict, *, review: bool = False) -> list[dict] | None:
    """Ask for zero or more videos, then let the user keep, edit, add, or delete them.

    During a metadata redo, saved videos stay as they are unless the user asks
    to change them. A saved video with a bad or repeated link still has to be fixed.
    """
    existing = _normalize_videos(previous.get('videos'))
    if existing is None:
        if not _ask('Add videos? (optional — answer n to skip)'):
            return None
        existing = [_collect_video('Video 1', {}, taken=[])]
    elif review and not _ask('Change existing videos?'):
        if not _video_problems(existing):
            return existing
        print(
            f'{constants.ICON_WARNING} Existing videos still need to be edited or deleted '
            'before they can be kept.',
        )
    return _manage_videos(existing)
