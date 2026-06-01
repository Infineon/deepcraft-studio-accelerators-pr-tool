"""Paths excluded from PR submission (git/Python repo artefacts)."""

from __future__ import annotations

import fnmatch
import os
from functools import lru_cache
from pathlib import Path

# Git / Python artefacts: ignored at project root for layout validation, never pushed.
EXCLUDED_NAMES: frozenset[str] = frozenset({
    '.git',
    '.gitignore',
    '.gitattributes',
    '__pycache__',
    '.venv',
    'venv',
    '.env',
    '.pytest_cache',
    '.mypy_cache',
    '.ruff_cache',
    '.tox',
    '.eggs',
})

EXCLUDED_FILE_GLOBS: tuple[str, ...] = (
    '*.pyc',
    '*.pyo',
    '*.pyd',
    '.DS_Store',
    'Thumbs.db',
)


@lru_cache(maxsize=8)
def python_env_dirs(project_path: str) -> frozenset[str]:
    """Project-relative paths of venv (``pyvenv.cfg``) or conda (``conda-meta/``) roots."""
    root = Path(project_path)
    found: set[str] = set()
    for dirpath, dirnames, _ in os.walk(root, topdown=True):
        current = Path(dirpath)
        if (current / 'pyvenv.cfg').is_file() or (current / 'conda-meta').is_dir():
            rel = current.relative_to(root).as_posix()
            if rel != '.':
                found.add(rel)
            dirnames.clear()
        else:
            dirnames[:] = [name for name in dirnames if name not in EXCLUDED_NAMES]
    return frozenset(found)


def is_submission_excluded(path: str, env_dirs: frozenset[str] = frozenset()) -> bool:
    """True if a path or root item must not be submitted."""
    normalized = path.replace('\\', '/').strip()
    if not normalized:
        return False
    for part in normalized.split('/'):
        if part in EXCLUDED_NAMES:
            return True
        if any(fnmatch.fnmatch(part, pattern) for pattern in EXCLUDED_FILE_GLOBS):
            return True
    return any(normalized == env_dir or normalized.startswith(f'{env_dir}/') for env_dir in env_dirs)


def is_excluded_project_root_entry(project_path: Path, name: str) -> bool:
    """True if a project-root name is a git/Python artefact (by name or env markers)."""
    env_dirs = python_env_dirs(str(project_path.resolve()))
    return is_submission_excluded(name, env_dirs) or name in env_dirs


def filter_submission_paths(names: str, project_path: Path) -> str:
    """Drop excluded paths from a newline-separated git path list."""
    env_dirs = python_env_dirs(str(project_path.resolve()))
    return '\n'.join(
        line for line in names.splitlines()
        if line.strip() and not is_submission_excluded(line, env_dirs)
    )


def build_submission_exclude_pathspecs(project_path: Path) -> list[str]:
    """Git ``:^`` pathspecs excluding artefacts under the project folder."""
    prefix = project_path.name
    env_dirs = python_env_dirs(str(project_path.resolve()))
    specs = [
        spec
        for name in sorted(EXCLUDED_NAMES)
        for spec in (f':^{prefix}/{name}', f':^{prefix}/**/{name}')
    ]
    specs += [
        spec
        for env_dir in sorted(env_dirs)
        for spec in (f':^{prefix}/{env_dir}', f':^{prefix}/{env_dir}/**')
    ]
    return specs
