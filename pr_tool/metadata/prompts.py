"""Interactive prompts for metadata collection."""

import os
import re
import shutil
import sys
from argparse import _ArgumentGroup
from typing import Callable

import constants
from metadata.choices import canonical_choice, match_choice

_GREEN = '\033[32m'
_YELLOW = '\033[33m'
_CYAN = '\033[36m'
_GREY = '\033[90m'
_MAGENTA = '\033[35m'
_RESET = '\033[0m'
_WINDOWS_STD_OUTPUT_HANDLE = -11
_WINDOWS_ENABLE_VIRTUAL_TERMINAL = 0x0004


def _enable_windows_virtual_terminal() -> bool:
    """Let the Windows console read ANSI colour codes. Return False if it cannot."""
    import ctypes

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.GetStdHandle(_WINDOWS_STD_OUTPUT_HANDLE)
    mode = ctypes.c_uint32()
    if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
        return False
    return bool(kernel32.SetConsoleMode(handle, mode.value | _WINDOWS_ENABLE_VIRTUAL_TERMINAL))


def _colour_enabled() -> bool:
    """Colour only for a real terminal, and never when ``NO_COLOR`` is set."""
    if os.environ.get('NO_COLOR') or not sys.stdout.isatty():
        return False
    if os.name == 'nt':
        return _enable_windows_virtual_terminal()
    return True


def _paint(text: str, code: str) -> str:
    """Wrap *text* in colour *code* when the terminal supports it; otherwise return it unchanged."""
    if _colour_enabled():
        return f'{code}{text}{_RESET}'
    return text


def paint_green(text: str) -> str:
    """Colour *text* green (field names and product words)."""
    return _paint(text, _GREEN)


def paint_yellow(text: str) -> str:
    """Colour *text* yellow (the ``Current value`` label and retry messages)."""
    return _paint(text, _YELLOW)


def paint_cyan(text: str) -> str:
    """Colour *text* cyan (the keys and list numbers the user types)."""
    return _paint(text, _CYAN)


def paint_grey(text: str) -> str:
    """Colour *text* grey (the inner separator lines)."""
    return _paint(text, _GREY)


def paint_magenta(text: str) -> str:
    """Colour *text* magenta, for other highlighted items such as ``metadata.json``."""
    return _paint(text, _MAGENTA)




def colour_key_line() -> str:
    """One line under the metadata header explaining what each colour means."""
    return (
        f'  Color Code: {paint_green("green")} field names, '
        f'{paint_cyan("cyan")} choices, options, and the field counter, '
        f'{paint_yellow("yellow")} current values and warnings, '
        f'{paint_magenta("magenta")} others.'
    )


def warn(message: str) -> None:
    """Print a retry or problem message in yellow."""
    print(paint_yellow(f'{constants.ICON_WARNING} {message}'))


def paint_words(text: str, words: tuple[str, ...]) -> str:
    """Colour each of *words* green inside *text*; the rest of the text is unchanged."""
    for word in words:
        text = text.replace(word, paint_green(word))
    return text


# The field currently being collected, as ``(label, index, total)``.
_field_progress: tuple[str, int, int] | None = None


def set_field_progress(label: str | None, index: int = 0, total: int = 0) -> None:
    """Mark the field whose prompt should show ``(index/total)``. ``None`` clears it."""
    global _field_progress
    if label is None or total <= 0:
        _field_progress = None
        return
    _field_progress = (label, index, total)


def _progress_mark() -> str:
    """The ``(2/9)`` counter in cyan, or plain text when colour is off."""
    if _field_progress is None:
        return ''
    _, index, total = _field_progress
    return paint_cyan(f'({index}/{total})')


def field_progress_prefix() -> str:
    """``(2/9) `` for a derived line that stands in for the field prompt."""
    mark = _progress_mark()
    return f'{mark} ' if mark else ''


def _progress_suffix(text: str) -> str:
    if _field_progress is None:
        return ''
    label = _field_progress[0]
    folded = text.casefold()
    if folded not in (label.casefold(), f'{label}(s)'.casefold()):
        return ''
    return f' {_progress_mark()}'


def field_name(text: str) -> str:
    """Show a prompt's field name in green capitals; plain text when colour is off.

    The field being collected also gets its place in the form, such as ``(2/9)``.
    """
    shown = paint_green(text.upper()) if _colour_enabled() else text
    return f'{shown}{_progress_suffix(text)}'


def format_custom_choice_value(value: str) -> str:
    """Capitalize the first letter of each word in a custom choice value."""
    return re.sub(
        r'\b([a-z])',
        lambda match: match.group(1).upper(),
        value.strip(),
    )


def arg_validator(max_len: int) -> Callable[[str], str]:
    def validate_arg(value: str) -> str:
        if not value:
            raise ValueError('Value is empty')
        if len(value) > max_len:
            raise ValueError(f'Value is more than {max_len} characters')
        return value

    return validate_arg


def _separator(char: str) -> str:
    """A full-width rule inside a field prompt. Grey, so the field's own name stands out."""
    width = shutil.get_terminal_size((80, 24)).columns
    return paint_grey(char * width)


def _field_separator() -> str:
    """The white ``====`` rule that starts each main field prompt, uncoloured."""
    width = shutil.get_terminal_size((80, 24)).columns
    return '=' * width


def _menu_choice(key: str, text: str) -> str:
    """One menu row. Numbers use the same ``1.`` form as the other prompts.

    The key is padded before it is coloured, so the description stays aligned
    on Windows, where the colour codes are not visible characters.
    """
    label = 'Enter' if key == 'Enter' else f'{key}.'
    return paint_cyan(f'  {label}'.ljust(12)) + text


MODIFY_KEY = '1'
NEW_VALUE_KEY = '2'
_NEW_VALUE_NOTE = 'Enter a new value only if none of the listed options fits'


def _custom_value_note(allow_custom: bool) -> str:
    """The reminder under a choice header, when a value outside the list is allowed."""
    return f'{_NEW_VALUE_NOTE}\n' if allow_custom else ''


def _saved_text_rows(*, allow_new: bool = True) -> list[str]:
    """Modify row for a saved value, plus type-new when a new value is allowed."""
    rows = [_menu_choice(MODIFY_KEY, 'Modify the current value')]
    if allow_new:
        rows.append(_menu_choice(NEW_VALUE_KEY, 'Type a new value'))
    return rows


def _queue_windows_console_text(text: str) -> bool:
    """Type *text* into the Windows console so the next ``input()`` can edit it."""
    import ctypes
    from ctypes import wintypes

    class _KeyEvent(ctypes.Structure):
        _fields_ = [
            ('bKeyDown', wintypes.BOOL),
            ('wRepeatCount', wintypes.WORD),
            ('wVirtualKeyCode', wintypes.WORD),
            ('wVirtualScanCode', wintypes.WORD),
            ('uChar', wintypes.WCHAR),
            ('dwControlKeyState', wintypes.DWORD),
        ]

    class _Event(ctypes.Union):
        _fields_ = [('KeyEvent', _KeyEvent)]

    class _InputRecord(ctypes.Structure):
        _fields_ = [('EventType', wintypes.WORD), ('Event', _Event)]

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.GetStdHandle(-10)
    mode = wintypes.DWORD()
    if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
        return False
    units = text.encode('utf-16-le')
    chars = [units[i:i + 2].decode('utf-16-le', 'surrogatepass') for i in range(0, len(units), 2)]
    records = (_InputRecord * (len(chars) * 2))()
    for index, char in enumerate(chars):
        for offset, key_down in ((0, True), (1, False)):
            record = records[index * 2 + offset]
            record.EventType = 0x0001
            record.Event.KeyEvent.bKeyDown = key_down
            record.Event.KeyEvent.wRepeatCount = 1
            record.Event.KeyEvent.uChar = char
    written = wintypes.DWORD()
    ok = kernel32.WriteConsoleInputW(handle, records, len(records), ctypes.byref(written))
    return bool(ok) and written.value == len(records)


def queue_line_for_editing(text: str) -> bool:
    """Put *text* on the next input line. Return False when the terminal cannot do it."""
    if not text:
        return False
    try:
        if not sys.stdin.isatty():
            return False
        if os.name == 'nt':
            return _queue_windows_console_text(text)
        import readline
    except (ImportError, OSError, AttributeError, ValueError):
        return False
    readline.set_startup_hook(lambda: readline.insert_text(text))
    return True


def input_prefilled(prompt: str, text: str, read: Callable[[str], str] | None = None) -> str:
    """Ask again with *text* already on the input line, so the user can edit it."""
    ask = read or input
    placed = queue_line_for_editing(text)
    if not placed:
        print(f'  {constants.ICON_WARNING} {paint_yellow("Current value:")} {text}')
        print('  Type the new value, or copy it from above.')
    try:
        return ask(prompt)
    finally:
        if placed and os.name != 'nt':
            import readline
            readline.set_startup_hook()


def _numbers_for_saved(selected: list[str], choices: list[str]) -> str:
    """List numbers for a saved selection, so Modify starts from ``1, 2``.

    A value that is not in the list stays as typed.
    """
    numbers = {choice: index for index, choice in enumerate(choices, start=1)}
    parts: list[str] = []
    for item in selected:
        number = numbers.get(item)
        if number is None:
            canonical = canonical_choice(item, choices)
            if canonical is not None:
                number = numbers.get(canonical)
        parts.append(str(number) if number is not None else item)
    return ', '.join(parts)


def _value_after_saved_menu(raw: str, current: str, *, allow_new: bool = True) -> str | None:
    """Read the replacement for a saved value. ``None`` means ask again.

    ``1`` places *current* on the input line. ``2`` starts a blank entry when a
    new value is allowed. Any other answer is refused, so a stray keystroke
    cannot replace the saved value.
    """
    if raw == MODIFY_KEY:
        return input_prefilled(': ', current).strip()
    if allow_new and raw == NEW_VALUE_KEY:
        return input(': ').strip()
    if allow_new:
        warn(
            'Press Enter to keep it, type 1 to modify it, '
            'or type 2 to type a new value. Please try again.'
        )
    else:
        warn('Press Enter to keep it, or type 1 to modify it. Please try again.')
    return None


def _saved_value_block(value: str, extra: list[str] | None = None) -> str:
    """List Enter under the field so a saved value stays on screen.

    ``extra`` rows, such as numbered choices, are listed with Enter.
    """
    rule = _separator('-')
    rows = [_menu_choice('Enter', 'Keep the current value'), *(extra or [])]
    listed = '\n'.join(rows)
    return (
        f'{rule}\n'
        f'  {constants.ICON_WARNING} {paint_yellow("Current value:")} {value}\n'
        f'{rule}\n'
        f'  Choose an option:\n'
        f'{listed}\n'
        f'{rule}\n'
    )


def _format_choices(choices: list[str]) -> str:
    n = len(choices)
    if n == 0:
        return ''
    number_width = len(str(n))
    numbers = [f'{i + 1:>{number_width}}.' for i in range(n)]
    entries = [f'{numbers[i]} {choice}' for i, choice in enumerate(choices)]
    col_width = max(len(e) for e in entries) + constants.COLUMN_PADDING
    term_width = shutil.get_terminal_size((80, 24)).columns
    num_cols = max(1, term_width // col_width)
    num_rows = (n + num_cols - 1) // num_cols
    rows: list[str] = []
    for row in range(num_rows):
        cells = []
        for col in range(num_cols):
            idx = col * num_rows + row
            if idx < n:
                padded = entries[idx].ljust(col_width)
                cells.append(paint_cyan(numbers[idx]) + padded[len(numbers[idx]):])
        rows.append(''.join(cells).rstrip())
    return '\n'.join(rows)


def input_str(name: str, max_len: int | None = None, default: str | None = None) -> str:
    top_sep = _field_separator()
    bottom_sep = _separator('-')
    limit_line = f' (max {max_len} characters)' if max_len is not None else ''
    saved = (
        _saved_value_block(default, _saved_text_rows())
        if default
        else f'{bottom_sep}\n'
    )
    prompt = (
        f'{top_sep}\n'
        f'{field_name(name)}{limit_line}\n'
        f'{saved}'
        f': '
    )
    while True:
        value = input(prompt).strip()
        if default:
            if not value:
                return default
            value = _value_after_saved_menu(value, default)
            if value is None:
                continue
        if not value:
            warn(f'Value cannot be empty, please try again.')
            continue
        if max_len is not None and len(value) > max_len:
            warn(f'Value is more than {max_len} characters, please try again.')
            continue
        return value


def confirm(question: str) -> bool:
    """Ask a yes/no question; loop until the user types y/yes or n/no."""
    while True:
        answer = input(f'{question} (y/n): ').strip().lower()
        if answer in ('y', 'yes'):
            return True
        if answer in ('n', 'no'):
            return False
        warn("Please answer 'y' or 'n'.")


def _choice_menu(question: str, options: list[tuple[str, str]]) -> str:
    """A question with menu rows, using the same rules as the other prompts."""
    top_sep = _field_separator()
    bottom_sep = _separator('-')
    rows = '\n'.join(_menu_choice(key, text) for key, text in options)
    return (
        f'{top_sep}\n'
        f'{question}\n'
        f'{bottom_sep}\n'
        f'  Choose an option:\n'
        f'{rows}\n'
        f'{bottom_sep}\n'
        f': '
    )


def confirm_menu(question: str, *, yes: str, no: str) -> bool:
    """Yes/no question shown as a menu. ``y`` returns True."""
    prompt = _choice_menu(question, [('y', yes), ('n', no)])
    while True:
        answer = input(prompt).strip().lower()
        if answer in ('y', 'yes'):
            return True
        if answer in ('n', 'no'):
            return False
        warn("Please answer 'y' or 'n'.")


def confirm_metadata(*, save_on_yes: bool = False) -> str:
    """Returns ``'yes'``, ``'no'`` (modify), or ``'abort'``.

    The question is a menu. With *save_on_yes*, the yes row says it saves metadata.json.
    """
    yes_text = 'Yes, save metadata.json' if save_on_yes else 'Yes, keep these values'
    prompt = _choice_menu(
        'Proceed with this metadata?',
        [
            ('y', yes_text),
            ('n', 'Modify the metadata'),
            ('a', 'Abort without saving'),
        ],
    )
    while True:
        answer = input(prompt).strip().lower()
        if answer in ('y', 'yes'):
            return 'yes'
        if answer in ('n', 'no'):
            return 'no'
        if answer in ('a', 'abort'):
            return 'abort'
        warn("Please answer 'y', 'n', or 'a'.")


def confirm_new_value(value: str, kind: str, *, only_if_necessary: bool = False) -> bool:
    if only_if_necessary:
        return confirm(
            f'"{value}" is not in the {kind} list. '
            f'Add it only if none of the listed options fits. Use it anyway?',
        )
    return confirm(f'"{value}" is not in the suggested {kind} list. Use it anyway?')


def _resolve_custom_choice(raw: str, choices: list[str]) -> str | None:
    """Return a catalog match for a custom entry, tolerating case, trademark, and spacing."""
    formatted = format_custom_choice_value(raw)
    if formatted in choices:
        return formatted
    return match_choice(raw, choices)


def _listed_number(token: str, count: int, *, allow_custom: bool) -> int | None:
    """Read a token that is only a number.

    Returns the 1-based choice when it is in the list. Returns ``0`` after a
    warning when the number is outside the list, so the caller asks again.
    Returns ``None`` when *token* is not just a number.

    A trailing mark such as ``15.`` still counts as the number ``15``. On a
    field that accepts new options, a number above the list is refused instead
    of being stored as a new option.
    """
    text = token.strip().rstrip('.,;:')
    if not text.isnumeric():
        return None
    number = int(text)
    if 1 <= number <= count:
        return number
    if number > count and allow_custom:
        warn(
            f'Number {text} is higher than {count}, the highest choice in this list. '
            'A new option cannot be a number above the list. Please try again.'
        )
    else:
        warn(f'Number {text} is not between 1 and {count}.')
    return 0


def _format_grouped_choices(groups: list[tuple[str, list[str]]]) -> str:
    lines: list[str] = []
    index = 1
    number_width = len(str(sum(len(items) for _, items in groups)))
    for heading, choices in groups:
        lines.append(heading)
        for choice in choices:
            number = f'{index:>{number_width}}.'
            lines.append(f'  {paint_cyan(number)} {choice}')
            index += 1
    return '\n'.join(lines)


def _column_sizes(count: int, limit: int = 4) -> list[int]:
    """Split *count* items into columns of at most *limit*, as evenly as possible."""
    if count <= limit:
        return [count]
    column_count = (count + limit - 1) // limit
    base, remainder = divmod(count, column_count)
    return [base + 1] * remainder + [base] * (column_count - remainder)


def _format_domain_choices(groups: list[tuple[str, list[str]]]) -> str:
    """Domains side by side, sensors listed downward under each magenta heading.

    A domain with more than four sensors continues in the next columns, three or
    four sensors each. The heading is shown on the first of those columns, and
    the sensor number starts in the same column as that heading.
    A further row of domains starts below when the next column does not fit
    the terminal width.
    """
    columns: list[list[tuple[str, str]]] = []
    index = 1
    for heading, items in groups:
        offset = 0
        for column_number, size in enumerate(_column_sizes(len(items))):
            if column_number == 0:
                column = [(heading, paint_magenta(heading))]
            else:
                column = [('', '')]
            for item in items[offset:offset + size]:
                number = f'{index}.'
                column.append((f'{number} {item}', f'{paint_cyan(number)} {item}'))
                index += 1
            offset += size
            columns.append(column)
    if not columns:
        return ''
    widths = [max(len(plain) for plain, _ in column) for column in columns]
    gap = constants.COLUMN_PADDING
    term_width = shutil.get_terminal_size((80, 24)).columns
    bands: list[list[int]] = []
    current: list[int] = []
    used = 0
    for column_index, width in enumerate(widths):
        extra = width if not current else gap + width
        if current and used + extra > term_width:
            bands.append(current)
            current = [column_index]
            used = width
        else:
            current.append(column_index)
            used += extra
    if current:
        bands.append(current)
    rendered: list[str] = []
    for band_index, band in enumerate(bands):
        if band_index:
            rendered.append('')
        height = max(len(columns[column_index]) for column_index in band)
        for row in range(height):
            cells: list[str] = []
            for position, column_index in enumerate(band):
                column = columns[column_index]
                pad = widths[column_index]
                painted = ''
                if row < len(column):
                    plain, painted = column[row]
                    pad -= len(plain)
                if position < len(band) - 1:
                    pad += gap
                cells.append(painted + (' ' * pad))
            rendered.append(''.join(cells).rstrip())
    return '\n'.join(rendered)


def input_grouped_choice(
    name: str,
    groups: list[tuple[str, list[str]]],
    default: str | None = None,
    *,
    allow_custom: bool = True,
) -> str:
    """Prompt for one value from labelled choice groups (e.g. Infineon vs partner brands)."""
    choices = [item for _, items in groups for item in items]
    choices_sub_list = _format_grouped_choices(groups)
    range_str = f'between 1 and {len(choices)}'
    top_sep = _field_separator()
    bottom_sep = _separator('-')
    saved = (
        _saved_value_block(default, _saved_text_rows(allow_new=allow_custom))
        if default
        else f'{bottom_sep}\n'
    )
    hint = (
        f'type a number {range_str} or enter a new name'
        if allow_custom
        else f'type a number {range_str} or a listed name'
    )
    prompt = (
        f'{top_sep}\n'
        f'{field_name(name)} - {hint}\n'
        f'{_custom_value_note(allow_custom)}'
        f'{choices_sub_list}\n'
        f'{saved}'
        f': '
    )
    while True:
        raw = input(prompt).strip()
        if default:
            if not raw:
                return default
            raw = _value_after_saved_menu(
                raw,
                _numbers_for_saved([default], choices),
                allow_new=allow_custom,
            )
            if raw is None:
                continue
        if not raw:
            warn(f'Value cannot be empty, please try again.')
            continue
        number = _listed_number(raw, len(choices), allow_custom=allow_custom)
        if number == 0:
            continue
        if number is not None:
            return choices[number - 1]
        if raw in choices:
            return raw
        resolved = _resolve_custom_choice(raw, choices)
        if resolved is not None:
            return resolved
        formatted = format_custom_choice_value(raw)
        if allow_custom and confirm_new_value(formatted, name.lower()):
            return formatted
        warn(f'"{raw}" is not in the list, please try again.')


def input_choice(
    name: str,
    choices: list[str],
    default: str | None = None,
    *,
    allow_custom: bool = True,
    coloured_name: bool = True,
) -> str:
    choices_sub_list = _format_choices(choices)
    range_str = f'between 1 and {len(choices)}'
    top_sep = _field_separator()
    saved = (
        _saved_value_block(default, _saved_text_rows(allow_new=allow_custom))
        if default
        else f'{_separator("-")}\n'
    )
    header_name = field_name(name) if coloured_name else name.upper()
    hint = (
        f'type a number {range_str} or enter a new name'
        if allow_custom
        else f'type a number {range_str} or a listed name'
    )
    print(
        f'{top_sep}\n'
        f'{header_name} - {hint}\n'
        f'{_custom_value_note(allow_custom)}'
        f'{choices_sub_list}'
    )
    while True:
        raw = input(f'{saved}: ').strip()
        if default:
            if not raw:
                return default
            raw = _value_after_saved_menu(
                raw,
                _numbers_for_saved([default], choices),
                allow_new=allow_custom,
            )
            if raw is None:
                continue
        if not raw:
            warn(f'Value cannot be empty, please try again.')
            continue
        number = _listed_number(raw, len(choices), allow_custom=allow_custom)
        if number == 0:
            continue
        if number is not None:
            return choices[number - 1]
        if raw in choices:
            return raw
        resolved = _resolve_custom_choice(raw, choices)
        if resolved is not None:
            return resolved
        formatted = format_custom_choice_value(raw)
        if allow_custom and confirm_new_value(formatted, name.lower()):
            return formatted
        warn(f'"{raw}" is not in the list, please try again.')


def _parse_multi_choice(
    raw: str,
    choices: list[str],
    name: str,
    *,
    allow_custom: bool,
    prefer_listed: bool,
    range_str: str,
) -> list[str] | None:
    """Turn a comma-separated answer into choices. ``None`` asks again."""
    tokens = [token.strip() for token in raw.split(',') if token.strip()]
    if not tokens:
        warn(f'Value cannot be empty, please try again.')
        return None
    results: list[str] = []
    for token in tokens:
        number = _listed_number(token, len(choices), allow_custom=allow_custom)
        if number == 0:
            return None
        if number is not None:
            results.append(choices[number - 1])
            continue
        if token in choices:
            results.append(token)
            continue
        resolved = _resolve_custom_choice(token, choices)
        if resolved is not None:
            results.append(resolved)
            continue
        if not allow_custom:
            warn(f'"{token}" is not in the list, please try again.')
            return None
        formatted = format_custom_choice_value(token)
        if not confirm_new_value(formatted, name.lower(), only_if_necessary=prefer_listed):
            return None
        results.append(formatted)
    deduped = list(dict.fromkeys(results))
    if not deduped:
        warn(f'You must choose at least one {name.lower()}, please try again.')
        return None
    return deduped


def input_choices(
    name: str,
    choices: list[str],
    default: list[str] | None = None,
    *,
    allow_custom: bool = True,
    prefer_listed: bool = False,
    coloured_name: bool = True,
    groups: list[tuple[str, list[str]]] | None = None,
) -> list[str]:
    if groups:
        choices = [item for _, items in groups for item in items]
        choices_sub_list = _format_domain_choices(groups)
    else:
        choices_sub_list = _format_choices(choices)
    range_str = f'between 1 and {len(choices)}'
    top_sep = _field_separator()
    saved = (
        _saved_value_block(', '.join(default), _saved_text_rows(allow_new=allow_custom))
        if default
        else f'{_separator("-")}\n'
    )
    note = _custom_value_note(allow_custom)
    if prefer_listed:
        hint = f'select from the list (numbers {range_str} or listed names, comma-separated).'
    elif allow_custom:
        hint = f'type one or more numbers {range_str} and/or names, comma-separated'
    else:
        hint = f'type one or more numbers {range_str} and/or listed names, comma-separated'
    shown_name = field_name(f'{name}(s)') if coloured_name else f'{name}(s)'.upper()
    print(
        f'{top_sep}\n'
        f'{shown_name} - {hint}\n'
        f'{note}'
        f'{choices_sub_list}'
    )
    while True:
        raw = input(f'{saved}: ').strip()
        if default:
            if not raw:
                return list(default)
            raw = _value_after_saved_menu(
                raw,
                _numbers_for_saved(default, choices),
                allow_new=allow_custom,
            )
            if raw is None:
                continue
        if not raw:
            warn(f'Value cannot be empty, please try again.')
            continue
        chosen = _parse_multi_choice(
            raw,
            choices,
            name,
            allow_custom=allow_custom,
            prefer_listed=prefer_listed,
            range_str=range_str,
        )
        if chosen is not None:
            return chosen


def input_metric_value(label: str, default: str | None = None) -> str | None:
    """Prompt for one metric value; empty input skips unless keeping a default."""
    top_sep = _field_separator()
    if default:
        body = _saved_value_block(default, _saved_text_rows())
    else:
        rule = _separator('-')
        body = (
            f'{rule}\n'
            f'  Choose an option:\n'
            f'{_menu_choice("Enter", "Skip this metric")}\n'
            f'{rule}\n'
        )
    prompt = (
        f'{top_sep}\n'
        f'{field_name(label)}\n'
        f'{body}'
        f': '
    )
    while True:
        value = input(prompt).strip()
        if default:
            if not value:
                return default
            value = _value_after_saved_menu(value, default)
            if value is None:
                continue
        if not value:
            return default
        return value


def register_cli_text(
    group: _ArgumentGroup,
    *,
    flag: str,
    help_text: str,
    max_length: int,
) -> None:
    group.add_argument(
        flag,
        type=arg_validator(max_length),
        default=None,
        help=help_text,
    )
