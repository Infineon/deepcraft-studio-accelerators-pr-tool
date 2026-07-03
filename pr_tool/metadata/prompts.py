"""Interactive prompts for metadata collection."""

import re
import shutil
from argparse import _ArgumentGroup
from typing import Callable

import constants
from metadata.choices import match_choice


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
    width = shutil.get_terminal_size((80, 24)).columns
    return char * width


def _format_choices(choices: list[str]) -> str:
    n = len(choices)
    if n == 0:
        return ''
    number_width = len(str(n))
    entries = [f'{i + 1:>{number_width}}. {choice}' for i, choice in enumerate(choices)]
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
                cells.append(entries[idx].ljust(col_width))
        rows.append(''.join(cells).rstrip())
    return '\n'.join(rows)


def input_str(name: str, max_len: int | None = None, default: str | None = None) -> str:
    top_sep = _separator('=')
    bottom_sep = _separator('-')
    default_line = f'>>> Press Enter to keep: {default}\n' if default else ''
    limit_line = f' (max {max_len} characters)' if max_len is not None else ''
    prompt = (
        f'{top_sep}\n'
        f'{name}{limit_line}\n'
        f'{default_line}'
        f'{bottom_sep}\n: '
    )
    while True:
        value = input(prompt).strip()
        if not value and default:
            return default
        if not value:
            print(f'{constants.ICON_WARNING} Value cannot be empty, please try again.')
            continue
        if max_len is not None and len(value) > max_len:
            print(f'{constants.ICON_WARNING} Value is more than {max_len} characters, please try again.')
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
        print(f"{constants.ICON_WARNING} Please answer 'y' or 'n'.")


def confirm_metadata() -> str:
    """Returns ``'yes'``, ``'no'`` (redo), or ``'abort'``."""
    while True:
        answer = input(
            'Proceed with this metadata? (y = yes / n = redo / a = abort): '
        ).strip().lower()
        if answer in ('y', 'yes'):
            return 'yes'
        if answer in ('n', 'no'):
            return 'no'
        if answer in ('a', 'abort'):
            return 'abort'
        print(f"{constants.ICON_WARNING} Please answer 'y', 'n', or 'a'.")


def confirm_new_value(value: str, kind: str) -> bool:
    return confirm(f'"{value}" is not in the suggested {kind} list. Use it anyway?')


def _resolve_custom_choice(raw: str, choices: list[str]) -> str | None:
    """Return a catalog match for a custom entry, tolerating case, trademark, and spacing."""
    formatted = format_custom_choice_value(raw)
    if formatted in choices:
        return formatted
    return match_choice(raw, choices)


def _format_grouped_choices(groups: list[tuple[str, list[str]]]) -> str:
    lines: list[str] = []
    index = 1
    number_width = len(str(sum(len(items) for _, items in groups)))
    for heading, choices in groups:
        lines.append(heading)
        for choice in choices:
            lines.append(f'  {index:>{number_width}}. {choice}')
            index += 1
    return '\n'.join(lines)


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
    top_sep = _separator('=')
    bottom_sep = _separator('-')
    default_line = f'>>> Press Enter to keep: {default}\n' if default else ''
    hint = (
        f'type a number {range_str} or enter a new name'
        if allow_custom
        else f'type a number {range_str} or a listed name'
    )
    prompt = (
        f'{top_sep}\n'
        f'{name} - {hint}\n'
        f'{default_line}'
        f'{choices_sub_list}\n'
        f'{bottom_sep}\n: '
    )
    while True:
        raw = input(prompt).strip()
        if not raw and default:
            return default
        if not raw:
            print(f'{constants.ICON_WARNING} Value cannot be empty, please try again.')
            continue
        if raw.isnumeric():
            n = int(raw)
            if n <= 0 or n > len(choices):
                print(f'{constants.ICON_WARNING} Number {raw} is not {range_str}.')
                continue
            return choices[n - 1]
        if raw in choices:
            return raw
        resolved = _resolve_custom_choice(raw, choices)
        if resolved is not None:
            return resolved
        formatted = format_custom_choice_value(raw)
        if allow_custom and confirm_new_value(formatted, name.lower()):
            return formatted
        print(f'{constants.ICON_WARNING} "{raw}" is not in the list, please try again.')


def input_choice(
    name: str,
    choices: list[str],
    default: str | None = None,
    *,
    allow_custom: bool = True,
) -> str:
    choices_sub_list = _format_choices(choices)
    range_str = f'between 1 and {len(choices)}'
    top_sep = _separator('=')
    bottom_sep = _separator('-')
    default_line = f'>>> Press Enter to keep: {default}\n' if default else ''
    hint = (
        f'type a number {range_str} or enter a new name'
        if allow_custom
        else f'type a number {range_str} or a listed name'
    )
    header = (
        f'{top_sep}\n'
        f'{name} - {hint}\n'
        f'{default_line}'
        f'{choices_sub_list}\n'
        f'{bottom_sep}'
    )
    print(header)
    retry_hint = (
        f'{name} - type a number {range_str}'
        + (' or enter a new name' if allow_custom else ' or a listed name')
    )
    while True:
        raw = input(f'{retry_hint}\n: ').strip()
        if not raw and default:
            return default
        if not raw:
            print(f'{constants.ICON_WARNING} Value cannot be empty, please try again.')
            continue
        if raw.isnumeric():
            n = int(raw)
            if n <= 0 or n > len(choices):
                print(f'{constants.ICON_WARNING} Number {raw} is not {range_str}.')
                continue
            return choices[n - 1]
        if raw in choices:
            return raw
        resolved = _resolve_custom_choice(raw, choices)
        if resolved is not None:
            return resolved
        formatted = format_custom_choice_value(raw)
        if allow_custom and confirm_new_value(formatted, name.lower()):
            return formatted
        print(f'{constants.ICON_WARNING} "{raw}" is not in the list, please try again.')


def input_choices(
    name: str,
    choices: list[str],
    default: list[str] | None = None,
    *,
    allow_custom: bool = True,
) -> list[str]:
    choices_sub_list = _format_choices(choices)
    range_str = f'between 1 and {len(choices)}'
    top_sep = _separator('=')
    bottom_sep = _separator('-')
    default_line = (f'>>> Press Enter to keep: {", ".join(default)}\n'
                    if default else '')
    hint = (
        f'type one or more numbers {range_str} and/or names, comma-separated'
        if allow_custom
        else f'type one or more numbers {range_str} and/or listed names, comma-separated'
    )
    header = (
        f'{top_sep}\n'
        f'{name}(s) - {hint}\n{default_line}{choices_sub_list}\n'
        f'{bottom_sep}'
    )
    print(header)
    retry_hint = (
        f'{name}(s) - comma-separated numbers {range_str}'
        + (' and/or names' if allow_custom else ' and/or listed names')
    )
    while True:
        raw = input(f'{retry_hint}\n: ').strip()
        if not raw and default:
            return list(default)
        if not raw:
            print(f'{constants.ICON_WARNING} Value cannot be empty, please try again.')
            continue
        tokens = [t.strip() for t in raw.split(',') if t.strip()]
        if not tokens:
            print(f'{constants.ICON_WARNING} Value cannot be empty, please try again.')
            continue
        results: list[str] = []
        retry = False
        for token in tokens:
            if token.isnumeric():
                n = int(token)
                if n <= 0 or n > len(choices):
                    print(f'{constants.ICON_WARNING} Number {token} is not {range_str}.')
                    retry = True
                    break
                results.append(choices[n - 1])
            elif token in choices:
                results.append(token)
            else:
                resolved = _resolve_custom_choice(token, choices)
                if resolved is not None:
                    results.append(resolved)
                elif allow_custom:
                    formatted = format_custom_choice_value(token)
                    if confirm_new_value(formatted, name.lower()):
                        results.append(formatted)
                    else:
                        retry = True
                        break
                else:
                    print(f'{constants.ICON_WARNING} "{token}" is not in the list, please try again.')
                    retry = True
                    break
        if retry:
            continue
        deduped = list(dict.fromkeys(results))
        if not deduped:
            print(f'{constants.ICON_WARNING} You must choose at least one {name.lower()}, please try again.')
            continue
        return deduped


def input_metric_value(label: str, default: str | None = None) -> str | None:
    """Prompt for one metric value; empty input skips unless keeping a default."""
    top_sep = _separator('=')
    bottom_sep = _separator('-')
    if default:
        default_line = f'>>> Press Enter to keep: {default}\n'
    else:
        default_line = '>>> Press Enter to skip this metric\n'
    prompt = (
        f'{top_sep}\n'
        f'{label}\n'
        f'{default_line}'
        f'{bottom_sep}\n: '
    )
    while True:
        value = input(prompt).strip()
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
