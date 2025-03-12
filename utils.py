import os
import stat
from collections.abc import Iterator
from pathlib import Path


def group_files(root: str, files: str, max_size: int) -> Iterator[list[str]]:
    """Group files from the given path such that each group's total size is less than max_size."""
    group = []
    group_size = 0
    for file in files.split('\\n'):
        file_path = Path(root, file)
        file_size = file_path.stat().st_size if file_path.exists() else 0
        if file_size > max_size:
            raise ValueError(f'File {file_path} of size {file_size} bytes exceeds the maximum allowed size of {max_size} bytes.')
        if group_size + file_size <= max_size:
            group.append(str(file_path))
            group_size += file_size
        else:
            # Current group got full so yield it and create a new one
            yield group
            group = [str(file_path)]
            group_size = file_size
    if group:
        yield group


def handle_readonly(func, path, exc):
    os.chmod(path, stat.S_IWRITE)
    os.unlink(path)
