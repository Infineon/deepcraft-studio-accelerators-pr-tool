"""Metadata field definitions and per-repository schemas."""

from __future__ import annotations

from argparse import _ArgumentGroup
from dataclasses import dataclass
from typing import Literal

FieldKind = Literal[
    'text',
    'long_text',
    'single_choice',
    'multi_choice',
    'derived_workflow',
    'derived_algorithm',
    'url',
    'image',
    'image_mirror',
    'brand',
    'accelerator_links',
    'model_zoo_psoc_links',
    'model_zoo_aurix_links',
    'videos',
    'metrics',
    'card_type',
    'card_id',
    'date',
    'links',
]


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    kind: FieldKind
    required: bool = True
    max_length: int | None = None
    choices: tuple[str, ...] = ()
    cli_flag: str | None = None
    cli_help: str | None = None
    cli_choices: tuple[str, ...] | None = None
    cli_action: str | None = None
    allow_custom: bool = True
    join_values: bool = False
    allow_empty: bool = False
    metric_note: bool = False
    choice_groups: tuple[tuple[str, tuple[str, ...]], ...] = ()

    def register_cli(self, group: _ArgumentGroup, *, max_length: int | None = None) -> None:
        from metadata.prompts import register_cli_text

        if self.kind == 'image':
            group.add_argument(
                '--tag',
                default=None,
                action='append',
                help='Tag used to auto-pick an image from images.json. '
                     'Pass --tag multiple times for more than one tag.',
            )
            group.add_argument(
                '--image',
                default=None,
                help='Image file name to use directly (e.g. "Audio.webp"). '
                     'Skips the tag-based auto-selection.',
            )
            return
        if not self.cli_flag:
            return
        if self.kind in ('text', 'long_text', 'url'):
            register_cli_text(
                group,
                flag=self.cli_flag,
                help_text=self.cli_help or self.label,
                max_length=max_length if max_length is not None else (self.max_length or 500),
            )
        elif self.kind == 'single_choice':
            group.add_argument(
                self.cli_flag,
                choices=list(self.cli_choices or self.choices),
                default=None,
                help=self.cli_help or self.label,
            )
        elif self.kind == 'multi_choice' and self.cli_action == 'append':
            group.add_argument(
                self.cli_flag,
                choices=list(self.cli_choices or self.choices),
                default=None,
                action='append',
                help=self.cli_help or self.label,
            )


def cli_text_max_lengths(schemas: tuple['MetadataSchema', ...]) -> dict[str, int]:
    """Longest text limit for each shared CLI flag, so one parser accepts every schema."""
    limits: dict[str, int] = {}
    for schema in schemas:
        for field in schema.fields:
            if field.cli_flag and field.max_length:
                limits[field.cli_flag] = max(limits.get(field.cli_flag, 0), field.max_length)
    return limits


@dataclass(frozen=True)
class MetadataSchema:
    repo_key: str
    fields: tuple[FieldSpec, ...]
    # When set, this is the saved key order, including a split brand pair.
    key_order: tuple[str, ...] | None = None

    def register_cli(self, group: _ArgumentGroup) -> None:
        for field in self.fields:
            field.register_cli(group)

    def register_cli_flags(
        self,
        group: _ArgumentGroup,
        registered: set[str],
        text_limits: dict[str, int] | None = None,
    ) -> None:
        """Register argparse flags once per schema field (shared across repositories)."""
        for field in self.fields:
            token = 'image' if field.kind == 'image' else field.cli_flag
            if not token or token in registered:
                continue
            field.register_cli(
                group,
                max_length=None if text_limits is None else text_limits.get(field.cli_flag or ''),
            )
            registered.add(token)

    @property
    def field_order(self) -> tuple[str, ...]:
        if self.key_order is not None:
            return self.key_order
        keys: list[str] = []
        for field in self.fields:
            if field.kind == 'brand':
                keys.extend(('brand_image_id', 'brand_url'))
            else:
                keys.append(field.key)
        return tuple(keys)
