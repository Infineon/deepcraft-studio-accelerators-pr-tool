"""Interactive prompt for optional webpage links.

The menu follows the video prompt: Enter skips or keeps, and a number adds,
modifies, or removes a link. The prompt asks for a link title and a link
description. They are stored as heading and sub-heading. A second link must
use a different address. The address is an absolute https page, not a video.
"""

from __future__ import annotations

import ipaddress
from typing import Any
from urllib.parse import urlparse

import constants
from metadata.link_check import ensure_https_scheme, link_response_error
from metadata.prompts import (
    MODIFY_KEY,
    _field_separator,
    _menu_choice,
    _separator,
    field_name,
    format_custom_choice_value,
    input_prefilled,
    input_str,
    paint_blue,
    paint_yellow,
    recap_entry_indent,
)
from metadata.schema import FieldSpec

LINK_LABEL = 'Learn More'
CONTACT_LABEL = 'Contact Us'
CONTACT_HEADING = 'Contact Us'
CONTACT_SUBHEADING = (
    'Reach out to us to take the next step and turn your ideas into a reality'
)
_LINK_TRIES = 3
_LINK_INTRO = '  Add links to webpages related to the content you want to submit.'
CONTACT_INTRO = '  Add one link to a page where people can contact the company or brand.'
# The address instruction shown under a link, and under the Brand URL prompt.
PAGE_ADDRESS_HINT = 'Use an absolute https:// address to a web page.'
_PAGE_RULE = f'  {PAGE_ADDRESS_HINT}'


# Names that resolve only on a local network. A public site is not one of these.
_INTRANET_SUFFIXES = (
    '.local',
    '.localhost',
    '.internal',
    '.intranet',
    '.lan',
    '.home',
    '.home.arpa',
    '.corp',
    '.localdomain',
)
_LOCAL_ADDRESS = (
    'Local and intranet addresses are not accepted. Use a public https:// address.'
)


def link_url_error(value: str) -> str | None:
    """Links must be absolute https URLs on a public host.

    A loopback, private, or link-local address is refused, as is a single-name
    host such as ``intranet`` and a name that ends in ``.local`` or ``.lan``.
    """
    url = value.strip()
    if not url.startswith('https://') or len(url) <= len('https://'):
        return f'{value!r} is not an absolute https:// URL.'
    if any(char.isspace() for char in url):
        return 'URL must not contain spaces.'
    host = (urlparse(url).hostname or '').lower().rstrip('.')
    if not host or _is_local_or_intranet(host):
        return _LOCAL_ADDRESS
    return None


# Two-part endings, so ``example.co.uk`` is seen as a bare domain too.
_TWO_PART_SUFFIXES = frozenset({
    'co.uk', 'org.uk', 'ac.uk', 'com.au', 'co.nz', 'co.jp', 'co.kr', 'co.in',
    'co.za', 'com.cn', 'com.br', 'com.tw', 'com.hk', 'com.sg', 'com.mx',
})


def www_missing_error(value: str) -> str | None:
    """Ask for ``www.`` in front of a bare domain such as ``infineon.com``.

    A bare domain can resolve to addresses that only answer inside a company
    network, so the check never finishes. A name that already has a prefix,
    such as ``developer.infineon.com``, is left alone, because ``www.`` in front
    of it would point somewhere else. An IP address is left to the other checks.
    """
    parsed = urlparse(value.strip())
    host = (parsed.hostname or '').lower().rstrip('.')
    if not host or host.startswith('www.'):
        return None
    try:
        ipaddress.ip_address(host)
        return None
    except ValueError:
        pass
    labels = host.split('.')
    bare = 3 if '.'.join(labels[-2:]) in _TWO_PART_SUFFIXES else 2
    if len(labels) != bare:
        return None
    suggestion = ''
    if '@' not in parsed.netloc:
        suggestion = f' For example {parsed._replace(netloc="www." + parsed.netloc).geturl()}.'
    return f'The address needs www. in front of {host}.{suggestion}'


def _is_local_or_intranet(host: str) -> bool:
    if host == 'localhost' or host.endswith(_INTRANET_SUFFIXES):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return '.' not in host
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
    )


def _text_limits() -> tuple[int, int]:
    """The title prompt uses the title limit. The description prompt uses the description limit."""
    from metadata.extra_content import DESCRIPTION_MAX_LENGTH, TITLE_MAX_LENGTH

    return TITLE_MAX_LENGTH, DESCRIPTION_MAX_LENGTH


def collect_links(
    previous: dict,
    *,
    key: str = 'links',
    title: str = 'Links',
    intro: str = _LINK_INTRO,
    menu_hint: str = 'add a webpage link (recommended)',
    stored_label: str = LINK_LABEL,
    single: bool = False,
    heading_default: str | None = None,
    subheading_default: str | None = None,
    url_label: str = 'Link URL',
) -> list[dict] | None:
    """Ask for webpage links. Enter with none leaves the field out of the file.

    ``1`` adds a link, ``2`` modifies one, and ``3`` removes one. A single-link
    prompt keeps at most one. Three failed attempts on an address return to
    this prompt. ``None`` means no links.
    """
    links = _normalize_links(previous.get(key), stored_label) or []
    heading_max, subheading_max = _text_limits()
    while True:
        action, index = _choose_links(
            links, heading_max, subheading_max,
            title=title, intro=intro, menu_hint=menu_hint, single=single,
        )
        if action == 'keep':
            if not links:
                return None
            return [_stored_link(link, stored_label) for link in links]
        if action == 'add':
            link = _collect_one_link(
                None, heading_max, subheading_max,
                prompt_name=title, stored_label=stored_label,
                heading_default=heading_default, subheading_default=subheading_default,
                url_label=url_label,
            )
            if link is not None and _reject_duplicate(link, links, single=single):
                continue
            if link is not None:
                links = [link] if single else [*links, link]
            continue
        current = links[index]
        if action == 'remove':
            del links[index]
            continue
        link = _collect_one_link(
            current, heading_max, subheading_max,
            prompt_name=title, stored_label=stored_label,
            heading_default=heading_default, subheading_default=subheading_default,
            url_label=url_label,
        )
        if link is not None and _reject_duplicate(link, links, single=single, skip=index):
            continue
        if link is not None:
            links[index] = link


def collect_contact(previous: dict) -> list[dict] | None:
    """Ask for one contact link. Enter with none leaves it out of ``links``."""
    return collect_links(
        previous,
        key='contact',
        title='Contact',
        intro=CONTACT_INTRO,
        menu_hint='add one contact link (recommended)',
        stored_label=CONTACT_LABEL,
        single=True,
        heading_default=CONTACT_HEADING,
        subheading_default=CONTACT_SUBHEADING,
        url_label='Contact URL',
    )


def links_issue(
    metadata: dict,
    spec: FieldSpec,
    *,
    single: bool = False,
    stored_label: str = LINK_LABEL,
    contact_label: str | None = None,
) -> tuple[str, str] | None:
    """Check saved links. A missing list is allowed when the field is optional."""
    key = spec.key
    links = metadata.get(key)
    if links is None or links == []:
        metadata.pop(key, None)
        if spec.required:
            message = (
                f'Missing required field: {key}'
                if links is None
                else f'{key} must be a non-empty list'
            )
            return ('missing', message)
        return None
    if not isinstance(links, list):
        return ('other', f'{key} must be a list')
    if single and len(links) > 1:
        return ('other', f'{key} must contain one link')
    heading_max, subheading_max = _text_limits()
    stored: list[dict] = []
    contact_seen = 0
    for index, link in enumerate(links, start=1):
        if not isinstance(link, dict):
            return ('other', f'{key}[{index}] must be an object')
        heading = link.get('heading')
        sub_heading = link.get('sub-heading')
        url = link.get('url')
        for name, value in (('heading', heading), ('sub-heading', sub_heading), ('url', url)):
            if not isinstance(value, str) or not value.strip():
                return ('missing', f'{key}[{index}] missing or empty {name!r}')
        heading = format_custom_choice_value(heading)
        sub_heading = sub_heading.strip()
        if len(heading) > heading_max:
            return (
                'other',
                f'{key}[{index}] heading exceeds max length of {heading_max} characters '
                f'(got {len(heading)})',
            )
        if len(sub_heading) > subheading_max:
            return (
                'other',
                f'{key}[{index}] sub-heading exceeds max length of {subheading_max} '
                f'characters (got {len(sub_heading)})',
            )
        error = link_url_error(url) or www_missing_error(url)
        if error:
            return ('other', f'{key}[{index}] url: {error}')
        if any(
            saved['url'].strip().casefold() == url.strip().casefold()
            for saved in stored
        ):
            return ('other', f'{key}[{index}] repeats an earlier link')
        raw_label = link.get('label')
        is_contact = (
            contact_label is not None
            and isinstance(raw_label, str)
            and raw_label.strip().casefold() == contact_label.casefold()
        )
        if is_contact:
            contact_seen += 1
            if contact_seen > 1:
                return ('other', f'{key} can contain only one contact link')
        stored.append(_stored_link({
            'heading': heading,
            'sub-heading': sub_heading,
            'url': url,
        }, contact_label if is_contact else stored_label))
    metadata[key] = stored
    return None


def _stored_link(link: dict, label: str = LINK_LABEL) -> dict:
    return {
        'label': label,
        'url': link['url'].strip(),
        'heading': link['heading'],
        'sub-heading': link['sub-heading'],
    }


def _normalize_links(value: Any, label: str = LINK_LABEL) -> list[dict] | None:
    if not isinstance(value, list) or not value:
        return None
    links: list[dict] = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        heading = entry.get('heading')
        sub_heading = entry.get('sub-heading')
        url = entry.get('url')
        if not all(isinstance(item, str) and item.strip() for item in (heading, sub_heading, url)):
            continue
        links.append({
            'label': label,
            'url': url.strip(),
            'heading': format_custom_choice_value(heading),
            'sub-heading': sub_heading.strip(),
        })
    return links or None


def _collect_one_link(
    current: dict | None,
    heading_max: int,
    subheading_max: int,
    *,
    prompt_name: str = 'Links',
    stored_label: str = LINK_LABEL,
    heading_default: str | None = None,
    subheading_default: str | None = None,
    url_label: str = 'Link URL',
) -> dict | None:
    """Collect one link. ``None`` returns to the link menu."""
    heading = format_custom_choice_value(input_str(
        'Link title',
        heading_max,
        default=current['heading'] if current else heading_default,
    ))
    sub_heading = input_str(
        'Link description',
        subheading_max,
        default=current['sub-heading'] if current else subheading_default,
    )
    url = _collect_link_url(
        current['url'] if current else None,
        prompt_name=prompt_name,
        url_label=url_label,
    )
    if url is None:
        return None
    return _stored_link(
        {'heading': heading, 'sub-heading': sub_heading, 'url': url},
        stored_label,
    )


def _link_address(link: dict) -> str:
    """The address that decides whether two links are the same."""
    return link['url'].strip().casefold()


def _reject_duplicate(
    link: dict,
    links: list[dict],
    *,
    single: bool,
    skip: int | None = None,
) -> bool:
    """Warn and return True when *link* repeats an address already in *links*.

    A one-link prompt has nothing to compare against. *skip* is the entry being
    modified, so a link is not a duplicate of itself.
    """
    if single:
        return False
    address = _link_address(link)
    if any(index != skip and _link_address(saved) == address for index, saved in enumerate(links)):
        _link_warn('That link is already in the list. Use a different address.')
        return True
    return False


def _link_warn(message: str) -> None:
    print(paint_yellow(f'{constants.ICON_WARNING} {message}'))


def _keep_lines(default: str) -> list[str]:
    return [
        _separator('-'),
        f'  {constants.ICON_WARNING} {paint_yellow("Current value:")} {default}',
        _separator('-'),
        '  Choose an option:',
        _menu_choice('Enter', 'Keep the current value'),
        _menu_choice(MODIFY_KEY, 'Modify the current value'),
    ]


def _read_prompt(name: str, lines: list[str]) -> str:
    body = ''.join(f'{line}\n' for line in lines)
    return input(f'{_separator("=")}\n{name}\n{body}{_separator("-")}\n: ').strip()


def _link_lines(default: str | None, attempts: int) -> list[str]:
    lines = [_PAGE_RULE] if default else ['  Add a web page address.']
    lines.append(f'  Attempts: {attempts} of {_LINK_TRIES}')
    if default:
        lines.extend(_keep_lines(default))
    return lines


def _collect_link_url(
    default: str | None = None,
    *,
    prompt_name: str = 'Links',
    url_label: str = 'Link URL',
) -> str | None:
    """Return an https page address, or ``None`` to show the link menu again."""
    attempts = 0
    while True:
        raw = _read_prompt(field_name(url_label), _link_lines(default, attempts))
        if default and raw == MODIFY_KEY:
            link = input_prefilled(': ', default, read=input).strip()
        elif default and raw:
            _link_warn('Press Enter to keep it, or type 1 to modify it. Please try again.')
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
            link = ensure_https_scheme(link)
            error = (
                link_url_error(link)
                or www_missing_error(link)
                or link_response_error(link)
            )
        if error is None:
            return link
        attempts += 1
        if attempts >= _LINK_TRIES:
            _link_warn(f'Returning to the {prompt_name} prompt. (attempt {attempts} of {_LINK_TRIES})')
            return None
        _link_warn(f'{error} ({attempts} of {_LINK_TRIES})')


def _show_link_menu(
    details: list[str],
    options: list[str],
    *,
    title: str,
    hint: str = '',
) -> None:
    rule = _separator('-')
    print(_field_separator())
    label = field_name(title)
    print(f'{label} - {hint}' if hint else label)
    print(rule)
    for line in details:
        print(line)
    print(rule)
    print('  Choose an option:')
    for option in options:
        print(option)
    print(rule)


def _choose_links(
    links: list[dict],
    heading_max: int,
    subheading_max: int,
    *,
    title: str,
    intro: str,
    menu_hint: str,
    single: bool,
) -> tuple[str, int]:
    """Return ``keep``, ``add``, ``modify``, or ``remove``, and a link index."""
    while True:
        listed = _listed_links(links)
        if single and links:
            details = [intro, *listed]
            options = [
                _menu_choice('1', 'Modify the contact link' if len(links) == 1 else 'Modify a contact link'),
                _menu_choice('2', 'Remove the contact link' if len(links) == 1 else 'Remove a contact link'),
            ]
            if len(links) == 1:
                options = [_menu_choice('Enter', 'Keep this contact link'), *options]
                prompt = 'Choice (Enter, 1, or 2): '
                retry = 'Press Enter to keep it, 1 to modify it, or 2 to remove it.'
            else:
                prompt = 'Choice (1 or 2): '
                retry = 'Only one contact link can be saved. Type 1 to modify one, or 2 to remove one.'
        elif links:
            details = [intro, *listed]
            options = [
                _menu_choice('Enter', 'Keep these links'),
                _menu_choice('1', 'Add a link'),
                _menu_choice('2', 'Modify a link'),
                _menu_choice('3', 'Remove a link'),
            ]
            prompt = 'Choice (Enter, 1, 2, or 3): '
            retry = 'Press Enter to keep them, 1 to add, 2 to modify, or 3 to remove.'
        else:
            details = [intro, _PAGE_RULE]
            add_text = 'Add a contact link' if single else 'Add a link'
            options = [
                _menu_choice('Enter', 'No contact link to add' if single else 'No link to add'),
                _menu_choice('1', add_text),
            ]
            prompt = 'Choice (Enter or 1): '
            retry = (
                'Press Enter if there is no contact link to add, or type 1 to add one.'
                if single
                else 'Press Enter if there is no link to add, or type 1 to add a link.'
            )
        _show_link_menu(details, options, title=title, hint=menu_hint)
        raw = input(prompt).strip()
        if not raw:
            if single and len(links) > 1:
                _link_warn(f'{retry} Please try again.')
                continue
            if links and (error := _saved_links_are_too_long(links, heading_max, subheading_max)):
                _link_warn(error)
                continue
            modify_key = '1' if single else '2'
            if links and (error := _saved_links_need_www(links, modify_key=modify_key)):
                _link_warn(error)
                continue
            return 'keep', 0
        if single and links:
            if raw in ('1', '2'):
                index = 0 if len(links) == 1 else _link_index(len(links))
                if index is None:
                    continue
                return ('modify' if raw == '1' else 'remove', index)
        elif raw == '1':
            return 'add', 0
        elif links and raw in ('2', '3'):
            index = _link_index(len(links))
            if index is None:
                continue
            return ('modify' if raw == '2' else 'remove', index)
        _link_warn(f'{retry} Please try again.')


def _listed_links(links: list[dict]) -> list[str]:
    """One block per link, numbered like a metric recap.

    The title line starts at the left. The description and the address are
    indented under that number. A grey rule separates links. The address stays
    blue. The recap says title and description. The file stores those words as
    heading and sub-heading.
    """
    lines: list[str] = []
    rule = _separator('-')
    for number, link in enumerate(links, start=1):
        if number > 1:
            lines.append(rule)
        indent = recap_entry_indent(number)
        lines.append(f'{number}. Title: {link["heading"]}')
        lines.append(f'{indent}Description: {link["sub-heading"]}')
        lines.append(f'{indent}Link: {paint_blue(link["url"])}')
    return lines


def _link_index(count: int) -> int | None:
    raw = input(f'Link number (1 to {count}): ').strip()
    if raw.isdigit() and 1 <= int(raw) <= count:
        return int(raw) - 1
    _link_warn(f'Type a number between 1 and {count}.')
    return None


def _saved_links_need_www(links: list[dict], *, modify_key: str) -> str | None:
    """Refuse Enter on a saved address that still needs ``www.`` or another prefix."""
    for number, link in enumerate(links, start=1):
        if error := www_missing_error(link['url']):
            return f'Link {number}: {error} Type {modify_key} to modify it.'
    return None


def _saved_links_are_too_long(
    links: list[dict],
    heading_max: int,
    subheading_max: int,
) -> str | None:
    for number, link in enumerate(links, start=1):
        if len(link['heading']) > heading_max:
            return (
                f'Link {number} title is more than {heading_max} characters. '
                'Type 2 to modify it.'
            )
        if len(link['sub-heading']) > subheading_max:
            return (
                f'Link {number} description is more than {subheading_max} characters. '
                'Type 2 to modify it.'
            )
    return None
