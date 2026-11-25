"""Project and metadata validation before publishing."""

from __future__ import annotations

import copy
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import constants
from metadata import finalize_metadata, format_metadata_json
from metadata.choices import (
    BRAND_IMAGE_ID,
    brand_for_image,
    brand_url_error,
    match_choice,
    normalize_project_types,
)
from metadata.link_prompt import www_missing_error
from metadata.extra_content import (
    PARTNER_REPO_KEY,
    extra_field_issue,
    optional_algorithm_issue,
    optional_workflow_issue,
)
from metadata.metric_prompt import metrics_issue
from metadata.prompts import format_custom_choice_value, paint_magenta
from metadata.rules import workflow_for_types
from metadata.schema import FieldSpec, MetadataSchema
from project_layouts import fixed_metadata_title, get_project_layout
from studio_templates import (
    STUDIO_TEMPLATE_LINK_MARKER,
    is_studio_template_link,
    is_studio_template_title,
)
from target_repo import TargetRepo

CollectMissingFn = Callable[[dict, set[str]], dict]
# Asks for the entire metadata again, with the saved values as defaults.
CollectAllFn = Callable[[dict], dict]
# (metadata, schema, addresses already asked) -> [(field key, message), ...]
LiveLinkCheckFn = Callable[[dict, MetadataSchema, set[str]], list[tuple[str, str]]]


@dataclass
class MetadataValidationResult:
    missing: list[str] = field(default_factory=list)
    choice_violations: list[str] = field(default_factory=list)
    other: list[str] = field(default_factory=list)
    fields_to_collect: set[str] = field(default_factory=set)
    choice_fields: set[str] = field(default_factory=set)

    @property
    def ok(self) -> bool:
        return not self.missing and not self.choice_violations and not self.other


def validate_project_structure(
    project_name: str, project_path: Path, target_repo: TargetRepo,
) -> None:
    """Validate the project folder before publishing."""
    get_project_layout(target_repo.project_layout).validate(project_name, project_path)


def validate_metadata(
    metadata: dict,
    schema: MetadataSchema,
    project_name: str | None = None,
    project_path: Path | None = None,
) -> MetadataValidationResult:
    """Validate *metadata* against *schema*, splitting missing vs choice issues."""
    from metadata.extra_content import copy_partner_brand_image

    result = MetadataValidationResult()
    if isinstance(metadata, dict):
        copy_partner_brand_image(metadata, schema.repo_key)
    if not isinstance(metadata, dict):
        result.missing.append('metadata.json must be a JSON object')
        return result

    for spec in schema.fields:
        if spec.kind == 'brand':
            _validate_brand(
                metadata,
                spec,
                result,
                allow_new=schema.repo_key == PARTNER_REPO_KEY,
            )
        elif spec.kind == 'image':
            _validate_required_str(metadata, 'thumbnail_image_id', spec, result)
        elif spec.kind == 'image_mirror':
            _validate_image_mirror(metadata, spec, result)
        elif spec.kind in ('text', 'long_text'):
            _validate_text(metadata, spec, result)
            if (
                schema.repo_key == 'accelerators'
                and spec.key == 'title'
                and spec.key not in result.fields_to_collect
            ):
                _flag_studio_template_title(metadata, spec, result)
        elif spec.kind == 'single_choice':
            _validate_single_choice(metadata, spec, result)
        elif spec.kind == 'multi_choice':
            _validate_multi_choice(metadata, spec, result)
        elif spec.kind == 'derived_workflow':
            if spec.required:
                _validate_derived_workflow(metadata, spec, result)
            else:
                _apply_issue(optional_workflow_issue(metadata, spec), spec, result)
        elif spec.kind == 'derived_algorithm':
            if spec.required:
                _validate_derived_algorithm(metadata, spec, result, project_name, project_path)
            else:
                _apply_issue(optional_algorithm_issue(metadata, spec), spec, result)
        elif spec.kind in ('accelerator_links', 'model_zoo_psoc_links', 'model_zoo_aurix_links'):
            _validate_links(metadata, spec, result, project_name)
        elif spec.kind == 'videos':
            _validate_videos(metadata, spec, result)
        elif spec.kind == 'metrics':
            for issue in metrics_issue(metadata, spec):
                _apply_issue(issue, spec, result)
        elif spec.kind in ('card_type', 'card_id', 'date', 'links'):
            _apply_issue(
                extra_field_issue(metadata, spec, project_name, repo_key=schema.repo_key),
                spec,
                result,
            )
        else:
            result.other.append(f'{spec.key}: unknown field kind {spec.kind!r}')
    return result


def _apply_issue(
    issue: tuple[str, str] | None,
    spec: FieldSpec,
    result: MetadataValidationResult,
) -> None:
    if issue is None:
        return
    kind, message = issue
    if kind == 'missing':
        _mark_missing(result, spec, message)
    elif kind == 'choice':
        _mark_choice(result, spec, message)
    else:
        _mark_other(result, spec, message)


def validate_loaded_metadata(
    metadata: dict,
    schema: MetadataSchema,
    collect_missing: CollectMissingFn,
    project_name: str | None = None,
    project_path: Path | None = None,
    notices: list[str] | None = None,
    check_links: LiveLinkCheckFn | None = None,
    collect_all: CollectAllFn | None = None,
) -> dict:
    """Validate loaded metadata. Optional videos stay unset until metadata is modified.

    *notices* collects short messages about automatic fixes. Print them with
    ``print_metadata_notices`` after the metadata overview.

    When a value is not in the suggested lists, the overview is shown with a
    warning, and the person chooses: keep the new entries, modify only the fields
    that hold them (*collect_missing*), or modify the entire metadata
    (*collect_all*, which falls back to *collect_missing* with every field).

    *check_links* asks the links a person entered whether they respond, once the
    other checks pass. A link that does not respond is shown, and its field is
    asked again until the link is changed or removed. Keeping it with Enter asks
    the link again. An address that responded is not asked twice.
    """
    from metadata import confirm_new_entries

    current = _repair_image_mirror(dict(metadata))
    _repair_metadata_title(current, schema, project_name, notices)
    settled: set[str] = set()
    while True:
        result = validate_metadata(current, schema, project_name, project_path)
        if check_links is not None and not (result.missing or result.other):
            unreachable = check_links(current, schema, settled)
            if unreachable:
                print(
                    f'\n{constants.ICON_WARNING} Some links in your project\'s '
                    f'metadata.json did not respond:',
                )
                for _key, issue in unreachable:
                    print(f'  - {issue}')
                print(
                    f'\n{constants.ICON_INFO} A link that does not respond cannot be '
                    f'kept. Modify or remove it below.',
                )
                current = collect_missing(current, {key for key, _issue in unreachable})
                current = _repair_image_mirror(current)
                continue
        if result.missing or result.other:
            print(
                f'\n{constants.ICON_WARNING} Your project\'s metadata.json is missing '
                f'required fields or has values this tool cannot accept:',
            )
            for issue in result.missing + result.other:
                print(f'  - {issue}')
            print(f'\n{constants.ICON_INFO} Please provide the missing or corrected metadata below.')
            if not result.fields_to_collect:
                raise ValueError('metadata.json has issues that cannot be collected interactively')
            current = collect_missing(current, result.fields_to_collect)
            current = _repair_image_mirror(current)
            continue
        if result.choice_violations:
            # The recap comes first so the warning and the question sit right under it.
            print_metadata_overview(finalize_metadata(copy.deepcopy(current), schema))
            print(
                f'\n{constants.ICON_WARNING} Review needed: used value(s) are not in the '
                f'suggested lists.',
            )
            for issue in result.choice_violations:
                print(f'  - {issue}')
            print(
                f'\n{constants.ICON_INFO} Values not yet in the AI Hub catalog are common '
                f'for new projects.',
            )
            print(
                f'  Also expected when metadata.json was edited or saved before the lists '
                f'were updated.',
            )
            print(
                f'\n{constants.ICON_INFO} Check the metadata above. Keep the new entries only '
                f'if they are meant to be new.',
            )
            print(
                f'  To pick a listed value instead, modify only the fields with new entries, '
                f'or modify the entire metadata.',
            )
            if result.choice_fields & {'sensors', 'domain'}:
                print(
                    f'\n{constants.ICON_INFO} Sensors and domain should be selected from '
                    f'the lists. Keep a new value only if none of the listed options fits.',
                )
            print()
            answer = confirm_new_entries([
                spec.label for spec in schema.fields if spec.key in result.choice_fields
            ])
            if answer == 'abort':
                print(f'{constants.ICON_ABORT} Aborted by user.')
                sys.exit(0)
            if answer == 'new':
                current = collect_missing(current, result.choice_fields)
                current = _repair_image_mirror(current)
                continue
            if answer == 'all':
                if collect_all is not None:
                    current = collect_all(current)
                else:
                    current = collect_missing(current, {spec.key for spec in schema.fields})
                current = _repair_image_mirror(current)
                continue
        return finalize_metadata(current, schema)


def _repair_metadata_title(
    metadata: dict,
    schema: MetadataSchema,
    project_name: str | None,
    notices: list[str] | None = None,
) -> None:
    """Clean a folder-style title before the overview."""
    title = metadata.get('title')
    if not isinstance(title, str):
        return
    original = title.strip()
    if not original:
        return
    if schema.repo_key == 'extra-content-partners':
        from metadata.extra_content import partner_display_name

        updated = partner_display_name(original)
        if updated == original:
            return
        metadata['title'] = updated
        message = f'Title updated from "{original}" to "{updated}".'
        if notices is not None:
            notices.append(message)
        return
    spaced = fixed_metadata_title(original, project_name)
    if spaced is None:
        updated = format_custom_choice_value(original)
        if updated == original:
            return
        metadata['title'] = updated
        message = f'Title updated from "{original}" to "{updated}".'
        if notices is not None:
            notices.append(message)
        return
    max_length = next(
        (spec.max_length for spec in schema.fields if spec.key == 'title'),
        None,
    )
    if max_length is not None and len(spaced) > max_length:
        message = (
            f'Title "{original}" stays as saved. '
            f'With spaces it would pass {max_length} characters.'
        )
    else:
        updated = format_custom_choice_value(spaced)
        metadata['title'] = updated
        message = f'Title updated from "{original}" to "{updated}".'
    if notices is not None:
        notices.append(message)


def print_between_separators(*lines: str) -> None:
    """Print *lines* between full-width dash rules, with a blank line above."""
    rule = '-' * shutil.get_terminal_size((80, 24)).columns
    print()
    print(rule)
    for line in lines:
        print(line)
    print(rule)


def print_metadata_overview(metadata: dict) -> None:
    """Print the metadata as it would be saved, under the ``metadata.json`` heading."""
    print_between_separators(
        f'Project {paint_magenta("metadata.json")} overview:',
        format_metadata_json(metadata, colour=True).rstrip('\n'),
    )


def print_metadata_notices(notices: list[str]) -> None:
    """Print automatic-fix notes between dash lines, then clear them."""
    if not notices:
        return
    print_between_separators(*(
        f'{constants.ICON_INFO} {message}' for message in notices
    ))
    notices.clear()


def _repair_image_mirror(metadata: dict) -> dict:
    from metadata.image_field import normalize_project_image_name

    thumb = metadata.get('thumbnail_image_id')
    if isinstance(thumb, str) and thumb.strip():
        thumb = normalize_project_image_name(thumb)
        metadata['thumbnail_image_id'] = thumb
        metadata['main_image_id'] = thumb
    elif isinstance(metadata.get('main_image_id'), str) and metadata['main_image_id'].strip():
        metadata['main_image_id'] = normalize_project_image_name(metadata['main_image_id'])
    return metadata


def _mark_missing(result: MetadataValidationResult, spec: FieldSpec, message: str) -> None:
    result.missing.append(message)
    result.fields_to_collect.add(spec.key)


def _mark_other(result: MetadataValidationResult, spec: FieldSpec, message: str) -> None:
    result.other.append(message)
    result.fields_to_collect.add(spec.key)


def _mark_choice(result: MetadataValidationResult, spec: FieldSpec, message: str) -> None:
    result.choice_violations.append(message)
    result.choice_fields.add(spec.key)


def _validate_required_str(
    metadata: dict,
    key: str,
    spec: FieldSpec,
    result: MetadataValidationResult,
) -> None:
    value = metadata.get(key)
    if not isinstance(value, str) or not value.strip():
        _mark_missing(result, spec, f'Missing or empty required field: {key}')


def _validate_text(metadata: dict, spec: FieldSpec, result: MetadataValidationResult) -> None:
    value = metadata.get(spec.key)
    if not isinstance(value, str) or not value.strip():
        _mark_missing(result, spec, f'Missing or empty required field: {spec.key}')
        return
    if spec.kind == 'long_text':
        from metadata.long_description import normalize_long_description, validate_long_description

        error = validate_long_description(value)
        if error:
            _mark_other(result, spec, f'{spec.key}: {error}')
            return
        value = normalize_long_description(value)
        metadata[spec.key] = value
    if spec.max_length is not None and len(value) > spec.max_length:
        _mark_other(
            result,
            spec,
            f'{spec.key} exceeds max length of {spec.max_length} characters '
            f'(got {len(value)})',
        )


def _flag_studio_template_title(
    metadata: dict,
    spec: FieldSpec,
    result: MetadataValidationResult,
) -> None:
    title = metadata.get('title')
    if isinstance(title, str) and is_studio_template_title(title):
        _mark_other(
            result, spec,
            f'title {title.strip()!r} is a Studio template title. '
            'Enter a title for this project.',
        )


def _choice_list_hint(spec: FieldSpec) -> str:
    return f'{len(spec.choices)} allowed values'


def _validate_single_choice(metadata: dict, spec: FieldSpec, result: MetadataValidationResult) -> None:
    value = metadata.get(spec.key)
    if not isinstance(value, str) or not value.strip():
        _mark_missing(result, spec, f'Missing or empty required field: {spec.key}')
        return
    if value in spec.choices:
        return
    matched = match_choice(value, spec.choices)
    if matched is not None:
        metadata[spec.key] = matched
        return
    _mark_choice(
        result, spec,
        f'{spec.key}: {value!r} is not in the allowed list ({_choice_list_hint(spec)})',
    )


def _validate_multi_choice(metadata: dict, spec: FieldSpec, result: MetadataValidationResult) -> None:
    raw = metadata.get(spec.key)
    if spec.key == 'type':
        value = normalize_project_types(raw)
        if value and raw != value:
            metadata[spec.key] = value
    else:
        value = raw
    if value is None:
        if spec.allow_empty:
            metadata[spec.key] = []
            return
        _mark_missing(result, spec, f'Missing required field: {spec.key}')
        return
    if not isinstance(value, list) or (not value and not spec.allow_empty):
        _mark_missing(result, spec, f'{spec.key} must be a non-empty list')
        return
    if not value:
        metadata[spec.key] = []
        return
    metadata[spec.key] = value
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            _mark_missing(result, spec, f'{spec.key} contains an invalid entry')
            return
        if item in spec.choices:
            continue
        matched = match_choice(item, spec.choices)
        if matched is not None:
            value[index] = matched
            continue
        _mark_choice(
            result, spec,
            f'{spec.key}: {item!r} is not in the allowed list ({_choice_list_hint(spec)})',
        )


def _validate_derived_workflow(metadata: dict, spec: FieldSpec, result: MetadataValidationResult) -> None:
    types = normalize_project_types(metadata.get('type'))
    if not types:
        return
    expected = workflow_for_types(types)
    actual = metadata.get('workflow')
    if actual is None:
        metadata['workflow'] = expected
        return
    if not isinstance(actual, list) or not actual:
        _mark_missing(result, spec, f'{spec.key} must be a non-empty list')
        return
    if actual != expected:
        _mark_other(
            result,
            spec,
            f'{spec.key} does not match project type '
            f'(expected {expected!r}, got {actual!r})',
        )


def _validate_derived_algorithm(
    metadata: dict,
    spec: FieldSpec,
    result: MetadataValidationResult,
    project_name: str | None,
    project_path: Path | None,
) -> None:
    """Prefer existing algorithm; fill from ``.improj`` when missing. Apply vision defaults."""
    if not project_name or project_path is None:
        if not metadata.get(spec.key):
            _mark_other(
                result,
                spec,
                f'{spec.key} cannot be derived without project path and name',
            )
        return
    try:
        from metadata.improj import (
            algorithm_from_improj,
            apply_vision_metadata_defaults,
        )
        improj_algorithm = algorithm_from_improj(project_path, project_name)
    except ValueError as exc:
        if not metadata.get(spec.key):
            _mark_other(result, spec, str(exc))
        return

    actual = metadata.get(spec.key)
    if not isinstance(actual, str) or not actual.strip():
        metadata[spec.key] = improj_algorithm
    elif actual not in spec.choices:
        matched = None
        from metadata.choices import match_choice
        matched = match_choice(actual, spec.choices)
        if matched is not None:
            metadata[spec.key] = matched
        else:
            # Keep improj value when the file has an unknown custom algorithm.
            metadata[spec.key] = improj_algorithm

    apply_vision_metadata_defaults(metadata, only_missing_kit=True)
    if metadata.get(spec.key) not in spec.choices:
        _mark_choice(
            result, spec,
            f'{spec.key}: {metadata.get(spec.key)!r} is not in the allowed list '
            f'({_choice_list_hint(spec)})',
        )


def _validate_image_mirror(metadata: dict, spec: FieldSpec, result: MetadataValidationResult) -> None:
    if not isinstance(metadata.get('main_image_id'), str) or not metadata['main_image_id'].strip():
        _mark_missing(result, spec, 'Missing or empty required field: main_image_id')


def _validate_brand(
    metadata: dict,
    spec: FieldSpec,
    result: MetadataValidationResult,
    *,
    allow_new: bool = False,
) -> None:
    brand_image_id = metadata.get('brand_image_id')
    brand_url = metadata.get('brand_url')
    if not isinstance(brand_image_id, str) or not brand_image_id.strip():
        _mark_missing(result, spec, 'Missing or empty required field: brand_image_id')
        return
    if not isinstance(brand_url, str) or not brand_url.strip():
        _mark_missing(result, spec, 'Missing or empty required field: brand_url')
        return
    if brand_image_id not in BRAND_IMAGE_ID:
        if brand_image_id.lower().endswith('.webp') and allow_new:
            if message := _brand_url_problem(brand_url):
                _mark_other(result, spec, message)
            return
        if brand_image_id.lower().endswith('.webp'):
            message = (
                f'brand_image_id: {brand_image_id!r} is a new partner, not one of the '
                f'{len(BRAND_IMAGE_ID)} known brands'
            )
        else:
            message = (
                f'brand_image_id: {brand_image_id!r} is not an image file name, '
                f'for example acme.webp'
            )
        _mark_choice(result, spec, message)
        if message := _brand_url_problem(brand_url):
            _mark_other(result, spec, message)
        return
    expected_url = brand_for_image(brand_image_id).brand_url
    if brand_url != expected_url:
        _mark_other(
            result,
            spec,
            f'brand_url does not match brand_image_id '
            f'(expected {expected_url!r}, got {brand_url!r})',
        )


def _brand_url_problem(brand_url: str) -> str | None:
    """A saved brand address that is not https, or that still needs ``www.``."""
    if brand_url_error(brand_url):
        return (
            f'brand_url: {brand_url!r} is not an absolute https:// URL, '
            'for example https://www.acme.example'
        )
    if error := www_missing_error(brand_url):
        return f'brand_url: {error}'
    return None


def _validate_links(
    metadata: dict,
    spec: FieldSpec,
    result: MetadataValidationResult,
    project_name: str | None = None,
) -> None:
    links = metadata.get('links')
    if links is None:
        _mark_missing(result, spec, 'Missing required field: links')
        return
    if not isinstance(links, list) or not links:
        _mark_missing(result, spec, 'links must be a non-empty list')
        return
    for index, link in enumerate(links, start=1):
        if not isinstance(link, dict):
            _mark_missing(result, spec, f'links[{index}] must be an object')
            return
        required_keys = ('label', 'url')
        if spec.kind != 'model_zoo_aurix_links' or link.get('label') != 'GitHub':
            required_keys = ('label', 'url', 'heading', 'sub-heading')
        for key in required_keys:
            if not isinstance(link.get(key), str) or not link[key].strip():
                _mark_missing(result, spec, f'links[{index}] missing or empty {key!r}')
                return
        if spec.kind == 'accelerator_links' and is_studio_template_link(link['url']):
            _mark_other(
                result, spec,
                f'links[{index}] url still points at a Studio template '
                f'({STUDIO_TEMPLATE_LINK_MARKER}). Replace it with this project\'s link.',
            )
            return
        if link.get('label') != 'GitHub' and '://github.com/' not in link['url']:
            # Generated GitHub links use github.com, which is the real address.
            # Every other saved link follows the same www. rule as a typed link.
            if error := www_missing_error(link['url']):
                _mark_other(result, spec, f'links[{index}] url: {error}')
                return
        _repair_github_link_url(link, project_name)


def _repair_github_link_url(link: dict, project_name: str | None) -> None:
    """Silently align a GitHub project link's trailing path segment with *project_name*."""
    if not project_name:
        return
    marker = '/tree/main/'
    url = link['url']
    if link.get('label') != 'GitHub' or marker not in url:
        return
    base, _, _tail = url.partition(marker)
    corrected = f'{base}{marker}{project_name}'
    if corrected != url:
        link['url'] = corrected


def _validate_videos(metadata: dict, spec: FieldSpec, result: MetadataValidationResult) -> None:
    from metadata.video_link import video_link_error
    from metadata.video_prompt import (
        VIDEO_DESCRIPTION_MAX_LENGTH,
        VIDEO_TITLE_MAX_LENGTH,
        _normalize_videos,
    )

    videos = metadata.get('videos')
    if videos is None:
        if spec.required:
            _mark_missing(result, spec, 'Missing required field: videos')
        return
    normalized = _normalize_videos(videos)
    if normalized is None:
        metadata.pop('videos', None)
        if spec.required:
            _mark_missing(result, spec, 'Missing required field: videos')
        return
    if len(normalized) > 1:
        _mark_other(result, spec, 'videos can contain only one video')
        return
    metadata['videos'] = normalized
    video = normalized[0]
    if len(video['title']) > VIDEO_TITLE_MAX_LENGTH:
        _mark_other(
            result, spec,
            f'videos title exceeds max length of {VIDEO_TITLE_MAX_LENGTH} characters',
        )
        return
    if len(video['description']) > VIDEO_DESCRIPTION_MAX_LENGTH:
        _mark_other(
            result, spec,
            f'videos description exceeds max length of {VIDEO_DESCRIPTION_MAX_LENGTH} characters',
        )
        return
    error = video_link_error(video['link'])
    if error:
        _mark_other(result, spec, f'videos[1] link: {error}')
