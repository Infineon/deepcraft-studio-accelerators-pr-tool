"""Schema-driven metadata collection for target repositories."""

from metadata.engine import collect_metadata, finalize_metadata
from metadata.format import format_metadata_json
from metadata.prompts import confirm, confirm_metadata, confirm_new_entries
from metadata.schemas import SCHEMAS

__all__ = [
    'SCHEMAS',
    'collect_metadata',
    'finalize_metadata',
    'confirm',
    'confirm_metadata',
    'confirm_new_entries',
    'format_metadata_json',
    'get_metadata_schema',
]


def get_metadata_schema(repo_key: str):
    try:
        return SCHEMAS[repo_key]
    except KeyError:
        choices = ', '.join(sorted(SCHEMAS))
        raise ValueError(
            f'No metadata schema for repository {repo_key!r}. '
            f'Known schemas: {choices}',
        ) from None
