"""Interactive prompt for optional performance metrics.

Enter skips or keeps the set. ``1`` asks for each figure in order, and Enter
on a figure skips it. ``2`` removes the set. A value is a number, except
Input Layer and Output Layer, which are shapes such as ``1x384x384x3``.
Each figure except Input Layer and Output Layer then takes an optional note on
how it was measured.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

import constants
from metadata.choices import PERFORMANCE_METRIC_LABELS
from metadata.metric_limits import device_names, limit_error
from metadata.prompts import (
    _field_separator,
    _menu_choice,
    _separator,
    field_name,
    input_optional_str,
    paint_magenta,
    paint_yellow,
    recap_entry_indent,
)
from metadata.schema import FieldSpec

_METRIC_INTRO = (
    '  Enter a value for each figure. Most figures then take an optional note on how '
    'it was measured. Press Enter to skip a figure or its note.'
)
_FIXED_MENU_HINT = 'add a performance metric'
_SKIP_HINT = 'Press Enter to skip this metric.'
_NOTE_SKIP_HINT = 'Press Enter to skip this note.'
_NOTE_EXAMPLE = 'Measured on PSOC\u2122 6 (int8x8) | ml-middleware and TFLM excluded'
_NOTE_ASIDE = f'Describe how this value was measured, for example {_NOTE_EXAMPLE}.'
_METRIC_NUMBER = re.compile(r'\d+(?:\.\d+)?')
_METRIC_SHAPE = re.compile(r'\d+(?:x\d+)+', re.IGNORECASE)
_SHAPE_LABELS = frozenset({'Input Layer', 'Output Layer'})
_NUMBER_WARNING = 'Enter a number, such as 73. Please try again.'
_SHAPE_WARNING = 'Enter a shape, such as 1x384x384x3. Please try again.'

# Shown under each label when it is chosen. Every predefined label needs one.
METRIC_DESCRIPTIONS: dict[str, str] = {
    'RW Memory Usage (KiB)': 'Read-write memory (RAM) the model uses at run time, in kibibytes.',
    'RO Memory Usage (KiB)': 'Read-only memory (flash) used by the model and its code, in kibibytes.',
    'Inference Time (ms)': 'Time to run one inference on the device, in milliseconds.',
    'Model Weight (MB)': 'Size of the model weights stored on the device, in megabytes.',
    'Input Layer': 'Shape of the input the model expects, for example 1x320x320x3.',
    'Output Layer': 'Shape of the output the model returns, for example 1x2268x6.',
    'Compute (MC)': 'Work for one inference, in millions of CPU cycles (MC).',
    'Energy (mJ)': 'Energy used by one inference, in millijoules.',
    'Scratch Pad Size (MB)': 'Temporary working memory the model needs while it runs, in megabytes.',
}


def metrics_by_label(metrics: list[dict] | None) -> dict[str, str]:
    """Map each complete metric label to its value. Empty values are left out."""
    by_label: dict[str, str] = {}
    if not metrics:
        return by_label
    for entry in metrics:
        if isinstance(entry, dict):
            label = entry.get('label')
            value = entry.get('value')
            if isinstance(label, str) and isinstance(value, str) and value.strip():
                by_label[label] = value.strip()
    return by_label


def collect_metrics(
    previous: dict,
    *,
    labels: tuple[str, ...] = PERFORMANCE_METRIC_LABELS,
    with_note: bool = True,
    title: str = 'Performance metrics',
    devices: Sequence[str] = (),
) -> list[dict] | None:
    """Ask for performance metrics. Enter with none leaves the field out of the file.

    ``1`` asks for every label in order. Enter on a figure skips it. ``2``
    removes the set. A note follows each entered value except a shape. ``None``
    means no metrics. A number must be inside the range the listed *devices*
    allow, and the least capable device sets the upper limit.
    """
    metrics = _saved_metrics(previous.get('metrics'))
    return _collect_fixed_metrics(
        metrics,
        labels,
        title=title,
        intro=_METRIC_INTRO,
        with_note=with_note,
        devices=devices,
    )


def metrics_issue(metadata: dict, spec: FieldSpec) -> list[tuple[str, str]]:
    """Check saved metrics. A missing list is allowed when the field is optional."""
    key = spec.key
    metrics = metadata.get(key)
    devices = device_names(metadata.get('device'))
    if metrics is None:
        if spec.required:
            return [('missing', f'Missing required field: {key}')]
        return []
    if not isinstance(metrics, list) or not metrics:
        return [('other', f'{key} must be a non-empty list when present')]
    allowed = tuple(spec.choices) if spec.choices else PERFORMANCE_METRIC_LABELS
    allowed_set = set(allowed)
    stored: list[dict] = []
    seen: set[str] = set()
    issues: list[tuple[str, str]] = []
    for index, entry in enumerate(metrics, start=1):
        if not isinstance(entry, dict):
            issues.append(('other', f'{key}[{index}] must be an object'))
            continue
        label = entry.get('label')
        value = entry.get('value')
        if not isinstance(label, str) or label not in allowed_set:
            issues.append((
                'choice',
                f'{key}[{index}] label {label!r} is not allowed '
                f'(expected one of {len(allowed_set)} predefined labels)',
            ))
        elif label in seen:
            issues.append(('other', f'{key}[{index}] label {label!r} is already used'))
        else:
            seen.add(label)
        if not isinstance(value, str) or not value.strip():
            issues.append(('missing', f'{key}[{index}] missing or empty value'))
            value = ''
        elif (
            isinstance(label, str)
            and label in allowed_set
            and (error := metric_value_error(label, value.strip(), devices))
        ):
            issues.append(('other', f'{key}[{index}] value {value.strip()!r}: {error}'))
        note = entry.get('note')
        if note is not None and (not isinstance(note, str) or not note.strip()):
            issues.append(('other', f'{key}[{index}] note must be text when present'))
        if not issues and isinstance(label, str) and isinstance(value, str):
            item = {'label': label, 'value': value.strip()}
            if isinstance(note, str) and note.strip() and _takes_note(label):
                item['note'] = note.strip()
            stored.append(item)
    if issues:
        return issues
    metadata[key] = stored
    return []


def _takes_note(label: str) -> bool:
    """Shape figures are self-explanatory, so only the other figures take a note."""
    return label not in _SHAPE_LABELS


def _saved_metrics(value: Any) -> list[dict]:
    """Keep each saved value. A note is included when the file already has one."""
    if not isinstance(value, list):
        return []
    metrics: list[dict] = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        label = entry.get('label')
        raw_value = entry.get('value')
        if not isinstance(label, str) or not label.strip():
            continue
        if not isinstance(raw_value, str) or not raw_value.strip():
            continue
        item = {'label': label, 'value': raw_value.strip()}
        note = entry.get('note')
        if _takes_note(label) and isinstance(note, str) and note.strip():
            item['note'] = note.strip()
        metrics.append(item)
    return metrics


def _in_prompt_order(metrics: list[dict], labels: tuple[str, ...]) -> list[dict]:
    """List saved figures in the prompt order. Input Layer and Output Layer are last."""
    rank = {label: index for index, label in enumerate(labels)}
    return sorted(metrics, key=lambda item: rank.get(item['label'], len(rank)))


def _collect_fixed_metrics(
    metrics: list[dict],
    labels: tuple[str, ...],
    *,
    title: str,
    intro: str,
    with_note: bool,
    devices: Sequence[str] = (),
) -> list[dict] | None:
    """Ask for every listed figure in order. Enter keeps or skips the set."""
    while True:
        metrics = _in_prompt_order(metrics, labels)
        action = _choose_fixed_metrics(
            metrics, title=title, intro=intro, with_note=with_note,
        )
        if action == 'keep':
            if error := _saved_metrics_out_of_range(metrics, devices):
                _metric_warn(f'{error} Type 1 to modify the metrics, or 2 to remove them.')
                continue
            return metrics or None
        if action == 'clear':
            metrics = []
            continue
        metrics = _ask_fixed_values(metrics, labels, with_note=with_note, devices=devices)


def _saved_metrics_out_of_range(metrics: list[dict], devices: Sequence[str]) -> str | None:
    """Refuse Enter on a saved value that the listed devices no longer allow.

    This happens when the device was changed after the metrics were entered.
    """
    for number, item in enumerate(metrics, start=1):
        if error := metric_value_error(item['label'], item['value'], devices):
            text = error.removesuffix(' Please try again.')
            return f'Metric {number}: {text}{"" if text.endswith(".") else "."}'
    return None


def _ask_fixed_values(
    metrics: list[dict],
    labels: tuple[str, ...],
    *,
    with_note: bool,
    devices: Sequence[str] = (),
) -> list[dict]:
    """Ask for each label's value, in list order, with no choice in between."""
    saved = {item['label']: item for item in metrics}
    collected: list[dict] = []
    for label in labels:
        current = saved.get(label)
        value = input_optional_str(
            label,
            default=current['value'] if current else None,
            hint='' if current else _SKIP_HINT,
            aside=METRIC_DESCRIPTIONS.get(label),
            validator=lambda text, metric_label=label: metric_value_error(
                metric_label, text, devices,
            ),
            clear_label='Remove the metric',
            clear_key='2',
        )
        if not value:
            continue
        entry = {'label': label, 'value': value}
        if with_note and _takes_note(label):
            saved_note = current.get('note') if current else None
            note = input_optional_str(
                f'Note for {label}',
                default=saved_note,
                hint='' if saved_note else _NOTE_SKIP_HINT,
                aside=_NOTE_ASIDE,
                clear_label='Remove the note',
                clear_key='2',
                nested=True,
            )
            if note:
                entry['note'] = note
        collected.append(entry)
    return collected


def _choose_fixed_metrics(
    metrics: list[dict],
    *,
    title: str,
    intro: str,
    with_note: bool,
) -> str:
    """Return ``keep``, ``enter``, or ``clear`` for a fixed set of figures."""
    while True:
        if metrics:
            options = [
                _menu_choice('Enter', 'Keep these metrics'),
                _menu_choice('1', 'Modify the metrics'),
                _menu_choice('2', 'Remove the metrics'),
            ]
            prompt = 'Choice (Enter, 1, or 2): '
            retry = 'Press Enter to keep them, 1 to modify them, or 2 to remove them.'
        else:
            options = [
                _menu_choice('Enter', 'No metric to add'),
                _menu_choice('1', 'Enter the metrics'),
            ]
            prompt = 'Choice (Enter or 1): '
            retry = 'Press Enter if there is no metric to add, or type 1 to enter the metrics.'
        _show_metric_menu(
            metrics, options, title=title, intro=intro, with_note=with_note,
            hint=_FIXED_MENU_HINT,
        )
        raw = input(prompt).strip()
        if not raw:
            return 'keep'
        if raw == '1':
            return 'enter'
        if metrics and raw == '2':
            return 'clear'
        _metric_warn(f'{retry} Please try again.')


def metric_value_error(label: str, value: str, devices: Sequence[str] = ()) -> str | None:
    """Return a warning when *value* is not allowed for *label*.

    Input Layer and Output Layer take a shape. Every other metric takes a number
    inside the range its listed *devices* allow. The least capable device sets the
    upper limit.
    """
    if label in _SHAPE_LABELS:
        if _METRIC_SHAPE.fullmatch(value):
            return None
        return _SHAPE_WARNING
    return _reject_metric_number(value) or limit_error(label, float(value), devices)


def _reject_metric_number(value: str) -> str | None:
    """Return a warning when *value* is not a plain number."""
    if _METRIC_NUMBER.fullmatch(value):
        return None
    return _NUMBER_WARNING


def _metric_warn(message: str) -> None:
    print(paint_yellow(f'{constants.ICON_WARNING} {message}'))


def _show_metric_menu(
    metrics: list[dict],
    options: list[str],
    *,
    title: str,
    intro: str,
    with_note: bool,
    hint: str = _FIXED_MENU_HINT,
) -> None:
    rule = _separator('-')
    print(_field_separator())
    label = field_name(title)
    print(f'{label} - {hint}')
    print(rule)
    if not metrics and intro:
        print(intro)
    for index, metric in enumerate(metrics, start=1):
        if index > 1:
            print(rule)
        # The number starts the line. A note lines up under the figure's name.
        print(f'{index}. {metric["label"]}: {metric["value"]}')
        if with_note and metric.get('note'):
            print(f'{recap_entry_indent(index)}{paint_magenta("Note:")} {metric["note"]}')
    print(rule)
    print('  Choose an option:')
    for option in options:
        print(option)
    print(rule)
