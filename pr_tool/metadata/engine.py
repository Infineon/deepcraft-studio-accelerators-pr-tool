"""Walk a metadata schema and collect field values interactively."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from typing import Any

from metadata.choices import (
    Brand,
    INFINEON_BRAND,
    METRIC_LABELS,
    NEW_BRAND_PARTNER_LABEL,
    PARTNER_BRANDS,
    accelerator_links,
    brand_for_image,
    brand_url_error,
    is_known_brand_image,
    model_zoo_psoc_links,
    model_zoo_aurix_links,
    normalize_project_types,
)
from metadata.rules import (
    devices_for_kits,
    domains_for_sensors,
    image_names_for_applications,
    image_names_for_context,
    image_names_for_domains,
    sensor_groups,
    use_cases_for_applications,
    use_cases_for_context,
    use_cases_for_domains,
    with_project_use_case,
    workflow_for_types,
)
from metadata.improj import (
    VISION_DEVICES,
    VISION_KITS,
    VISION_SENSORS,
    algorithm_from_improj,
    apply_vision_metadata_defaults,
    is_vision_algorithm,
)
from metadata.image_field import select_project_image
from metadata.link_check import link_response_error
from metadata.long_description_prompt import input_html_text
from metadata.prompts import (
    confirm,
    field_progress_prefix,
    input_choice,
    input_choices,
    input_grouped_choice,
    input_metric_value,
    input_str,
    input_suggested_text,
    set_field_progress,
    warn,
)
from project_layouts import title_with_spaces
from metadata.schema import FieldSpec, MetadataSchema
from metadata.video_prompt import collect_videos, videos_are_empty

# Fields that must come from the listed options; a new value is kept only after confirmation.
LISTED_ONLY_FIELD_KEYS = ('sensors', 'domain', 'use_case')

# Filled in automatically on every run, so they never show or count a step.
_AUTOMATIC_KINDS = (
    'derived_workflow',
    'image_mirror',
    'accelerator_links',
    'model_zoo_psoc_links',
    'model_zoo_aurix_links',
)


def _is_asked(
    field: FieldSpec,
    *,
    result: dict,
    previous: dict,
    review_pass: bool,
    vision: dict | None,
) -> bool:
    """True when the user is asked this field, given the answers so far.

    Fields the tool fills in (workflow, copied image, links, a domain or device
    that follows the sensors or kit, and the vision defaults) are not asked.
    """
    if field.kind in _AUTOMATIC_KINDS:
        return False
    if field.kind == 'derived_algorithm':
        return review_pass
    if field.key in ('sensors', 'kit') and vision is not None and not review_pass:
        return False
    if field.key == 'domain':
        return domains_for_sensors(_selected_list(result, previous, 'sensors')) is None
    if field.key == 'device':
        if vision is not None and not review_pass:
            return False
        kits = result.get('kit') or previous.get('kit')
        if isinstance(kits, list) and kits and devices_for_kits(kits) is not None:
            return False
    return True


def _noted(message: str) -> str:
    """A derived-field line, with the field counter when one is active."""
    return f'\n{field_progress_prefix()}{message}'


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

    if 'sensors' in result and isinstance(result.get('sensors'), list):
        sensors = result['sensors']
    elif isinstance(previous.get('sensors'), list):
        sensors = previous['sensors']
    else:
        sensors = None
    if isinstance(sensors, list) and sensors:
        allowed_domains = domains_for_sensors(sensors)
        if allowed_domains:
            result['domain'] = list(allowed_domains)


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
        'kit': kits,
        'device': devices,
    }


def _selected_list(result: dict, previous: dict, key: str) -> list[str]:
    value = result.get(key)
    if isinstance(value, list) and value:
        return [item for item in value if isinstance(item, str)]
    value = previous.get(key)
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def _collect_domain(
    field: FieldSpec,
    *,
    previous: dict,
    result: dict,
) -> list[str]:
    """Select every domain the sensors map to, or prompt when a sensor has no rule."""
    allowed = domains_for_sensors(_selected_list(result, previous, 'sensors'))
    if allowed:
        print(_noted(f'Domain derived from sensor(s): {", ".join(allowed)}'))
        return list(allowed)
    prev_value = previous.get(field.key)
    default = prev_value if isinstance(prev_value, list) else None
    return input_choices(
        field.label,
        list(field.choices),
        default=default,
        allow_custom=field.allow_custom,
        prefer_listed=field.key in LISTED_ONLY_FIELD_KEYS,
    )


def _sensor_prompt_groups(choices: list[str]) -> list[tuple[str, list[str]]]:
    """Sensor names under their domain, for the choice prompt."""
    return sensor_groups(choices)


def _follows_scope(
    subject: str,
    applications: list[str],
    domains: list[str],
    by_application: list[str] | None,
    by_domain: list[str] | None,
    *,
    empty_noun: str,
) -> None:
    """Say which application and domain lists a prompt is using."""
    lines: list[str] = []
    if by_application is not None:
        lines.append(f'application(s): {", ".join(applications)}')
    if by_domain is not None:
        lines.append(f'domain(s): {", ".join(domains)}')
    if not lines:
        return
    print(f'\n{subject} follow the selected {lines[0]}')
    for line in lines[1:]:
        print(f'and the selected {line}')
    if by_application is not None and by_domain is not None:
        if not set(by_application) & set(by_domain):
            print(f'  No listed {empty_noun} fits both, so the list follows the domain.')


def _use_case_scope(applications: list[str], domains: list[str]) -> None:
    """Say which application and domain lists the use-case prompt is using."""
    _follows_scope(
        'Use cases',
        applications,
        domains,
        use_cases_for_applications(applications),
        use_cases_for_domains(domains),
        empty_noun='use case',
    )


def _collect_use_case(
    field: FieldSpec,
    *,
    previous: dict,
    result: dict,
) -> list[str]:
    """Offer the use cases that fit the selected applications and domains.

    A use case already saved in the file stays as the current value, including
    one that is not in the suggested list. Enter keeps it.
    """
    applications = _selected_list(result, previous, 'application')
    domains = _selected_list(result, previous, 'domain')
    allowed = use_cases_for_context(applications, domains)
    algorithm = result.get('algorithm') or previous.get('algorithm')
    filtered = with_project_use_case(
        list(allowed) if allowed is not None else None,
        algorithm,
    )
    choices = filtered if filtered is not None else list(field.choices)
    prev_value = previous.get(field.key)
    default = prev_value if isinstance(prev_value, list) and prev_value else None
    _use_case_scope(applications, domains)
    return input_choices(
        field.label,
        choices,
        default=default,
        allow_custom=field.allow_custom,
        prefer_listed=field.key in LISTED_ONLY_FIELD_KEYS,
    )


def _collect_device(
    field: FieldSpec,
    *,
    previous: dict,
    result: dict,
) -> list[str]:
    """Use the kit mapping. Ask only when a kit has no device."""
    kits = result.get('kit') or previous.get('kit')
    derived = None
    if isinstance(kits, list) and kits:
        derived = devices_for_kits(kits)
    if derived is not None:
        print(_noted(f'Device(s) derived from kit: {", ".join(derived)}'))
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
        print(_noted(f'Workflow derived from project type: {", ".join(workflows)}'))
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
        print(_noted(f'Algorithm derived from {project_name}.improj ProjectType: {derived}'))
        return derived
    default = previous.get(field.key) if isinstance(previous.get(field.key), str) else derived
    print(f'\nDefault from {project_name}.improj ProjectType: {derived}')
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
    while True:
        brand_image_id = input_str(
            'Brand image file name',
            max_len=None,
            default=image_default,
        )
        if brand_image_id.lower().endswith('.webp'):
            break
        warn('Enter an image file name ending in .webp, for example acme.webp.')
        image_default = None
    while True:
        brand_url = input_str(
            'Brand URL',
            max_len=None,
            default=url_default,
        )
        error = brand_url_error(brand_url) or link_response_error(brand_url)
        if error is None:
            break
        warn(error)
        url_default = None
    return Brand(
        label=NEW_BRAND_PARTNER_LABEL,
        brand_image_id=brand_image_id,
        brand_url=brand_url,
    )


def _collect_brand(previous: dict, *, fallback: str | None = None) -> Brand:
    prev_image = previous.get('brand_image_id')
    default = None
    if prev_image:
        if is_known_brand_image(prev_image):
            default = brand_for_image(prev_image).label
        else:
            default = NEW_BRAND_PARTNER_LABEL
    elif fallback:
        default = fallback
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
    print(_noted('Enter a value for each metric (labels are predefined).'))
    metrics: list[dict] = []
    for label in METRIC_LABELS:
        value = input_metric_value(label, default=previous_values.get(label))
        if value:
            metrics.append({'label': label, 'value': value})
    return metrics or None


def _collect_image(
    args: Namespace,
    *,
    use_cli_args: bool,
    previous: dict,
    result: dict,
) -> str:
    image_arg = args.image if use_cli_args else None
    tag_arg = args.tag if use_cli_args else None
    default = previous.get('thumbnail_image_id') or previous.get('main_image_id')
    applications = _selected_list(result, previous, 'application')
    domains = _selected_list(result, previous, 'domain')
    image_names = image_names_for_context(applications, domains)
    _follows_scope(
        'Images and tags',
        applications,
        domains,
        image_names_for_applications(applications),
        image_names_for_domains(domains),
        empty_noun='image',
    )
    return select_project_image(
        image_arg=image_arg,
        tag_arg=tag_arg,
        default=default,
        image_names=image_names,
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
    repo_key: str,
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

    if field.key == 'domain':
        return _collect_domain(field, previous=previous, result=result)

    if field.key == 'use_case':
        return _collect_use_case(field, previous=previous, result=result)

    if field.key == 'device':
        if vision is not None and not review_pass:
            print(_noted(f'Device(s) derived from vision ProjectType: {", ".join(vision["device"])}'))
            return list(vision['device'])
        return _collect_device(field, previous=previous, result=result)

    if field.kind == 'brand':
        fallback = INFINEON_BRAND.label if repo_key == 'model-zoo-aurix' else None
        return _collect_brand(previous, fallback=fallback)

    if field.kind == 'text':
        if field.key == 'title' and not cli:
            saved = prev_value.strip() if isinstance(prev_value, str) else ''
            if not saved:
                suggested = title_with_spaces(project_name)
                if suggested:
                    return input_suggested_text(
                        field.label,
                        suggested,
                        field.max_length,
                        note='Suggested from the project folder name.',
                    )
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
        if field.key in ('sensors', 'kit') and vision is not None:
            auto_value = list(vision[field.key])
            if not review_pass:
                label = {
                    'sensors': 'Sensor(s)',
                    'kit': 'Kit(s)',
                }[field.key]
                print(_noted(f'{label} derived from vision ProjectType: {", ".join(auto_value)}'))
                return auto_value
            default = prev_value if isinstance(prev_value, list) and prev_value else auto_value
            print(f'\nVision ProjectType default: {", ".join(auto_value)}')
            return input_choices(
                field.label,
                list(field.choices),
                default=default,
                allow_custom=field.allow_custom,
                prefer_listed=field.key in LISTED_ONLY_FIELD_KEYS,
                groups=_sensor_prompt_groups(list(field.choices)) if field.key == 'sensors' else None,
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
                prefer_listed=field.key in LISTED_ONLY_FIELD_KEYS,
                groups=_sensor_prompt_groups(list(field.choices)) if field.key == 'sensors' else None,
            )
        if field.join_values:
            return [', '.join(chosen)]
        return chosen
    if field.kind == 'image':
        return _collect_image(
            args, use_cli_args=use_cli_args, previous=previous, result=result,
        )
    if field.kind == 'accelerator_links':
        return accelerator_links(project_name)
    if field.kind == 'model_zoo_psoc_links':
        return model_zoo_psoc_links(project_name, _kits_for_links(result, previous))
    if field.kind == 'model_zoo_aurix_links':
        return model_zoo_aurix_links(project_name)
    if field.kind == 'videos':
        return collect_videos(previous)
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
    if 'videos' in result and videos_are_empty(result.get('videos')):
        result.pop('videos', None)
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

    *review_pass*: when True (user chose to re-edit after the overview), defaults
    such as algorithm and vision sensors / kits are prompted so the user can
    change them. A device that follows a known kit is filled in without a prompt.
    """
    previous = previous or {}
    result: dict = dict(previous)
    fields = [
        field for field in schema.fields
        if only_fields is None or field.key in only_fields
    ]
    has_vision_defaults = any(spec.kind == 'derived_algorithm' for spec in schema.fields)
    asked_so_far = 0
    for position, field in enumerate(fields):
        vision = None
        if has_vision_defaults:
            vision = _vision_defaults_for_collect(
                result,
                previous,
                project_path=project_path,
                project_name=project_name,
            )
        if _is_asked(
            field, result=result, previous=previous, review_pass=review_pass, vision=vision,
        ):
            asked_so_far += 1
            remaining = sum(
                1 for later in fields[position + 1:]
                if _is_asked(
                    later, result=result, previous=previous,
                    review_pass=review_pass, vision=vision,
                )
            )
            set_field_progress(field.label, asked_so_far, asked_so_far + remaining)
        else:
            set_field_progress(None)
        try:
            value = _collect_field(
                field,
                args=args,
                use_cli_args=use_cli_args,
                previous=previous,
                result=result,
                project_name=project_name,
                project_path=project_path,
                review_pass=review_pass,
                vision_defaults=has_vision_defaults,
                repo_key=schema.repo_key,
            )
        finally:
            set_field_progress(None)
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
