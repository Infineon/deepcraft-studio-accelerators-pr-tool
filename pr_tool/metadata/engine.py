"""Walk a metadata schema and collect field values interactively."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from typing import Any

import constants
from metadata.choices import (
    Brand,
    INFINEON_BRAND,
    METRIC_LABELS,
    NEW_BRAND_PARTNER_LABEL,
    PARTNER_BRANDS,
    accelerator_links,
    brand_for_image,
    devices_for_kits,
    is_known_brand_image,
    model_zoo_psoc_links,
    model_zoo_aurix_links,
    normalize_project_types,
    workflow_for_types,
)
from metadata.improj import (
    VISION_DEVICES,
    VISION_DOMAIN,
    VISION_KITS,
    VISION_SENSORS,
    algorithm_from_improj,
    apply_vision_metadata_defaults,
    is_vision_algorithm,
)
from metadata.image_field import select_project_image
from metadata.prompts import (
    confirm,
    input_choice,
    input_choices,
    input_grouped_choice,
    input_html_text,
    input_metric_value,
    input_str,
)
from metadata.schema import FieldSpec, MetadataSchema
from metadata.video_link import video_link_error

def _order_metadata(metadata: dict, schema: MetadataSchema) -> dict:
    """Return metadata with keys in schema field order."""
    ordered: dict = {}
    for key in schema.field_order:
        if key in metadata:
            ordered[key] = metadata[key]
    return ordered


def _apply_derived_fields(result: dict, previous: dict) -> None:
    types = normalize_project_types(result.get('type', previous.get('type')))
    if types:
        result['type'] = types
        result['workflow'] = workflow_for_types(types)

    kits = result.get('kit')
    if not isinstance(kits, list) or not kits:
        kits = previous.get('kit') if isinstance(previous.get('kit'), list) else None
    if isinstance(kits, list) and kits:
        derived_devices = devices_for_kits(kits)
        if derived_devices is not None:
            result['device'] = derived_devices


def _resolve_algorithm(
    result: dict,
    previous: dict,
    *,
    project_path: Path,
    project_name: str,
) -> str | None:
    algorithm = result.get('algorithm') or previous.get('algorithm')
    if is_vision_algorithm(algorithm) or (
        isinstance(algorithm, str) and algorithm in (
            'Classification', 'Regression', 'Object Detection', 'Image Classification',
        )
    ):
        return algorithm if isinstance(algorithm, str) else None
    try:
        return algorithm_from_improj(project_path, project_name)
    except ValueError:
        return algorithm if isinstance(algorithm, str) else None


def _vision_defaults_for_collect(
    result: dict,
    previous: dict,
    *,
    project_path: Path,
    project_name: str,
) -> dict | None:
    """Vision quick-fill values, or ``None`` when this is not a vision Studio project."""
    algorithm = _resolve_algorithm(
        result, previous, project_path=project_path, project_name=project_name,
    )
    if not is_vision_algorithm(algorithm):
        return None
    kits = list(VISION_KITS)
    devices = devices_for_kits(kits) or list(VISION_DEVICES)
    return {
        'algorithm': algorithm,
        'sensors': list(VISION_SENSORS),
        'domain': list(VISION_DOMAIN),
        'kit': kits,
        'device': devices,
    }


def _collect_device(
    field: FieldSpec,
    *,
    previous: dict,
    result: dict,
    review_pass: bool,
) -> list[str]:
    kits = result.get('kit') or previous.get('kit')
    derived = None
    if isinstance(kits, list) and kits:
        derived = devices_for_kits(kits)
    default = previous.get(field.key) if isinstance(previous.get(field.key), list) else None
    if derived is not None and not default:
        default = derived
    if derived is not None and not review_pass:
        print(f'\nDevice(s) derived from kit: {", ".join(derived)}')
        return derived
    if review_pass:
        print('\n(Press Enter to keep the default; or pick other device(s) from the list.)')
    return input_choices(
        field.label,
        list(field.choices),
        default=default,
        allow_custom=field.allow_custom,
    )


def _collect_workflow(result: dict, previous: dict) -> list[str]:
    types = normalize_project_types(result.get('type', previous.get('type')))
    workflows = workflow_for_types(types)
    if workflows:
        print(f'\nWorkflow derived from project type: {", ".join(workflows)}')
    return workflows


def _collect_algorithm(
    field: FieldSpec,
    *,
    project_path: Path,
    project_name: str,
    previous: dict,
    review_pass: bool,
) -> str:
    derived = algorithm_from_improj(project_path, project_name)
    if not review_pass:
        print(f'\nAlgorithm derived from {project_name}.improj ProjectType: {derived}')
        return derived
    default = previous.get(field.key) if isinstance(previous.get(field.key), str) else derived
    print(f'\nDefault from {project_name}.improj ProjectType: {derived}')
    print('(Press Enter to keep the default, or pick another algorithm.)')
    return input_choice(
        field.label,
        list(field.choices),
        default=default,
        allow_custom=False,
    )

def _cli_dest(flag: str) -> str:
    return flag.lstrip('-').replace('-', '_')


def _cli_value(args: Namespace, field: FieldSpec) -> Any:
    if not field.cli_flag or field.kind == 'image':
        return None
    return getattr(args, _cli_dest(field.cli_flag), None)


def _collect_custom_brand(previous: dict) -> Brand:
    prev_image = previous.get('brand_image_id')
    prev_url = previous.get('brand_url')
    image_default = prev_image if isinstance(prev_image, str) and not is_known_brand_image(prev_image) else None
    url_default = prev_url if isinstance(prev_url, str) and image_default else None
    print('\nEnter brand details for the new brand/partner.')
    brand_image_id = input_str(
        'Brand image file name',
        max_len=None,
        default=image_default,
    )
    brand_url = input_str(
        'Brand URL',
        max_len=None,
        default=url_default,
    )
    return Brand(
        label=NEW_BRAND_PARTNER_LABEL,
        brand_image_id=brand_image_id,
        brand_url=brand_url,
    )


def _collect_brand(previous: dict) -> Brand:
    prev_image = previous.get('brand_image_id')
    default = None
    if prev_image:
        if is_known_brand_image(prev_image):
            default = brand_for_image(prev_image).label
        else:
            default = NEW_BRAND_PARTNER_LABEL
    groups = [
        ('Infineon brand:', [INFINEON_BRAND.label]),
        ('Partner brand:', [brand.label for brand in PARTNER_BRANDS]),
        ('Other:', [NEW_BRAND_PARTNER_LABEL]),
    ]
    label = input_grouped_choice(
        'Brand', groups, default=default, allow_custom=False,
    )
    if label == NEW_BRAND_PARTNER_LABEL:
        return _collect_custom_brand(previous)
    for brand in (INFINEON_BRAND, *PARTNER_BRANDS):
        if brand.label == label:
            return brand
    raise ValueError(f'Unknown brand choice: {label!r}')


def _metrics_by_label(metrics: list[dict] | None) -> dict[str, str]:
    by_label: dict[str, str] = {}
    if not metrics:
        return by_label
    for entry in metrics:
        if isinstance(entry, dict):
            label = entry.get('label')
            value = entry.get('value')
            if isinstance(label, str) and isinstance(value, str) and value:
                by_label[label] = value
    return by_label


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
        videos.append({
            'title': title.strip(),
            'description': description.strip(),
            'link': link.strip(),
        })
    return videos or None


def _collect_video_link(default: str | None = None) -> str:
    print(
        '  Single video URL only (for example https://youtu.be/...). '
        'Playlists and regular web pages are not allowed.',
    )
    while True:
        link = input_str('Video link', default=default)
        error = video_link_error(link)
        if error is None:
            return link
        print(f'{constants.ICON_WARNING} {error}')


def _collect_videos(previous: dict) -> list[dict] | None:
    existing = _normalize_videos(previous.get('videos'))
    if existing is not None:
        print('\nExisting videos:')
        for index, video in enumerate(existing, start=1):
            print(f'  {index}. {video["title"]} — {video["link"]}')
        link_errors = [
            f'{index}. {video["link"]}: {error}'
            for index, video in enumerate(existing, start=1)
            if (error := video_link_error(video['link']))
        ]
        if link_errors:
            print(f'{constants.ICON_WARNING} Existing video links are not single-video URLs:')
            for error in link_errors:
                print(f'  {error}')
        elif confirm('Keep existing videos?'):
            return existing
    if not confirm('Add videos? (optional — answer n to skip)'):
        return None
    videos: list[dict] = []
    index = 1
    previous_entries = existing or []
    while True:
        defaults = previous_entries[index - 1] if index <= len(previous_entries) else {}
        print(f'\nVideo {index}')
        title = input_str(
            'Video title',
            default=defaults.get('title') if isinstance(defaults.get('title'), str) else None,
        )
        description = input_str(
            'Video description',
            default=(
                defaults.get('description')
                if isinstance(defaults.get('description'), str)
                else None
            ),
        )
        link = _collect_video_link(
            defaults.get('link') if isinstance(defaults.get('link'), str) else None,
        )
        videos.append({
            'title': title,
            'description': description,
            'link': link,
        })
        if not confirm('Add another video?'):
            break
        index += 1
    return videos or None


def _collect_metrics(previous: dict) -> list[dict] | None:
    existing = previous.get('metrics')
    if existing is not None and confirm('Keep existing performance metrics?'):
        return list(existing)
    if not confirm('Add performance metrics? (optional — answer n to skip)'):
        return None
    previous_values = _metrics_by_label(existing if isinstance(existing, list) else None)
    print('\nEnter a value for each metric (labels are predefined).')
    metrics: list[dict] = []
    for label in METRIC_LABELS:
        value = input_metric_value(label, default=previous_values.get(label))
        if value:
            metrics.append({'label': label, 'value': value})
    return metrics or None


def _collect_image(args: Namespace, *, use_cli_args: bool, previous: dict) -> str:
    image_arg = args.image if use_cli_args else None
    tag_arg = args.tag if use_cli_args else None
    default = previous.get('thumbnail_image_id') or previous.get('main_image_id')
    return select_project_image(
        image_arg=image_arg,
        tag_arg=tag_arg,
        default=default,
    )


def _kits_for_links(result: dict, previous: dict) -> list[str]:
    kits = result.get('kit') or previous.get('kit')
    if isinstance(kits, list) and kits:
        return list(kits)
    raise ValueError('At least one kit must be selected before building project links')


def _collect_field(
    field: FieldSpec,
    *,
    args: Namespace,
    use_cli_args: bool,
    previous: dict,
    result: dict,
    project_name: str,
    project_path: Path,
    review_pass: bool,
    vision_defaults: bool,
) -> Any:
    prev_value = previous.get(field.key)
    cli = _cli_value(args, field) if use_cli_args else None
    vision = None
    if vision_defaults:
        vision = _vision_defaults_for_collect(
            result,
            previous,
            project_path=project_path,
            project_name=project_name,
        )

    if field.kind == 'image_mirror':
        return result.get('thumbnail_image_id', prev_value)

    if field.kind == 'derived_workflow':
        return _collect_workflow(result, previous)

    if field.kind == 'derived_algorithm':
        return _collect_algorithm(
            field,
            project_path=project_path,
            project_name=project_name,
            previous=previous,
            review_pass=review_pass,
        )

    if field.key == 'device':
        if vision is not None and not review_pass:
            print(f'\nDevice(s) derived from vision ProjectType: {", ".join(vision["device"])}')
            return list(vision['device'])
        return _collect_device(
            field, previous=previous, result=result, review_pass=review_pass,
        )

    if field.kind == 'brand':
        return _collect_brand(previous)

    if field.kind == 'text':
        return cli or input_str(
            field.label,
            field.max_length,
            default=prev_value if isinstance(prev_value, str) else None,
        )
    if field.kind == 'long_text':
        return cli or input_html_text(
            field.label,
            field.max_length,
            default=prev_value if isinstance(prev_value, str) else None,
        )
    if field.kind == 'url':
        return cli or input_str(
            field.label,
            field.max_length,
            default=prev_value if isinstance(prev_value, str) else None,
        )
    if field.kind == 'single_choice':
        default = prev_value if isinstance(prev_value, str) else None
        return cli or input_choice(
            field.label,
            list(field.choices),
            default=default,
            allow_custom=field.allow_custom,
        )
    if field.kind == 'multi_choice':
        if field.key in ('sensors', 'domain', 'kit') and vision is not None:
            auto_value = list(vision[field.key])
            if not review_pass:
                label = {
                    'sensors': 'Sensor(s)',
                    'domain': 'Domain',
                    'kit': 'Kit(s)',
                }[field.key]
                print(f'\n{label} derived from vision ProjectType: {", ".join(auto_value)}')
                return auto_value
            default = prev_value if isinstance(prev_value, list) and prev_value else auto_value
            print(f'\nVision ProjectType default: {", ".join(auto_value)}')
            print('(Press Enter to keep the default, or pick other value(s) from the list.)')
            return input_choices(
                field.label,
                list(field.choices),
                default=default,
                allow_custom=field.allow_custom,
            )
        if field.key == 'type':
            default = normalize_project_types(prev_value) or None
        else:
            default = prev_value if isinstance(prev_value, list) else None
        if field.join_values and not default:
            default = list(field.choices)
        if cli:
            chosen = list(cli)
        else:
            chosen = input_choices(
                field.label,
                list(field.choices),
                default=default,
                allow_custom=field.allow_custom,
            )
        if field.join_values:
            return [', '.join(chosen)]
        return chosen
    if field.kind == 'image':
        return _collect_image(args, use_cli_args=use_cli_args, previous=previous)
    if field.kind == 'accelerator_links':
        return accelerator_links(project_name)
    if field.kind == 'model_zoo_psoc_links':
        return model_zoo_psoc_links(project_name, _kits_for_links(result, previous))
    if field.kind == 'model_zoo_aurix_links':
        return model_zoo_aurix_links(project_name)
    if field.kind == 'videos':
        return _collect_videos(previous)
    if field.kind == 'metrics':
        return _collect_metrics(previous)
    raise ValueError(f'Unknown field kind: {field.kind!r}')


def _join_choice_fields(result: dict, schema: MetadataSchema) -> None:
    """Store selected values as one comma-separated entry when the schema asks for it."""
    for field in schema.fields:
        if not field.join_values:
            continue
        values = result.get(field.key)
        if field.key == 'type':
            values = normalize_project_types(values)
        if isinstance(values, list) and values:
            result[field.key] = [', '.join(values)]


def finalize_metadata(metadata: dict, schema: MetadataSchema) -> dict:
    """Apply derived fields and return metadata in schema key order."""
    result = dict(metadata)
    _apply_derived_fields(result, metadata)
    _join_choice_fields(result, schema)
    return _order_metadata(result, schema)


def collect_metadata(
    schema: MetadataSchema,
    *,
    args: Namespace,
    project_name: str,
    project_path: Path,
    use_cli_args: bool = True,
    previous: dict | None = None,
    only_fields: set[str] | None = None,
    review_pass: bool = False,
) -> dict:
    """Build metadata dict following ``schema`` field order and rules.

    *review_pass*: when True (user chose to re-edit after the overview), auto-derived
    fields such as algorithm / vision sensors / kits are prompted with defaults so
    the user can change them.
    """
    previous = previous or {}
    result: dict = dict(previous)
    for field in schema.fields:
        if only_fields is not None and field.key not in only_fields:
            continue
        value = _collect_field(
            field,
            args=args,
            use_cli_args=use_cli_args,
            previous=previous,
            result=result,
            project_name=project_name,
            project_path=project_path,
            review_pass=review_pass,
            vision_defaults=any(
                spec.kind == 'derived_algorithm' for spec in schema.fields
            ),
        )
        if field.kind == 'brand':
            result['brand_image_id'] = value.brand_image_id
            result['brand_url'] = value.brand_url
            continue
        if value is None and not field.required:
            result.pop(field.key, None)
            continue
        result[field.key] = value
    _apply_derived_fields(result, previous)
    return finalize_metadata(result, schema)
