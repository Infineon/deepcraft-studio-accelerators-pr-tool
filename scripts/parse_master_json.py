"""Parse deepcraft.infineon.com/master.json for metadata filter values."""
import json
import pathlib
import sys
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'pr_tool'))
from metadata.choices import (
    INFINEON_BRAND_IMAGE_ID,
    INFINEON_BRAND_URL,
    PARTNER_BRAND_IMAGE_ID,
    PARTNER_BRAND_URL,
)

URL = 'https://deepcraft.infineon.com/master.json'
FIELDS = (
    'domain', 'application', 'use_case', 'kit', 'device',
    'brand_image_id', 'brand_url',
)

# deepcraft.png and deepcraft.webp are the same asset on the AI Hub.
BRAND_IMAGE_ID_ALIASES = {'deepcraft.png': 'deepcraft.webp'}


def normalize_field_value(field: str, value: str) -> str:
    if field == 'brand_image_id':
        return BRAND_IMAGE_ID_ALIASES.get(value, value)
    if field == 'brand_url' and value == INFINEON_BRAND_URL:
        return value
    return value


def load_master(path: pathlib.Path | None) -> list[dict]:
    if path:
        data = json.loads(path.read_text(encoding='utf-8'))
    else:
        with urllib.request.urlopen(URL, timeout=60) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    if isinstance(data, dict):
        for key in ('projects', 'items', 'models', 'data'):
            if key in data and isinstance(data[key], list):
                return data[key]
        return list(data.values()) if data else []
    if isinstance(data, list):
        return data
    raise TypeError(f'Unexpected master.json shape: {type(data)}')


def unique_values(projects: list[dict], field: str) -> list[str]:
    values: set[str] = set()
    for project in projects:
        if not isinstance(project, dict):
            continue
        raw = project.get(field)
        if raw is None:
            continue
        if isinstance(raw, str):
            values.add(normalize_field_value(field, raw))
        elif isinstance(raw, list):
            for item in raw:
                if isinstance(item, str) and item.strip():
                    values.add(normalize_field_value(field, item))
    return sorted(values, key=str.casefold)


def _print_brand_group(field: str, infineon: list[str], partner: list[str]) -> None:
    print(f'\n{field} ({len(infineon) + len(partner)}):')
    if infineon:
        print('  Infineon brand:')
        for v in infineon:
            print(f'    {v!r}')
    if partner:
        print('  Partner brand:')
        for v in partner:
            print(f'    {v!r}')


def main() -> None:
    path = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
    projects = load_master(path)
    print(f'Projects: {len(projects)}')
    for field in FIELDS:
        vals = unique_values(projects, field)
        if field == 'brand_image_id':
            _print_brand_group(
                field,
                [v for v in vals if v in INFINEON_BRAND_IMAGE_ID],
                [v for v in vals if v in PARTNER_BRAND_IMAGE_ID],
            )
            continue
        if field == 'brand_url':
            _print_brand_group(
                field,
                [v for v in vals if v == INFINEON_BRAND_URL],
                [v for v in vals if v in PARTNER_BRAND_URL],
            )
            continue
        print(f'\n{field} ({len(vals)}):')
        for v in vals:
            print(f'  {v!r}')


if __name__ == '__main__':
    main()
