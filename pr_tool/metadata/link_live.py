"""Live check of the links a person entered into an existing metadata file.

Only links that came from a person are asked: the webpage links of an extra
content card, the address of a new brand or partner, and the video. Links the
tool adds on its own, such as the Studio, GitHub, and Model Zoo links, and the
address of a catalogue brand, are left alone.
"""

from __future__ import annotations

import constants
from metadata.choices import is_known_brand_image
from metadata.link_check import link_response_error, video_link_response_error
from metadata.schema import MetadataSchema

# (field key, where it is in the file, address, is it a video)
CustomLink = tuple[str, str, str, bool]


def custom_links(metadata: dict, schema: MetadataSchema) -> list[CustomLink]:
    """The addresses in *metadata* that a person entered, in file order."""
    found: list[CustomLink] = []
    for spec in schema.fields:
        if spec.kind == 'links':
            entries = metadata.get(spec.key)
            for number, entry in enumerate(entries if isinstance(entries, list) else [], start=1):
                url = entry.get('url') if isinstance(entry, dict) else None
                if isinstance(url, str) and url.strip():
                    found.append((spec.key, f'{spec.key}[{number}]', url.strip(), False))
        elif spec.kind == 'brand':
            image = metadata.get('brand_image_id')
            url = metadata.get('brand_url')
            if (
                isinstance(image, str) and image.strip()
                and not is_known_brand_image(image)
                and isinstance(url, str) and url.strip()
            ):
                found.append((spec.key, 'brand_url', url.strip(), False))
        elif spec.kind == 'videos':
            entries = metadata.get(spec.key)
            for number, entry in enumerate(entries if isinstance(entries, list) else [], start=1):
                link = entry.get('link') if isinstance(entry, dict) else None
                if isinstance(link, str) and link.strip():
                    found.append((spec.key, f'{spec.key}[{number}] link', link.strip(), True))
    return found


def custom_link_issues(
    metadata: dict,
    schema: MetadataSchema,
    settled: set[str],
) -> list[tuple[str, str]]:
    """Ask each custom link whether it responds. Returns ``(field key, message)`` pairs.

    *settled* holds the addresses that already responded, so they are not asked
    again. The set is updated in place. An address that does not respond is never
    added to it, so it is asked again until it is changed or removed, as when a
    link is created from scratch.
    """
    pending = [item for item in custom_links(metadata, schema) if item[2] not in settled]
    if not pending:
        return []
    print(f'\n{constants.ICON_INFO} Checking that the links in your metadata.json respond...')
    issues: list[tuple[str, str]] = []
    answers: dict[tuple[str, bool], str | None] = {}
    for key, where, url, is_video in pending:
        if (url, is_video) not in answers:
            check = video_link_response_error if is_video else link_response_error
            answers[(url, is_video)] = check(url)
        error = answers[(url, is_video)]
        if error:
            issues.append((key, f'{where}: {url} - {error}'))
        else:
            settled.add(url)
    return issues
