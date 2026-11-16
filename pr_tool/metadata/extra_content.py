"""DEEPCRAFT AI Hub extra-content cards: schemas, field checks, and card-only prompts."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import constants
from metadata import choices as c
from metadata.choices import match_choice, normalize_project_types
from metadata.link_prompt import CONTACT_LABEL, collect_contact, collect_links, links_issue
from metadata.prompts import (
    advance_field_progress,
    field_progress_prefix,
    format_custom_choice_value,
    input_choices,
    input_optional_str,
    input_str,
)
from metadata.rules import SUITE_IMAGE_NAME, workflow_for_types
from metadata.schema import FieldSpec, MetadataSchema
SUITE_IMAGE = SUITE_IMAGE_NAME
SUITE_IMAGE_REPOS = frozenset({
    'extra-content-getting-started',
    'extra-content-resources',
})
PARTNER_REPO_KEY = 'extra-content-partners'
PARTNER_NAME_HINT = (
    'Trademark and registered symbols are supported: type (TM), (R), or (SM) '
    'to enter ™, ®, or ℠ (for example, Acme (TM) is saved as Acme™).'
)
BRAND_IMAGE_HINT = 'Use a .webp image in 16:9 format, for example acme.webp.'
BRAND_URL_HINT = 'Enter the company or brand home page.'
PARTNER_LINKS_INTRO = (
    '  Add links to webpages that describe the company or brand focus and main activities.'
)
_PARTNER_MARKS = (
    (re.compile(r'\(\s*TM\s*\)', re.IGNORECASE), '\u2122'),
    (re.compile(r'\(\s*SM\s*\)', re.IGNORECASE), '\u2120'),
    (re.compile(r'\(\s*R\s*\)', re.IGNORECASE), '\u00ae'),
)
_LINK_TRIES = 3

# Use cases that appear on AI Hub cards and are not in the Studio catalog.
EXTRA_CONTENT_USE_CASE = (
    'Edge AI',
    'Edge AI Development',
    'Electrical Anomaly Detection',
    'Keyword Spotting',
    'Power Electronics',
    'Power Quality Monitoring',
    'Privacy-Preserving Analytics',
    'Visual Inspection',
)

RESOURCE_CONTENT_TYPE = (
    'Article',
    'Blog Post',
    'Documentation',
    'News',
    'Tutorial',
    'Video',
    'Webinar',
    'White Paper',
)

SOLUTION_METRIC_LABELS = (
    'RW Memory Usage (KiB)',
    'RO Memory Usage (KiB)',
    'Inference Time (ms)',
)

# Returned by collect_extra_field when the field belongs to a shared schema.
NOT_EXTRA = object()

# Saved key order shared with Accelerators and AURIX.
_CARD_FILE_ORDER = (
    'title', 'description', 'long_description', 'algorithm',
    'sensors', 'domain', 'application', 'use_case', 'kit', 'device', 'type',
    'workflow',
    'thumbnail_image_id', 'main_image_id', 'brand_image_id', 'brand_url',
    'videos', 'links',
)

TITLE_MAX_LENGTH = 100
DESCRIPTION_MAX_LENGTH = 300


def date_error(value: str) -> str | None:
    """Return an error unless *value* is ``YYYY-MM-DD``."""
    try:
        parsed = date.fromisoformat(value.strip())
    except ValueError:
        return f'{value!r} is not a date in YYYY-MM-DD format.'
    if parsed.isoformat() != value.strip():
        return f'{value!r} is not a date in YYYY-MM-DD format.'
    return None


def card_type_issue(metadata: dict, spec: FieldSpec) -> tuple[str, str] | None:
    """Check an AI Hub ``type`` string. Returns ``(missing|other, message)`` or None."""
    value = metadata.get(spec.key)
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], str):
        value = value[0]
        metadata[spec.key] = value
    if isinstance(value, list):
        return (
            'other',
            f'{spec.key} must be a single content type string, not a list ({value!r})',
        )
    if not isinstance(value, str) or not value.strip():
        return ('missing', f'Missing or empty required field: {spec.key}')
    if value in spec.choices:
        return None
    matched = match_choice(value, spec.choices)
    if matched is not None:
        metadata[spec.key] = matched
        return None
    return (
        'other',
        f'{spec.key}: {value!r} is not a content type this tool can publish '
        f'({", ".join(spec.choices)})',
    )


def card_id_issue(
    metadata: dict,
    spec: FieldSpec,
    project_name: str | None,
) -> tuple[str, str] | None:
    """Resource ``id`` is the card directory name."""
    if project_name:
        metadata[spec.key] = project_name
        return None
    value = metadata.get(spec.key)
    if not isinstance(value, str) or not value.strip():
        return ('missing', f'Missing or empty required field: {spec.key}')
    return None


def date_issue(metadata: dict, spec: FieldSpec) -> tuple[str, str] | None:
    value = metadata.get(spec.key)
    if value is None:
        if spec.required:
            return ('missing', f'Missing required field: {spec.key}')
        return None
    if not isinstance(value, str) or not value.strip():
        return ('other', f'{spec.key} must be a YYYY-MM-DD string when present')
    error = date_error(value)
    if error:
        return ('other', f'{spec.key}: {error}')
    return None


def collect_card_type(field: FieldSpec, card_type: str | None) -> str:
    """``type`` is the content type chosen before metadata collection."""
    if not card_type or card_type not in field.choices:
        raise ValueError(
            f'{field.key}: no content type selected for this run '
            f'(choose from {", ".join(field.choices)})',
        )
    print(f'\n{constants.ICON_INFO} {field.label} set from your selection: {card_type}')
    return card_type


def collect_card_id(field: FieldSpec, project_name: str) -> str:
    """Published resource cards set ``id`` to the card directory name."""
    print(f'\n{constants.ICON_INFO} {field.label} set from the folder name: {project_name}')
    return project_name


def collect_date(field: FieldSpec, previous: dict) -> str | None:
    prev_value = previous.get(field.key)
    default = prev_value if isinstance(prev_value, str) and not date_error(prev_value) else None
    if field.required:
        while True:
            value = input_str(f'{field.label} (YYYY-MM-DD)', default=default)
            error = date_error(value)
            if error is None:
                return value.strip()
            print(f'{constants.ICON_WARNING} {error}')
    return input_optional_str(
        f'{field.label} (YYYY-MM-DD)',
        default=default,
        hint='Optional. Example: 2026-01-14. Type - to clear a saved date.',
        validator=date_error,
    )


def _noted(message: str) -> str:
    prefix = field_progress_prefix()
    return f'\n{prefix}{message}' if prefix else f'\n{message}'


def _improj_algorithm(project_path: Path, project_name: str) -> str | None:
    """The Accelerator algorithm, or None when this folder has no .improj."""
    from metadata.improj import algorithm_from_improj

    try:
        return algorithm_from_improj(project_path, project_name)
    except ValueError:
        return None


def _algorithm_names(value: object) -> list[str]:
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    if isinstance(value, list):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return []


def collect_optional_algorithm(
    field: FieldSpec,
    *,
    project_path: Path,
    project_name: str,
    previous: dict,
    review_pass: bool,
) -> list[str] | None:
    """Ask for one or more algorithms. A .improj value is the default. Enter skips."""
    derived = _improj_algorithm(project_path, project_name)
    saved = _algorithm_names(previous.get(field.key))
    if derived and review_pass:
        print(f'\nDefault from {project_name}.improj ProjectType: {derived}')
    elif derived and not saved:
        print(_noted(
            f'Algorithm derived from {project_name}.improj ProjectType: {derived}',
        ))
    chosen = input_choices(
        field.label,
        list(field.choices),
        default=saved or ([derived] if derived else None),
        allow_custom=False,
        allow_empty=True,
    )
    return chosen or None


def collect_optional_workflow(
    field: FieldSpec,
    *,
    result: dict,
    previous: dict,
    review_pass: bool,
) -> list[str] | None:
    """Derive workflow from project type when that rule applies. Otherwise ask.

    Enter leaves the list empty, and an empty list is not written to the file.
    """
    types = normalize_project_types(result.get('type', previous.get('type')))
    derived = workflow_for_types(types)
    if derived and not review_pass:
        print(_noted(f'Workflow derived from project type: {", ".join(derived)}'))
        return derived
    saved = previous.get(field.key)
    default = saved if isinstance(saved, list) and saved else (derived or None)
    chosen = input_choices(
        field.label,
        list(field.choices),
        default=default,
        allow_custom=False,
        allow_empty=True,
    )
    return chosen or None


def collect_extra_field(
    field: FieldSpec,
    *,
    project_path: Path,
    project_name: str,
    previous: dict,
    result: dict,
    review_pass: bool,
    card_type: str | None,
    repo_key: str | None = None,
) -> Any:
    """Collect a card-only field, or an optional derived algorithm or workflow.

    Shared required fields return ``NOT_EXTRA`` so the existing collector runs.
    """
    if field.kind == 'card_type':
        return collect_card_type(field, card_type)
    if field.kind == 'card_id':
        return collect_card_id(field, project_name)
    if field.kind == 'date':
        return collect_date(field, previous)
    if field.kind == 'links':
        if repo_key == PARTNER_REPO_KEY:
            return collect_partner_links(previous)
        return collect_links(previous)
    if field.kind == 'derived_algorithm' and not field.required:
        return collect_optional_algorithm(
            field,
            project_path=project_path,
            project_name=project_name,
            previous=previous,
            review_pass=review_pass,
        )
    if field.kind == 'derived_workflow' and not field.required:
        return collect_optional_workflow(
            field,
            result=result,
            previous=previous,
            review_pass=review_pass,
        )
    return NOT_EXTRA


def extra_field_issue(
    metadata: dict,
    spec: FieldSpec,
    project_name: str | None,
    repo_key: str | None = None,
) -> tuple[str, str] | None:
    """Check one card-only field. Callers only pass card kinds."""
    if spec.kind == 'card_type':
        return card_type_issue(metadata, spec)
    if spec.kind == 'card_id':
        return card_id_issue(metadata, spec, project_name)
    if spec.kind == 'date':
        return date_issue(metadata, spec)
    if spec.kind == 'links':
        contact_label = CONTACT_LABEL if repo_key == PARTNER_REPO_KEY else None
        return links_issue(metadata, spec, contact_label=contact_label)
    raise ValueError(f'{spec.key}: {spec.kind!r} is not an extra-content field')


def collect_partner_links(previous: dict) -> list[dict] | None:
    """Ask for partner pages, then one contact link, and store both in ``links``."""
    pages, contact = _partner_link_groups(previous.get('links'))
    page_links = collect_links({'links': pages}, intro=PARTNER_LINKS_INTRO)
    advance_field_progress('Contact')
    contact_links = collect_contact({'contact': contact})
    merged = [*(page_links or []), *(contact_links or [])]
    return merged or None


def _partner_link_groups(value: Any) -> tuple[list[dict], list[dict]]:
    """Split saved links into page links and the contact link."""
    if not isinstance(value, list):
        return [], []
    pages: list[dict] = []
    contact: list[dict] = []
    for entry in value:
        label = entry.get('label') if isinstance(entry, dict) else None
        if isinstance(label, str) and label.strip().casefold() == CONTACT_LABEL.casefold():
            contact.append(entry)
        else:
            pages.append(entry)
    return pages, contact


def optional_algorithm_issue(
    metadata: dict,
    spec: FieldSpec,
) -> tuple[str, str] | None:
    """A blank algorithm is omitted. Each value that is present must be in the catalog."""
    names = _algorithm_names(metadata.get(spec.key))
    if not names:
        metadata.pop(spec.key, None)
        return None
    resolved: list[str] = []
    for item in names:
        if item in spec.choices:
            resolved.append(item)
            continue
        matched = match_choice(item, spec.choices)
        if matched is None:
            return (
                'choice',
                f'{spec.key}: {item!r} is not in the allowed list ({", ".join(spec.choices)})',
            )
        resolved.append(matched)
    metadata[spec.key] = resolved
    from metadata.improj import apply_vision_metadata_defaults
    apply_vision_metadata_defaults(metadata, only_missing_kit=True)
    return None


def optional_workflow_issue(metadata: dict, spec: FieldSpec) -> tuple[str, str] | None:
    """A blank workflow is omitted. A project type still forces its workflow."""
    value = metadata.get(spec.key)
    if value is None or value == [] or value == '':
        metadata.pop(spec.key, None)
        value = None
    expected = workflow_for_types(normalize_project_types(metadata.get('type')))
    if expected:
        if value is None:
            metadata[spec.key] = expected
            return None
        if value != expected:
            return (
                'other',
                f'{spec.key} does not match project type '
                f'(expected {expected!r}, got {value!r})',
            )
        return None
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        return ('other', f'{spec.key} must be a list of workflow names when present')
    for index, item in enumerate(value):
        if item in spec.choices:
            continue
        matched = match_choice(item, spec.choices)
        if matched is not None:
            value[index] = matched
            continue
        return (
            'choice',
            f'{spec.key}: {item!r} is not in the allowed list ({", ".join(spec.choices)})',
        )
    return None


def drop_blank_algorithm_and_workflow(metadata: dict) -> None:
    """Leave algorithm and workflow out of the file when the user skipped them."""
    algorithm = metadata.get('algorithm')
    names = _algorithm_names(algorithm)
    if names:
        metadata['algorithm'] = names
    else:
        metadata.pop('algorithm', None)
    workflow = metadata.get('workflow')
    if not isinstance(workflow, list) or not workflow:
        metadata.pop('workflow', None)


def partner_display_name(value: str) -> str:
    """A partner name, keeping trademark and registered marks.

    ``(TM)``, ``(SM)``, and ``(R)`` are stored as ™, ℠, and ®. A mark already
    typed as a symbol stays as typed.
    """
    text = value.strip()
    for pattern, mark in _PARTNER_MARKS:
        text = pattern.sub(mark, text)
    text = re.sub(r'\s+([\u2122\u2120\u00ae])', r'\1', text)
    return format_custom_choice_value(text)


def copy_partner_brand_image(metadata: dict, repo_key: str) -> None:
    """A partner card uses the brand image as both project images."""
    if repo_key != PARTNER_REPO_KEY:
        return
    image = metadata.get('brand_image_id')
    if isinstance(image, str) and image.strip():
        metadata['thumbnail_image_id'] = image.strip()
        metadata['main_image_id'] = image.strip()


def with_suite_image(names: list[str] | None, repo_key: str) -> list[str] | None:
    """Keep ``deepcraft_ai_suite.webp`` available for Getting Started and Resources.

    Its tags are included because the image prompt takes tags from the file list.
    """
    if repo_key not in SUITE_IMAGE_REPOS or names is None or SUITE_IMAGE in names:
        return names
    return [*names, SUITE_IMAGE]


def _title(shared: Callable[[str], FieldSpec], *, label: str = 'Title') -> FieldSpec:
    return replace(
        shared('title'),
        label=label,
        max_length=TITLE_MAX_LENGTH,
        cli_help=f'The title; max {TITLE_MAX_LENGTH} characters.',
    )


def _description(shared: Callable[[str], FieldSpec]) -> FieldSpec:
    return replace(
        shared('description'),
        max_length=DESCRIPTION_MAX_LENGTH,
        cli_help=f'Short description; max {DESCRIPTION_MAX_LENGTH} characters.',
    )


def _links() -> FieldSpec:
    return FieldSpec('links', 'Links', 'links', required=False)


def _card_type(type_label: str) -> FieldSpec:
    return FieldSpec(
        'type', 'Content type', 'card_type',
        choices=(type_label,),
        allow_custom=False,
    )


def _use_case(shared: Callable[[str], FieldSpec], *, allow_empty: bool = False) -> FieldSpec:
    return replace(
        shared('use_case'),
        choices=c.USE_CASE + EXTRA_CONTENT_USE_CASE,
        allow_empty=allow_empty,
    )


def _algorithm() -> FieldSpec:
    return FieldSpec(
        'algorithm', 'Algorithm', 'derived_algorithm',
        required=False,
        choices=c.ALGORITHM,
        allow_custom=False,
    )


def _workflow() -> FieldSpec:
    return FieldSpec(
        'workflow', 'Workflow', 'derived_workflow',
        required=False,
        choices=c.WORKFLOW,
        allow_custom=False,
    )


def _card_fields(
    type_label: str,
    shared: Callable[[str], FieldSpec],
    videos_field: FieldSpec,
    *trailing: FieldSpec,
    sensors_empty: bool = False,
    domain_empty: bool = False,
    use_case_empty: bool = False,
    title_label: str = 'Title',
    include_workflow: bool = True,
) -> tuple[FieldSpec, ...]:
    """Accelerator and AURIX field order. Card-only fields follow in *trailing*."""
    sensors = shared('sensors')
    domain = shared('domain')
    if sensors_empty:
        sensors = replace(sensors, allow_empty=True)
    if domain_empty:
        domain = replace(domain, allow_empty=True)
    workflow = (_workflow(),) if include_workflow else ()
    return (
        _title(shared, label=title_label),
        _description(shared),
        shared('long_description'),
        _algorithm(),
        sensors,
        domain,
        shared('application'),
        _use_case(shared, allow_empty=use_case_empty),
        shared('kit'),
        shared('device'),
        _card_type(type_label),
        *workflow,
        shared('thumbnail_image_id'),
        shared('main_image_id'),
        shared('brand'),
        videos_field,
        _links(),
        *trailing,
    )


def _resources_file_order() -> tuple[str, ...]:
    """``id`` leads the file. ``content_type`` follows ``type``."""
    type_at = _CARD_FILE_ORDER.index('type')
    return (
        ('id',)
        + _CARD_FILE_ORDER[:type_at + 1]
        + ('content_type',)
        + _CARD_FILE_ORDER[type_at + 1:]
        + ('published_date',)
    )


def build_ai_hub_schemas(
    shared: Callable[[str], FieldSpec],
    videos_field: FieldSpec,
) -> tuple[MetadataSchema, ...]:
    """Getting Started, Partners, Resources, Solutions, and Tools, in that registry order."""
    getting_started = MetadataSchema(
        repo_key='extra-content-getting-started',
        fields=_card_fields('Getting Started', shared, videos_field),
    )
    partners = MetadataSchema(
        repo_key=PARTNER_REPO_KEY,
        fields=_card_fields(
            'Partners', shared, videos_field, title_label='Brand/Partner name',
        ),
    )
    resources = MetadataSchema(
        repo_key='extra-content-resources',
        key_order=_resources_file_order(),
        fields=_card_fields(
            'Resources',
            shared,
            videos_field,
            FieldSpec('id', 'Id', 'card_id'),
            FieldSpec('published_date', 'Published date', 'date', required=False),
            FieldSpec(
                'content_type', 'Resource type', 'single_choice',
                choices=RESOURCE_CONTENT_TYPE,
                allow_custom=False,
            ),
            sensors_empty=True,
            domain_empty=True,
            use_case_empty=True,
        ),
    )
    solutions = MetadataSchema(
        repo_key='extra-content-solutions',
        fields=_card_fields(
            'Solutions',
            shared,
            videos_field,
            FieldSpec(
                'metrics', 'Performance metrics', 'metrics',
                required=False,
                choices=SOLUTION_METRIC_LABELS,
                metric_note=True,
            ),
            include_workflow=False,
        ),
    )
    tools = MetadataSchema(
        repo_key='extra-content-tools',
        fields=_card_fields('Tools', shared, videos_field),
    )
    return getting_started, partners, resources, solutions, tools
