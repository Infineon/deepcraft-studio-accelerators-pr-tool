"""Self-update: fetch the latest tool revision from GitHub ``main`` and re-exec.

The "version" is simply the latest commit SHA on ``main`` (read via the public
GitHub API), compared against a local ``.tool_revision`` marker written after each
update. This needs no manual version bumps and no CI: any merge to ``main`` ships.

Uses only the standard library so the check runs before ``gh`` auth. Any
network/extract failure is non-fatal: the tool prints a manual-download notice
and continues with the current copy.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

from constants import ICON_INFO, ICON_SUCCESS, ICON_WARNING, TOOL_REPO

TOOL_DIR = Path(__file__).resolve().parent
REVISION_FILE = TOOL_DIR / '.tool_revision'

_COMMIT_API_URL = f'https://api.github.com/repos/{TOOL_REPO}/commits/main'
_TARBALL_URL = f'https://codeload.github.com/{TOOL_REPO}/tar.gz/refs/heads/main'
_RELEASES_URL = f'https://github.com/{TOOL_REPO}'
_UPDATED_ENV = 'PRTOOL_SELF_UPDATED'
_TIMEOUT_SECONDS = 10
_ARCHIVE_SUBDIR = 'pr_tool/'


def _running_from_git_checkout() -> bool:
    """True if the tool lives inside a git working copy (clone users update via git)."""
    for directory in (TOOL_DIR, *TOOL_DIR.parents):
        if (directory / '.git').exists():
            return True
    return False


def _read_local_revision() -> str:
    try:
        return REVISION_FILE.read_text(encoding='utf-8').strip()
    except OSError:
        return ''


def _write_local_revision(revision: str) -> None:
    try:
        REVISION_FILE.write_text(revision + '\n', encoding='utf-8')
    except OSError:
        pass


def _open(url: str, *, accept: str | None = None):
    headers = {'User-Agent': 'deepcraft-pr-tool'}
    if accept:
        headers['Accept'] = accept
    request = urllib.request.Request(url, headers=headers)
    return urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS)


def _fetch_remote_revision() -> str:
    with _open(_COMMIT_API_URL, accept='application/vnd.github+json') as response:
        payload = json.loads(response.read().decode('utf-8'))
    sha = payload.get('sha')
    return sha if isinstance(sha, str) else ''


def _download(url: str, dest: Path) -> None:
    with _open(url) as response, open(dest, 'wb') as out:
        shutil.copyfileobj(response, out)


def _extract_tool_files(tar_path: Path, staging: Path) -> bool:
    """Extract only the ``pr_tool/`` subtree of the archive into *staging*."""
    with tarfile.open(tar_path, 'r:gz') as tar:
        members = tar.getmembers()
        if not members:
            return False
        top = members[0].name.split('/')[0]
        prefix = f'{top}/{_ARCHIVE_SUBDIR}'
        extracted = False
        for member in members:
            if not member.isfile() or not member.name.startswith(prefix):
                continue
            rel = member.name[len(prefix):]
            target = (staging / rel).resolve()
            if not str(target).startswith(str(staging.resolve())):
                continue  # guard against path traversal
            target.parent.mkdir(parents=True, exist_ok=True)
            source = tar.extractfile(member)
            if source is None:
                continue
            with source, open(target, 'wb') as out:
                shutil.copyfileobj(source, out)
            extracted = True
        return extracted


def _apply_update() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        tar_path = tmp_path / 'tool.tar.gz'
        _download(_TARBALL_URL, tar_path)
        staging = tmp_path / 'staged'
        staging.mkdir()
        if not _extract_tool_files(tar_path, staging):
            raise RuntimeError('pr_tool/ folder not found in downloaded archive')
        for source in staging.rglob('*'):
            if source.is_file():
                dest = TOOL_DIR / source.relative_to(staging)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dest)


def _reexec() -> None:
    os.environ[_UPDATED_ENV] = '1'
    script = str(Path(sys.argv[0]).resolve())
    result = subprocess.run([sys.executable, script, *sys.argv[1:]], env=os.environ)
    sys.exit(result.returncode)


def ensure_latest_version(*, enabled: bool = True) -> None:
    """Update the tool to the latest ``main`` revision and re-exec, if it changed."""
    if not enabled or os.environ.get(_UPDATED_ENV):
        return
    if _running_from_git_checkout():
        return  # never overwrite a git working copy; use ``git pull`` there instead
    try:
        remote = _fetch_remote_revision()
    except Exception:
        return  # offline or unreachable: skip silently, run current copy
    if not remote:
        return
    local = _read_local_revision()
    if local == remote:
        return
    if local:
        print(f'{ICON_INFO} A newer version of the PR tool is available '
              f'({local[:7]} \u2192 {remote[:7]}). Updating...')
    else:
        print(f'{ICON_INFO} Ensuring you have the latest version of the PR tool...')
    try:
        _apply_update()
    except Exception as exc:
        print(f'{ICON_WARNING} Automatic update failed ({exc}).')
        print(f'  {ICON_INFO} Download the latest version manually: {_RELEASES_URL}')
        return
    _write_local_revision(remote)
    print(f'{ICON_SUCCESS} Updated to the latest version ({remote[:7]}). Restarting...\n')
    _reexec()
