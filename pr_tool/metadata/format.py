import json

from metadata.prompts import paint_green
from metadata.schema import MetadataSchema


def format_metadata_json(
    metadata: dict,
    schema: MetadataSchema | None = None,
    *,
    colour: bool = False,
) -> str:
    """Pretty-print metadata; keys follow ``schema.field_order`` when a schema is given.

    ``colour`` paints the field names green for the on-screen overview. Names stay
    lower case as in the file. The file written to disk is always plain, so pass
    ``colour`` only when printing.
    """
    if not metadata:
        return '{}'
    if schema is not None:
        from metadata.engine import finalize_metadata

        metadata = finalize_metadata(metadata, schema)
    entries = []
    for key, value in metadata.items():
        shown_key = json.dumps(key)
        if colour:
            shown_key = paint_green(shown_key)
        entries.append(f'  {shown_key}: {json.dumps(value)}')
    return '{\n' + ',\n'.join(entries) + '\n}\n'