"""Walk a metadata schema and collect field values interactively."""

from __future__ import annotations

from argparse import Namespace
from typing import Any

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
    normalize_project_types,
    workflow_for_types,
)
from metadata.image_field import select_project_image
from metadata.prompts import (
    confirm,
    input_choice,
    input_choices,
    input_grouped_choice,
    input_metric_value,
    input_str,
)
from metadata.schema import FieldSpec, MetadataSchema


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


def _collect_device(
    field: FieldSpec,
    *,
    previous: dict,
    result: dict,
) -> list[str]:
    kits = result.get('kit') or previous.get('kit')
    if isinstance(kits, list) and kits:
        derived = devices_for_kits(kits)
        if derived is not None:
            print(f'\nDevice(s) derived from kit: {", ".join(derived)}')
            return derived
    default = previous.get(field.key) if isinstance(previous.get(field.key), list) else None
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
) -> Any:
    prev_value = previous.get(field.key)
    cli = _cli_value(args, field) if use_cli_args else None

    if field.kind == 'image_mirror':
        return result.get('thumbnail_image_id', prev_value)

    if field.kind == 'derived_workflow':
        return _collect_workflow(result, previous)

    if field.key == 'device':
        return _collect_device(field, previous=previous, result=result)

    if field.kind == 'brand':
        return _collect_brand(previous)

    if field.kind == 'text':
        return cli or input_str(
            field.label,
            field.max_length,
            default=prev_value if isinstance(prev_value, str) else None,
        )
    if field.kind == 'long_text':
        return cli or input_str(
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
        if field.key == 'type':
            default = normalize_project_types(prev_value) or None
        else:
            default = prev_value if isinstance(prev_value, list) else None
        if cli:
            return list(cli)
        return input_choices(
            field.label,
            list(field.choices),
            default=default,
            allow_custom=field.allow_custom,
        )
    if field.kind == 'image':
        return _collect_image(args, use_cli_args=use_cli_args, previous=previous)
    if field.kind == 'accelerator_links':
        return accelerator_links(project_name)
    if field.kind == 'model_zoo_psoc_links':
        return model_zoo_psoc_links(project_name, _kits_for_links(result, previous))
    if field.kind == 'metrics':
        return _collect_metrics(previous)
    raise ValueError(f'Unknown field kind: {field.kind!r}')


def finalize_metadata(metadata: dict, schema: MetadataSchema) -> dict:
    """Apply derived fields and return metadata in schema key order."""
    result = dict(metadata)
    _apply_derived_fields(result, metadata)
    return _order_metadata(result, schema)


def collect_metadata(
    schema: MetadataSchema,
    *,
    args: Namespace,
    project_name: str,
    use_cli_args: bool = True,
    previous: dict | None = None,
    only_fields: set[str] | None = None,
) -> dict:
    """Build metadata dict following ``schema`` field order and rules."""
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
