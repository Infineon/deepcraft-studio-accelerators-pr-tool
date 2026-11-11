"""Reviewer notes posted as a pull request comment after the PR is created.

Each function in ``REVIEW_NOTES`` inspects the saved metadata and returns
markdown lines. Add a function and list it there to flag something else.
An empty result means no comment is posted.

``post_pull_request_comment`` and ``_post_review_comment`` send that comment.
They take the ``gh`` callable from the caller so this module does not import
the main script.
"""

from pathlib import Path
from tempfile import NamedTemporaryFile

import constants
from image_selector import DEFAULT_IMAGE, get_available_images
from metadata.choices import is_known_brand_image
from metadata.schema import MetadataSchema

# Choice fields whose saved values are compared with the catalog.
_CHOICE_KINDS = ('single_choice', 'multi_choice', 'derived_workflow', 'derived_algorithm')


def _text_values(raw: object) -> list[str]:
    if isinstance(raw, str):
        return [raw.strip()] if raw.strip() else []
    if isinstance(raw, list):
        return [item.strip() for item in raw if isinstance(item, str) and item.strip()]
    return []


def new_catalog_entries(metadata: dict, schema: MetadataSchema) -> list[str]:
    """One line per value that is not in the field's catalog list."""
    lines: list[str] = []
    for field in schema.fields:
        if field.kind not in _CHOICE_KINDS or not field.choices:
            continue
        known = set(field.choices)
        for value in _text_values(metadata.get(field.key)):
            parts = [part.strip() for part in value.split(',')] if field.join_values else [value]
            for part in parts:
                if part and part not in known:
                    lines.append(f'New {field.label.lower()}: `{part}`')
    return lines


def new_partner(metadata: dict, schema: MetadataSchema) -> list[str]:
    """A brand image that is not one of the listed partners, on its own line."""
    del schema
    image = metadata.get('brand_image_id')
    if not isinstance(image, str) or not image.strip() or is_known_brand_image(image.strip()):
        return []
    url = metadata.get('brand_url')
    url_text = url.strip() if isinstance(url, str) else ''
    if url_text:
        return [f'New partner: `{image.strip()}` — {url_text}']
    return [f'New partner: `{image.strip()}`']


def new_project_image(metadata: dict, schema: MetadataSchema) -> list[str]:
    """A project image file that is not in ``images.json``, on its own line."""
    del schema
    catalog = {name.casefold() for name in get_available_images()}
    catalog.add(DEFAULT_IMAGE.casefold())
    lines: list[str] = []
    seen: set[str] = set()
    for key in ('thumbnail_image_id', 'main_image_id'):
        value = metadata.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        name = value.strip()
        folded = name.casefold()
        if folded in catalog or folded in seen or is_known_brand_image(name):
            continue
        seen.add(folded)
        lines.append(f'New image: `{name}`')
    return lines


# Add a callable ``(metadata, schema) -> list[str]`` here to flag another case.
REVIEW_NOTES = (
    new_catalog_entries,
    new_partner,
    new_project_image,
)


def review_comment(metadata: dict, schema: MetadataSchema) -> str | None:
    """Markdown comment for reviewers, or ``None`` when nothing needs a flag.

    A new partner is pulled out of the list and shown in its own highlighted block.
    """
    lines: list[str] = []
    for note in REVIEW_NOTES:
        lines.extend(note(metadata, schema))
    if not lines:
        return None
    partners = [line for line in lines if line.startswith('New partner:')]
    others = [line for line in lines if not line.startswith('New partner:')]
    parts = [
        '> **NEW VALUES DETECTED**\n'
        '>\n'
        '> The metadata file of this project contains new values to be reviewed.',
    ]
    if others:
        parts.append('\n'.join(f'- {line}' for line in others))
    if partners:
        highlighted = '\n'.join(
            '> ' + line.replace('New partner:', '**New partner:**', 1)
            for line in partners
        )
        parts.append(f'> [!IMPORTANT]\n{highlighted}')
    return '\n\n'.join(parts) + '\n'


def _usable_gh_string(value: object) -> str | None:
    """Return a non-empty gh --jq string, or None when missing/failed."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or text == 'null':
        return None
    return text


def post_pull_request_comment(gh, head_branch: str, target_repo, body: str) -> bool:
    """Post *body* on the pull request. Falls back to the issues API."""
    body_file = NamedTemporaryFile(
        'w', encoding='utf-8', newline='\n', suffix='-pr-comment.md', delete=False,
    )
    body_path = Path(body_file.name)
    try:
        body_file.write(body)
        body_file.close()
        posted = gh(
            ['pr', 'comment', head_branch, '--body-file', str(body_path)],
            check=False,
            quiet_stderr=True,
        )
        if posted == 0:
            return True
        number = _usable_gh_string(
            gh(
                ['pr', 'view', head_branch, '--json', 'number', '--jq', '.number'],
                check=False,
                quiet_stderr=True,
            ),
        )
        if not number or not number.isdigit():
            return False
        api_posted = gh(
            [
                'api',
                f'repos/{target_repo.base_repo}/issues/{number}/comments',
                '-f', f'body=@{body_path}',
            ],
            check=False,
            quiet_stderr=True,
        )
        return api_posted == 0
    finally:
        body_path.unlink(missing_ok=True)


def _post_review_comment(gh, cli, head_branch: str, target_repo, metadata: dict, metadata_schema) -> None:
    """Comment on a newly created PR when the metadata has values to flag."""
    body = review_comment(metadata, metadata_schema)
    if not body:
        return
    cli.progress('Posting a review comment for new metadata entries...')
    if post_pull_request_comment(gh, head_branch, target_repo, body):
        print(f'  {constants.ICON_INFO} Posted a review comment for values that are not in the tool lists.')
        return
    print(
        f'  {constants.ICON_WARNING} Could not post the review comment. '
        'The pull request was still created.',
    )
