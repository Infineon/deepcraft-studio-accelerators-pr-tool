import fnmatch
import re
from abc import ABC, abstractmethod
from pathlib import Path

from submission_exclusions import is_excluded_project_root_entry

COMMON_ROOT_FILES = ('README.md', 'metadata.json')

_CAMEL_CASE_PATTERN = re.compile(r'(?:[A-Z][a-z]*)+')
_FOLDER_BRANCH_SAFE_PATTERN = re.compile(r'^[a-zA-Z0-9]([a-zA-Z0-9._-]*[a-zA-Z0-9])?$')
_WINDOWS_RESERVED_NAMES = frozenset({
    'CON', 'PRN', 'AUX', 'NUL',
    *(f'COM{i}' for i in range(1, 10)),
    *(f'LPT{i}' for i in range(1, 10)),
})


def validate_camel_case_project_name(project_name: str) -> None:
    if not _CAMEL_CASE_PATTERN.fullmatch(project_name):
        raise ValueError(f'Project name "{project_name}" is not CamelCase')


def validate_folder_branch_safe_project_name(project_name: str) -> None:
    """Allow names valid as a local folder and as a single Git branch segment (no spaces)."""
    if not project_name:
        raise ValueError('Project name cannot be empty.')
    if not _FOLDER_BRANCH_SAFE_PATTERN.fullmatch(project_name):
        raise ValueError(
            f'Project name "{project_name}" is not valid: use letters, digits, ".", "_", or "-", '
            'must start and end with a letter or digit, and must not contain spaces.',
        )
    if '..' in project_name:
        raise ValueError(f'Project name "{project_name}" cannot contain "..".')
    if project_name.endswith('.lock'):
        raise ValueError(f'Project name "{project_name}" cannot end with ".lock".')
    if project_name.upper() in _WINDOWS_RESERVED_NAMES:
        raise ValueError(
            f'Project name "{project_name}" is a reserved Windows device name.',
        )


class ProjectLayout(ABC):
    """Validates a project folder before publishing."""

    name: str

    def validate(self, project_name: str, project_path: Path) -> None:
        self.validate_project_name(project_name)
        self._validate_common(project_path)
        self._validate_layout(project_name, project_path)

    def validate_project_name(self, project_name: str) -> None:
        """Raise ValueError if the project / branch name is invalid for this layout."""
        raise NotImplementedError

    def _validate_common(self, project_path: Path) -> None:
        for item in COMMON_ROOT_FILES:
            if not (project_path / item).is_file():
                raise ValueError(f'{item} is missing from the project root directory.')

    @abstractmethod
    def _validate_layout(self, project_name: str, project_path: Path) -> None:
        """Layout-specific rules beyond README.md and metadata.json."""


class AcceleratorLayout(ProjectLayout):
    name = 'accelerator_layout'

    def validate_project_name(self, project_name: str) -> None:
        validate_camel_case_project_name(project_name)

    def _validate_layout(self, project_name: str, project_path: Path) -> None:
        required_items = {f'{project_name}.improj', 'Data'}
        allowed_items = {
            '*.im*', 'Models', 'PreprocessorTrack',
            'Resources', 'Tools', 'Units',
        }
        project_root_items = {path.name for path in project_path.iterdir()}
        if missing_items := required_items - project_root_items:
            raise ValueError(f'Items {missing_items} are missing from project\'s root directory.')
        allowed_root_items: list[str] = []
        for pattern in required_items | allowed_items | set(COMMON_ROOT_FILES):
            allowed_root_items += fnmatch.filter(project_root_items, pattern)
        excluded_root_items = {
            name for name in project_root_items if is_excluded_project_root_entry(project_path, name)
        }
        if not_allowed_items := (
            project_root_items - set(allowed_root_items) - excluded_root_items
        ):
            raise ValueError(
                f'Items {not_allowed_items} are not allowed in project\'s root directory;\n'
                f'Allowed items are {required_items | allowed_items | set(COMMON_ROOT_FILES)}'
            )


class ModelZooPsocLayout(ProjectLayout):
    name = 'model_zoo_psoc_layout'

    def validate_project_name(self, project_name: str) -> None:
        validate_folder_branch_safe_project_name(project_name)

    def _validate_layout(self, project_name: str, project_path: Path) -> None:
        pass


LAYOUTS: dict[str, ProjectLayout] = {
    AcceleratorLayout.name: AcceleratorLayout(),
    ModelZooPsocLayout.name: ModelZooPsocLayout(),
}


def get_project_layout(key: str) -> ProjectLayout:
    try:
        return LAYOUTS[key]
    except KeyError:
        choices = ', '.join(LAYOUTS)
        raise ValueError(f'Unknown project layout {key!r}. Choose from: {choices}') from None
