from pathlib import Path

from project_layouts import get_project_layout
from target_repo import TargetRepo


def validate_project_structure(
    project_name: str, project_path: Path, target_repo: TargetRepo,
) -> None:
    """Validate the project folder before publishing."""
    get_project_layout(target_repo.project_layout).validate(project_name, project_path)
