"""Collect thumbnail/main image ids for metadata.json."""

from image_selector import (
    get_available_images,
    get_available_tags,
    get_tags_for_images,
    select_image,
)
from metadata.prompts import (
    _field_separator,
    _menu_choice,
    _saved_value_block,
    _separator,
    field_name,
    input_choice,
    input_choices,
    warn,
)

import constants


def normalize_project_image_name(name: str) -> str:
    """Ensure project images use the ``.webp`` extension (legacy ``.png`` → ``.webp``)."""
    stripped = name.strip()
    if stripped.lower().endswith('.png'):
        return f'{stripped[:-4]}.webp'
    return stripped


def select_project_image(
    *,
    image_arg: str | None,
    tag_arg: list[str] | None,
    default: str | None = None,
    image_names: list[str] | None = None,
) -> str:
    """Pick a project image.

    *image_names* limits the catalog to those files, and the tag list to the
    tags on those files. ``None`` keeps the full catalog.
    """
    if image_arg:
        return normalize_project_image_name(image_arg)
    if tag_arg:
        return normalize_project_image_name(select_image(tag_arg, names=image_names))
    catalog = get_available_images()
    if image_names is not None:
        allowed = set(image_names)
        available_images = [name for name in catalog if name in allowed] or catalog
        available_tags = get_tags_for_images(available_images)
    else:
        available_images = catalog
        available_tags = get_available_tags()
    top_sep = _field_separator()
    bottom_sep = _separator('-')
    default_normalized = normalize_project_image_name(default) if default else None
    if default_normalized:
        options = [
            _menu_choice('1', 'Auto-select based on tags'),
            _menu_choice('2', 'Pick from available images'),
        ]
        saved = _saved_value_block(default_normalized, options)
    else:
        options = [
            _menu_choice('Enter', 'Auto-select based on tags'),
            _menu_choice('1', 'Pick from available images'),
        ]
        saved = (
            f'{bottom_sep}\n'
            f'  Choose an option:\n'
            + '\n'.join(options) + '\n'
            f'{bottom_sep}\n'
        )
    prompt = (
        f'{top_sep}\n'
        f'{field_name("Project image")} - choose how to set the project image (.webp)\n'
        f'{saved}'
        f': '
    )

    def by_tags() -> str:
        tags = (
            input_choices('Tag', available_tags, coloured_name=False)
            if available_tags else []
        )
        return normalize_project_image_name(select_image(tags, names=available_images))

    def from_list() -> str | None:
        if not available_images:
            warn('No images available in the catalog.')
            return None
        print(f'\n{constants.ICON_INFO} Pick an image file name from the catalog list below (.webp).\n')
        return normalize_project_image_name(
            input_choice('Image', available_images, coloured_name=False),
        )

    while True:
        choice = input(prompt).strip()
        if default_normalized:
            if not choice:
                return default_normalized
            if choice == '1':
                return by_tags()
            if choice == '2':
                picked = from_list()
                if picked is not None:
                    return picked
                continue
            warn('Press Enter to keep it, or type 1 or 2.')
            continue
        if not choice:
            return by_tags()
        if choice == '1':
            picked = from_list()
            if picked is not None:
                return picked
            continue
        warn('Press Enter to auto-select, or type 1 to pick an image.')
