from dataclasses import dataclass

from constants import BASE_REPO_OWNER, HOST


@dataclass(frozen=True)
class TargetRepo:
    """Configuration for a GitHub repository this tool can publish to."""

    key: str
    repo_name: str
    label: str
    pr_title_template: str
    project_layout: str
    git_ignored_dirs: tuple[str, ...]

    @property
    def base_repo(self) -> str:
        return f'{BASE_REPO_OWNER}/{self.repo_name}'

    @property
    def base_repo_url(self) -> str:
        return f'{HOST}/{self.base_repo}.git'

    def pr_title(self, project_name: str) -> str:
        return self.pr_title_template.format(project_name=project_name)


def validate_target_repos_registry(target_repos: dict[str, TargetRepo]) -> None:
    """Ensure every registry entry is consistent and references a known layout."""
    from project_layouts import LAYOUTS

    for key, cfg in target_repos.items():
        if cfg.key != key:
            raise ValueError(
                f'TARGET_REPOS[{key!r}].key is {cfg.key!r}; must match the registry key',
            )
        if cfg.project_layout not in LAYOUTS:
            choices = ', '.join(LAYOUTS)
            raise ValueError(
                f'TARGET_REPOS[{key!r}] uses unknown project_layout '
                f'{cfg.project_layout!r}. Choose from: {choices}',
            )


def get_target_repo(key: str) -> TargetRepo:
    from constants import TARGET_REPOS

    try:
        return TARGET_REPOS[key]
    except KeyError:
        choices = ', '.join(TARGET_REPOS)
        raise ValueError(
            f'Unknown target repository {key!r}. Choose from: {choices}',
        ) from None
