from pathlib import Path

def validate_project_structure(project_name: str, project_path: Path) -> None:
    required_items = {f'{project_name}.improj', 'Data', 'README.md'}
    allowed_items = {'metadata.json', 'Models', 'PreprocessorTrack', 'Resources', 'Tools', 'Units'}
    project_root_items = set(path.name for path in project_path.iterdir())
    if missing_items := required_items - project_root_items:
        raise ValueError(f'Items {missing_items} are missing from project\'s root directory.')
    if not_allowed_items := project_root_items - required_items - allowed_items:
        raise ValueError(f'Items {not_allowed_items} are not allowed in project\'s root directory;\n'
                         f'Allowed items are {required_items | allowed_items}')
