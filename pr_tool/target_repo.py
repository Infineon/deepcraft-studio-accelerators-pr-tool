from dataclasses import dataclass

from constants import BASE_REPO_OWNER, HOST


@dataclass(frozen=True)
class ContentCategory:
    """One content folder inside a target repository.

    ``key`` identifies the content folder in the startup menu. ``directory`` is the folder the card
    is published under. ``type_label`` is written to ``type`` in metadata.json.
    ``schema_key`` selects that content type's schema.
    """

    key: str
    directory: str
    type_label: str
    schema_key: str
    # Shown in the startup menu so the user can pick the content folder.
    description: str


@dataclass(frozen=True)
class Publication:
    """Where one card or project is committed inside a target repository."""

    repo_subpath: str
    branch_name: str
    pr_title: str


@dataclass(frozen=True)
class TargetRepo:
    """Configuration for a GitHub repository this tool can publish to."""

    key: str
    repo_name: str
    label: str
    pr_title_template: str
    project_layout: str
    git_ignored_dirs: tuple[str, ...]
    # When True, the tool writes metadata.json and exits. No fork, push, or pull
    # request. Any future target can set this; the metadata fields still come
    # from that target's schema.
    metadata_only: bool = False
    # GitHub owner of the upstream repository. ``None`` means ``BASE_REPO_OWNER``.
    owner: str | None = None
    # The tool warns before any work and again before the push. It cannot check
    # authorization; an unauthorized pull request is closed without review.
    restricted: bool = False
    # Commit and push only ``<category>/<name>/metadata.json``, then open a PR.
    push_metadata_only: bool = False
    content_categories: tuple[ContentCategory, ...] = ()

    @property
    def repo_owner(self) -> str:
        return self.owner or BASE_REPO_OWNER

    @property
    def base_repo(self) -> str:
        return f'{self.repo_owner}/{self.repo_name}'

    @property
    def base_repo_url(self) -> str:
        return f'{HOST}/{self.base_repo}.git'

    @property
    def has_content_categories(self) -> bool:
        return bool(self.content_categories)

    def category_for_type(self, type_label: str) -> ContentCategory | None:
        """The content folder whose ``type`` matches a saved metadata file."""
        for category in self.content_categories:
            if category.type_label == type_label:
                return category
        return None

    def category(self, key: str) -> ContentCategory:
        for category in self.content_categories:
            if category.key == key:
                return category
        choices = ', '.join(item.key for item in self.content_categories)
        raise ValueError(
            f'Unknown content type {key!r} for --repo {self.key}. Choose from: {choices}',
        )

    def pr_title(self, project_name: str, category: ContentCategory | None = None) -> str:
        return self.pr_title_template.format(
            project_name=project_name,
            category=category.type_label if category else '',
        )

    def publication(
        self,
        project_name: str,
        category: ContentCategory | None = None,
    ) -> Publication:
        """Path, branch, and pull-request title for one project in this repository."""
        if category is not None:
            repo_subpath = f'{category.directory}/{project_name}'
            branch_name = f'{category.directory}-{project_name}'
        else:
            repo_subpath = project_name
            branch_name = project_name
        return Publication(
            repo_subpath=repo_subpath,
            branch_name=branch_name,
            pr_title=self.pr_title(project_name, category),
        )


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
        if cfg.metadata_only and cfg.push_metadata_only:
            raise ValueError(
                f'TARGET_REPOS[{key!r}] cannot set both metadata_only and push_metadata_only',
            )
        category_keys = [category.key for category in cfg.content_categories]
        if len(set(category_keys)) != len(category_keys):
            raise ValueError(f'TARGET_REPOS[{key!r}] has duplicate content category keys')
        schema_keys = [category.schema_key for category in cfg.content_categories]
        if len(set(schema_keys)) != len(schema_keys):
            raise ValueError(f'TARGET_REPOS[{key!r}] has duplicate content category schemas')
        type_labels = [category.type_label for category in cfg.content_categories]
        if len(set(type_labels)) != len(type_labels):
            raise ValueError(f'TARGET_REPOS[{key!r}] has duplicate content type labels')
        for category in cfg.content_categories:
            if '/' in category.directory or not category.directory:
                raise ValueError(
                    f'TARGET_REPOS[{key!r}] content category {category.key!r} must use a '
                    'single top-level directory name',
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
