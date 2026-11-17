"""Prompts that apply to a target repository before metadata collection."""

import json
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from constants import ICON_INFO, ICON_WARNING
from metadata.prompts import _choice_menu, confirm, warn
from target_repo import ContentCategory, TargetRepo

if TYPE_CHECKING:
    from input import Input

RESTRICTED_MARK = 'RESTRICTED: authorized users only'


def repo_choice_help(key: str, cfg: TargetRepo) -> str:
    """One ``--repo`` choice, including content types and the restricted mark."""
    text = f'{key} ({cfg.base_repo})'
    if cfg.has_content_categories:
        types = ', '.join(category.key for category in cfg.content_categories)
        text += f' — content types: {types}'
    if cfg.restricted:
        text += f' — {RESTRICTED_MARK}'
    return text


def confirm_restricted(target_repo, *, before_push: bool, question: str) -> bool:
    """Warn about a restricted target and return whether the user confirmed."""
    if not target_repo.restricted:
        return True
    print_restricted_warning(target_repo, before_push=before_push)
    return confirm(question)


def print_restricted_warning(target_repo, *, before_push: bool) -> None:
    """Warn that only authorized users may contribute to a restricted target."""
    print()
    print('!' * 60)
    print(f'  {ICON_WARNING} RESTRICTED REPOSITORY: {target_repo.base_repo}')
    print('!' * 60)
    if before_push:
        print(f'  {ICON_WARNING} You are about to push to your fork and open a pull request')
        print(f'  against {target_repo.base_repo}.')
    else:
        print(f'  {ICON_WARNING} Target "{target_repo.label}" ({target_repo.key}).')
    print(f'  {ICON_WARNING} Only AUTHORIZED users may contribute content to this repository.')
    print('  If you are not authorized, do not continue: your pull request will')
    print('  be closed without review.')
    if before_push:
        print(f'  {ICON_INFO} This is the last confirmation before the tool contacts GitHub.')
    else:
        print(f'  {ICON_INFO} Nothing is pushed until you confirm again right before the push.')
    print('!' * 60)
    print()


def saved_card_content(
    target_repo: TargetRepo,
    metadata_path: Path,
    *,
    override: bool,
) -> tuple[ContentCategory, dict] | None:
    """Load an existing card and the content folder named by its ``type``.

    ``None`` means there is no saved card to follow, so the caller asks which
    content folder to use. The saved ``type`` is left unchanged.
    """
    if override or not target_repo.has_content_categories or not metadata_path.is_file():
        return None
    try:
        loaded = json.loads(metadata_path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f'Could not read existing {metadata_path}: {exc}') from exc
    if not isinstance(loaded, dict):
        raise ValueError(f'Existing {metadata_path} must be a JSON object.')
    saved_type = loaded.get('type')
    category = (
        target_repo.category_for_type(saved_type) if isinstance(saved_type, str) else None
    )
    if category is None:
        known = ', '.join(item.type_label for item in target_repo.content_categories)
        raise ValueError(
            f'Existing {metadata_path.name} has content type {saved_type!r}. '
            f'It must be one of: {known}.',
        )
    return category, loaded


def select_content_category_interactively(
    args: 'Input',
    print_header: Callable[..., None],
) -> None:
    """Ask which content folder the metadata file is for."""
    categories = tuple(args.target_repo.content_categories)
    print_header('Content Type', icon=ICON_INFO)
    print(f'  {ICON_INFO} "{args.target_repo.label}" groups several content folders.')
    print('  Pick the type of content you are adding.')
    print()
    label_width = max(len(category.type_label) for category in categories) + 6
    options = [
        (str(index), f'{category.type_label:<{label_width}}{category.description}')
        for index, category in enumerate(categories, start=1)
    ]
    prompt = _choice_menu('Which content folder is this AI Hub card for?', options)
    accepted = {key for key, _text in options}
    while True:
        answer = input(prompt).strip()
        if answer in accepted:
            args.select_content_category(categories[int(answer) - 1].key)
            return
        warn(f'Type a number from 1 to {len(categories)}.')
