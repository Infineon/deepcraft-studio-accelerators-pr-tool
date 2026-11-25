import argparse
import os
import sys
from pathlib import Path

import constants
from metadata import collect_metadata, confirm, get_metadata_schema
from metadata.schema import cli_text_max_lengths
from metadata.schemas import SCHEMAS
from target_prompts import repo_choice_help
from target_repo import get_target_repo
from project_layouts import get_project_layout

sys.path.append(os.path.dirname(os.path.abspath(__file__)))


class _RepoHelpfulParser(argparse.ArgumentParser):
    """ArgumentParser that always reminds the user of the valid --repo targets."""

    repo_choices_help: list[str] = []

    def error(self, message: str) -> None:  # type: ignore[override]
        if 'repo' in message and self.repo_choices_help:
            separator = '=' * 60
            targets = '\n'.join(f'  - {choice}' for choice in self.repo_choices_help)
            self.print_usage(sys.stderr)
            self.exit(2, (
                f'{separator}\n'
                f'{self.prog}: error: {message}\n'
                f'{separator}\n'
                f'Example:\n'
                f'  python {self.prog} --path <your-project-path> --repo <push-to-this-repo>\n'
                f'{separator}\n'
                f'Available --repo targets:\n{targets}\n'
                f'{separator}\n'
            ))
        super().error(message)


class Input:
    def __init__(self) -> None:
        repo_choices = [
            repo_choice_help(key, cfg) for key, cfg in constants.TARGET_REPOS.items()
        ]
        parser = _RepoHelpfulParser(
            description=f'Submit a project to an Infineon {constants.DEEPCRAFT} GitHub repository.',
        )
        parser.repo_choices_help = repo_choices
        parser.add_argument(
            '--repo', required=True, choices=sorted(constants.TARGET_REPOS),
            metavar='TARGET',
            help=f'Target repository. Choices: {", ".join(repo_choices)}',
        )
        parser.add_argument('--path', required=True,
                            help='The root path of the project, or the folder that holds metadata.json.')
        parser.add_argument('--name', default=None,
                            help='The name of the project, in CamelCase;  That name will also be the branch name;'
                                 'Default is the containing directory\'s name.')
        parser.add_argument('--override-metadata', action='store_true',
                            help='Override existing metadata.json file, if any, with meta-data options below.')
        parser.add_argument('--no-update', action='store_true',
                            help='Do not check for or install a newer version of the tool on startup.')
        parser.add_argument('--verbose', '-v', action='store_true',
                            help='Print every git/gh command and captured output (for debugging).')
        metadata_group = parser.add_argument_group('Project meta-data')
        registered_cli: set[str] = set()
        text_limits = cli_text_max_lengths(tuple(SCHEMAS.values()))
        for schema in SCHEMAS.values():
            schema.register_cli_flags(metadata_group, registered_cli, text_limits)
        args = parser.parse_args()
        self._args = args
        self.verbose = args.verbose
        self.repo_key = args.repo
        self.target_repo = get_target_repo(args.repo)
        self._content_category = None
        self._metadata_schema = None
        if not self.target_repo.has_content_categories:
            self._metadata_schema = get_metadata_schema(args.repo)
        self.project_path = Path(args.path).resolve()
        self.project_name = args.name or self.project_path.name
        self.card_name_from_title = (
            self.target_repo.push_metadata_only
            and not (self.project_path / 'metadata.json').is_file()
        )
        if not self.card_name_from_title:
            get_project_layout(self.target_repo.project_layout).validate_project_name(
                self.project_name,
            )
        if not self.project_path.exists():
            if not self._can_create_project_path():
                raise ValueError(f'Project path does not exist: {self.project_path}')
            print(f'Project path does not exist: {self.project_path}')
            if not confirm('Create this folder?'):
                raise ValueError(f'Project path does not exist: {self.project_path}')
            try:
                self.project_path.mkdir(parents=True)
            except OSError as exc:
                raise ValueError(
                    f'Could not create project path {self.project_path}: {exc}',
                ) from exc
        if not self.project_path.is_dir():
            raise ValueError(f'Project path is not a directory: {self.project_path}')
        # Defer interactive collection until after the project summary is confirmed
        # in pr_tool.py (so the user can abort before filling metadata).
        self.override_metadata = args.override_metadata
        self.metadata = None

    def _can_create_project_path(self) -> bool:
        """AURIX and extra content only need a folder for metadata.json."""
        return self.target_repo.metadata_only or self.target_repo.push_metadata_only

    def select_content_category(self, key: str) -> None:
        """Choose the content folder and the schema that goes with it."""
        self._content_category = self.target_repo.category(key)
        self._metadata_schema = get_metadata_schema(self._content_category.schema_key)

    @property
    def content_category(self):
        return self._content_category

    @property
    def metadata_schema(self):
        if self._metadata_schema is None:
            raise ValueError('Select a content type before collecting metadata.')
        return self._metadata_schema

    def collect_metadata(self, *, use_cli_args: bool = True,
                         previous: dict | None = None,
                         only_fields: set[str] | None = None,
                         review_pass: bool = False) -> dict:
        return collect_metadata(
            self.metadata_schema,
            args=self._args,
            project_name=self.project_name,
            project_path=self.project_path,
            use_cli_args=use_cli_args,
            previous=previous,
            only_fields=only_fields,
            review_pass=review_pass,
            card_type=None if self._content_category is None else self._content_category.type_label,
        )
