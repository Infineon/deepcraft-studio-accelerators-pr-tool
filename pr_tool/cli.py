import shutil
import sys
from pathlib import Path
from subprocess import CompletedProcess, run, PIPE

from constants import *

# Define convenient functions to operate on the git tree
CliResult = CompletedProcess | str | int

TOOL_DIR = Path(__file__).resolve().parent
MINIMUM_UPDATABLE_GIT_VERSION = '2.16.2'  # update-git-for-windows option
MINIMUM_GIT_VERSION = '2.43'  # git show-ref --exists


def _resolve_gh_executable() -> tuple[str, str]:
    """Return ``(executable path, source label)`` for GitHub CLI.

    Prefers ``gh.exe`` / ``gh`` shipped next to this module, then ``gh`` on
  ``PATH``.
    """
    for name in ('gh.exe', 'gh'):
        bundled = TOOL_DIR / name
        if bundled.is_file():
            return str(bundled), 'bundled'
    on_path = shutil.which('gh')
    if on_path:
        return on_path, 'PATH'
    expected = TOOL_DIR / 'gh.exe'
    print(
        'Error: GitHub CLI (gh) not found.\n'
        f'  Expected bundled executable at: {expected}\n'
        '  Or install GitHub CLI and add it to your PATH:\n'
        '  https://cli.github.com/',
        file=sys.stderr,
    )
    sys.exit(1)


class Cli:
    def __init__(self):
        self.cwd = None
        self.git_dir = None
        self.gh_executable, self.gh_source = _resolve_gh_executable()

    def gh_version(self) -> str:
        """Return the ``gh --version`` string (first line), or ``unknown``."""
        try:
            result = run(
                [self.gh_executable, '--version'],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout.strip().splitlines()[0]
        except OSError:
            pass
        return 'unknown version'

    def run(self, args: list, *popenargs, cwd=None, check=True, stdout=None, **kwargs) -> CliResult:
        print(' '.join(args))
        result = run(args, *popenargs, cwd=cwd or self.cwd, check=check, stdout=stdout, **kwargs)
        if stdout == PIPE:
            output = result.stdout.decode().strip()
            if not output and not check:
                output = str(result.returncode)
            print('-> ' + output[:512])
            return output
        elif not check:
            print(f'-> {result.returncode}')
            return result.returncode
        else:
            return result

    def git(self, args: list, *popenargs, **kwargs) -> CliResult:
        return self.run(['git', f'--git-dir={self.git_dir}'] + args, *popenargs, **kwargs)

    def gh(self, args: list, *popenargs, **kwargs) -> CliResult:
        if args[0] == 'pr':
            # All PR commands interact with Infineon's repo (the fork's base repo)
            args.extend(['--repo', BASE_REPO])
        if '--jq' in args:
            # Commands with JQ are assumed to have a query that outputs a string value
            kwargs['stdout'] = PIPE
        return self.run([self.gh_executable] + args, *popenargs, **kwargs)

    def ensure_git_version(self) -> None:
        """Ensure that git version is enough."""
        version = self.git(['version'], stdout=PIPE).rpartition(' ')[2]
        version_msg = f'git version {MINIMUM_GIT_VERSION} or newer is required.'
        if version < MINIMUM_GIT_VERSION:
            # The message clarifies why update-git-for-windows is called
            print(version_msg)
        if version < MINIMUM_UPDATABLE_GIT_VERSION or (
                version < MINIMUM_GIT_VERSION and self.git(['update-git-for-windows'], check=False) == 1):
            raise Exception(version_msg)
