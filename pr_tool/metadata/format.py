import json

from metadata.schema import MetadataSchema


def format_metadata_json(metadata: dict, schema: MetadataSchema | None = None) -> str:
    """Pretty-print metadata; keys follow ``schema.field_order`` when a schema is given."""
    if not metadata:
        return '{}'
    if schema is not None:
        from metadata.engine import finalize_metadata

        metadata = finalize_metadata(metadata, schema)
    entries = [
        f'  {json.dumps(key)}: {json.dumps(value)}'
        for key, value in metadata.items()
    ]
    return '{\n' + ',\n'.join(entries) + '\n}\n'