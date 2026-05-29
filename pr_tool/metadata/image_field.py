"""Collect thumbnail/main image ids for metadata.json."""

from image_selector import get_available_images, get_available_tags, select_image
from metadata.prompts import _separator, input_choice, input_choices

import constants


def select_project_image(
    *,
    image_arg: str | None,
    tag_arg: list[str] | None,
    default: str | None = None,
) -> str:
    if image_arg:
        return image_arg
    if tag_arg:
        return select_image(tag_arg)
    available_images = get_available_images()
    top_sep = _separator('=')
    bottom_sep = _separator('-')
    default_line = f'>>> Press Enter to keep: {default}\n' if default else ''
    prompt = (
        f'{top_sep}\n'
        f'Project image - choose how to set the project image\n'
        f'{default_line}'
        f'  1. Auto-select based on tags\n'
        f'  2. Pick from available images\n'
        f'{bottom_sep}\n: '
    )
    while True:
        choice = input(prompt).strip()
        if not choice and default:
            return default
        if choice == '1':
            available_tags = get_available_tags()
            tags = input_choices('Tag', available_tags) if available_tags else []
            return select_image(tags)
        if choice == '2':
            if not available_images:
                print(f'{constants.ICON_WARNING} No images available in the catalog.')
                continue
            print(f'\n{constants.ICON_INFO} Pick an image file name from the catalog list below.\n')
            return input_choice('Image', available_images)
        print(f'{constants.ICON_WARNING} Please type 1 or 2.')
