"""Interactive prompt for optional performance metrics.

A solution card has a fixed set of figures. Enter skips or keeps them, and 1
asks for each value in order. Model-zoo metrics use the link menu instead:
Enter skips or keeps, and a number adds, modifies, or removes one label.
"""

from __future__ import annotations

import re
from typing import Any

import constants
from metadata.choices import METRIC_LABELS
from metadata.prompts import (
    _field_separator,
    _menu_choice,
    _separator,
    field_name,
    input_choice,
    input_str,
    paint_yellow,
)
from metadata.schema import FieldSpec

_METRIC_INTRO = '  Add performance figures. Each one uses a listed label and a value.'
_FIXED_INTRO = (
    '  Enter a value for each figure, then a short note on how it was measured.'
)
_MENU_HINT = 'add a performance metric (recommended)'
_FIXED_MENU_HINT = 'add a performance metric'
_NOTE_EXAMPLE = 'Measured on PSOC\u2122 6 (int8x8) | ml-middleware and TFLM excluded'
_NOTE_ASIDE = f'Describe how this value was measured, for example {_NOTE_EXAMPLE}.'
_METRIC_NUMBER = re.compile(r'\d+(?:\.\d+)?')
_NUMBER_WARNING = 'Enter a number, such as 73. Please try again.'

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
    labels: tuple[str, ...] = METRIC_LABELS,
    with_note: bool = False,
    title: str = 'Performance metrics',
) -> list[dict] | None:
    """Ask for performance metrics. Enter with none leaves the field out of the file.

    With a note, the labels are a fixed set: ``1`` asks for every value in
    order. Otherwise ``1`` adds one label, ``2`` modifies one, and ``3``
    removes one. Each label can be saved once. ``None`` means no metrics.
    """
    metrics = _saved_metrics(previous.get('metrics'), with_note=with_note)
    if with_note:
        return _collect_fixed_metrics(metrics, labels, title=title, with_note=with_note)
    intro = _METRIC_INTRO
    while True:
        action, index = _choose_metrics(
            metrics, labels, title=title, intro=intro, with_note=with_note,
        )
        if action == 'keep':
            return metrics or None
        if action == 'add':
            metric = _collect_one_metric(None, labels, metrics, with_note=with_note)
            if metric is not None:
                metrics.append(metric)
            continue
        if action == 'remove':
            del metrics[index]
            continue
        metric = _collect_one_metric(
            metrics[index], labels, metrics, with_note=with_note,
        )
        if metric is not None:
            metrics[index] = metric


def metrics_issue(metadata: dict, spec: FieldSpec) -> list[tuple[str, str]]:
    """Check saved metrics. A missing list is allowed when the field is optional."""
    key = spec.key
    metrics = metadata.get(key)
    if metrics is None:
        if spec.required:
            return [('missing', f'Missing required field: {key}')]
        return []
    if not isinstance(metrics, list) or not metrics:
        return [('other', f'{key} must be a non-empty list when present')]
    allowed = tuple(spec.choices) if spec.choices else METRIC_LABELS
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
        elif spec.metric_note and _reject_metric_number(value.strip()):
            issues.append(('other', f'{key}[{index}] value {value.strip()!r} must be a number'))
        if spec.metric_note:
            note = entry.get('note')
            if not isinstance(note, str) or not note.strip():
                issues.append(('missing', f'{key}[{index}] missing or empty note'))
        if not issues and isinstance(label, str) and isinstance(value, str):
            item = {'label': label, 'value': value.strip()}
            if spec.metric_note:
                item['note'] = entry['note'].strip()
            stored.append(item)
    if issues:
        return issues
    metadata[key] = stored
    return []


def _saved_metrics(value: Any, *, with_note: bool) -> list[dict]:
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
        if with_note:
            note = entry.get('note')
            if not isinstance(note, str) or not note.strip():
                continue
            item['note'] = note.strip()
        metrics.append(item)
    return metrics


def _open_labels(labels: tuple[str, ...], metrics: list[dict], current: str | None) -> list[str]:
    used = {item['label'] for item in metrics}
    if current is not None:
        used.discard(current)
    return [label for label in labels if label not in used]


def _collect_fixed_metrics(
    metrics: list[dict],
    labels: tuple[str, ...],
    *,
    title: str,
    with_note: bool,
) -> list[dict] | None:
    """Ask for every listed figure in order. Enter keeps or skips the set."""
    while True:
        action = _choose_fixed_metrics(
            metrics, title=title, intro=_FIXED_INTRO, with_note=with_note,
        )
        if action == 'keep':
            return metrics or None
        if action == 'clear':
            metrics = []
            continue
        metrics = _ask_fixed_values(metrics, labels, with_note=with_note)


def _ask_fixed_values(
    metrics: list[dict],
    labels: tuple[str, ...],
    *,
    with_note: bool,
) -> list[dict]:
    """Ask for each label's value, in list order, with no choice in between."""
    saved = {item['label']: item for item in metrics}
    collected: list[dict] = []
    for label in labels:
        current = saved.get(label)
        value = input_str(
            label,
            default=current['value'] if current else None,
            aside=METRIC_DESCRIPTIONS.get(label),
            reject=_reject_metric_number,
        )
        entry = {'label': label, 'value': value}
        if with_note:
            entry['note'] = input_str(
                'Note',
                default=current.get('note') if current else None,
                aside=_NOTE_ASIDE,
            )
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
                _menu_choice('1', 'Change the metrics'),
                _menu_choice('2', 'Remove the metrics'),
            ]
            prompt = 'Choice (Enter, 1, or 2): '
            retry = 'Press Enter to keep them, 1 to change them, or 2 to remove them.'
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


def _collect_one_metric(
    current: dict | None,
    labels: tuple[str, ...],
    metrics: list[dict],
    *,
    with_note: bool,
) -> dict | None:
    """Collect one metric. ``None`` returns to the metric menu."""
    choices = _open_labels(labels, metrics, current['label'] if current else None)
    if not choices:
        _metric_warn('Every listed metric is already saved.')
        return None
    label = input_choice(
        'Metric',
        choices,
        default=current['label'] if current and current['label'] in choices else None,
        allow_custom=False,
    )
    value = input_str(
        label,
        default=current['value'] if current else None,
        aside=METRIC_DESCRIPTIONS.get(label),
    )
    entry = {'label': label, 'value': value}
    if with_note:
        entry['note'] = input_str(
            'Note',
            default=current.get('note') if current else None,
            aside=_NOTE_ASIDE,
        )
    return entry


def _reject_metric_number(value: str) -> str | None:
    """Return a warning when a solution metric value is not a plain number."""
    if _METRIC_NUMBER.fullmatch(value):
        return None
    return _NUMBER_WARNING


def _metric_warn(message: str) -> None:
    print(paint_yellow(f'{constants.ICON_WARNING} {message}'))


def _choose_metrics(
    metrics: list[dict],
    labels: tuple[str, ...],
    *,
    title: str,
    intro: str,
    with_note: bool,
) -> tuple[str, int]:
    """Return ``keep``, ``add``, ``modify``, or ``remove``, and a metric index."""
    can_add = bool(_open_labels(labels, metrics, None))
    while True:
        if metrics:
            options = [_menu_choice('Enter', 'Keep these metrics')]
            if can_add:
                options.append(_menu_choice('1', 'Add a metric'))
            options.extend([
                _menu_choice('2', 'Modify a metric'),
                _menu_choice('3', 'Remove a metric'),
            ])
            retry = (
                'Press Enter to keep them, 1 to add, 2 to modify, or 3 to remove.'
                if can_add
                else 'Press Enter to keep them, 2 to modify, or 3 to remove.'
            )
        else:
            options = [
                _menu_choice('Enter', 'No metric to add'),
                _menu_choice('1', 'Add a metric'),
            ]
            retry = 'Press Enter if there is no metric to add, or type 1 to add a metric.'
        _show_metric_menu(metrics, options, title=title, intro=intro, with_note=with_note)
        raw = input('Choice (Enter, 1, 2, or 3): ' if metrics else 'Choice (Enter or 1): ').strip()
        if not raw:
            return 'keep', 0
        if not metrics and raw == '1':
            return 'add', 0
        if metrics and raw == '1' and can_add:
            return 'add', 0
        if metrics and raw in ('2', '3'):
            index = 0 if len(metrics) == 1 else _metric_index(len(metrics))
            if index is None:
                continue
            return ('modify' if raw == '2' else 'remove', index)
        _metric_warn(f'{retry} Please try again.')


def _show_metric_menu(
    metrics: list[dict],
    options: list[str],
    *,
    title: str,
    intro: str,
    with_note: bool,
    hint: str = _MENU_HINT,
) -> None:
    rule = _separator('-')
    print(_field_separator())
    label = field_name(title)
    print(f'{label} - {hint}')
    print(rule)
    if not metrics and intro:
        print(intro)
    for number, metric in enumerate(metrics, start=1):
        print(f'  {number}. {metric["label"]}')
        print(f'     {metric["value"]}')
        if with_note:
            print(f'     {metric["note"]}')
    print(rule)
    print('  Choose an option:')
    for option in options:
        print(option)
    print(rule)


def _metric_index(count: int) -> int | None:
    raw = input(f'Metric number (1 to {count}): ').strip()
    if raw.isdigit() and 1 <= int(raw) <= count:
        return int(raw) - 1
    _metric_warn(f'Type a number between 1 and {count}.')
    return None
