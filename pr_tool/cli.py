import json
import shutil
import sys
from pathlib import Path
from subprocess import CalledProcessError, CompletedProcess, run, PIPE

from constants import (
    ICON_ERROR,
    ICON_INFO,
    ICON_PROGRESS,
    MINIMUM_GIT_VERSION,
    MINIMUM_UPDATABLE_GIT_VERSION,
)

# Define convenient functions to operate on the git tree
CliResult = CompletedProcess | str | int

TOOL_DIR = Path(__file__).resolve().parent


def _resolve_gh_executable() -> tuple[str, str]:
    """Return ``(executable path, source label)`` for GitHub CLI.

    Prefers ``gh.exe`` / ``gh`` shipped next to this module, then ``gh`` on ``PATH``.
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
        f'{ICON_ERROR} Error: GitHub CLI (gh) not found.\n'
        f'  Expected bundled executable at: {expected}\n'
        '  Quick fix:\n'
        '  1) Install GitHub CLI: https://cli.github.com/\n'
        '  2) Add the install folder (not gh.exe) to PATH\n'
        '  3) Restart your terminal/shell and run again',
        file=sys.stderr,
    )
    sys.exit(1)


class Cli:
    def __init__(self, *, verbose: bool = False, base_repo: str):
        self.cwd = None
        self.git_dir = None
        self.verbose = verbose
        self.base_repo = base_repo
        self.gh_executable, self.gh_source = _resolve_gh_executable()

    def progress(self, message: str) -> None:
        """Print a short status line (always shown in quiet mode)."""
        if not self.verbose:
            print(f'  {ICON_PROGRESS} {message}')

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
        cmd = ' '.join(args)
        if self.verbose:
            print(cmd)
        try:
            result = run(args, *popenargs, cwd=cwd or self.cwd, check=check, stdout=stdout, **kwargs)
        except CalledProcessError:
            print(f'{ICON_ERROR} Command failed: {cmd}', file=sys.stderr)
            raise
        if stdout == PIPE:
            output = result.stdout.decode().strip()
            if not output and not check:
                output = str(result.returncode)
            if self.verbose:
                print('-> ' + output[:512])
            return output
        if not check and self.verbose:
            print(f'-> {result.returncode}')
        return result.returncode if not check else result

    def git(self, args: list, *popenargs, **kwargs) -> CliResult:
        return self.run(['git', f'--git-dir={self.git_dir}'] + args, *popenargs, **kwargs)

    def gh(self, args: list, *popenargs, **kwargs) -> CliResult:
        if args[0] == 'pr':
            # All PR commands interact with Infineon's repo (the fork's base repo)
            args.extend(['--repo', self.base_repo])
        if '--jq' in args:
            # Commands with JQ are assumed to have a query that outputs a string value
            kwargs['stdout'] = PIPE
        return self.run([self.gh_executable] + args, *popenargs, **kwargs)

    def _parse_github_scopes(self, scopes: object) -> set[str]:
        if isinstance(scopes, str):
            return {part.strip() for part in scopes.split(',') if part.strip()}
        if isinstance(scopes, list):
            return {str(scope).strip() for scope in scopes if str(scope).strip()}
        return set()

    def _active_github_host(self) -> dict | None:
        output = self.run(
            [self.gh_executable, 'auth', 'status', '--hostname', 'github.com', '--json', 'hosts'],
            stdout=PIPE,
            check=True,
        )
        hosts = json.loads(output)['hosts']['github.com']
        if not isinstance(hosts, list):
            hosts = [hosts]
        return next((host for host in hosts if host.get('active')), hosts[0] if hosts else None)

    def ensure_github_auth(self, *, required_scopes: tuple[str, ...] = ('workflow',)) -> None:
        """Ensure GitHub CLI is logged in with the scopes this tool needs."""
        host = self._active_github_host()
        if host is None or host.get('state') != 'success':
            login = host.get('login') if host else None
            detail = host.get('error') if host else None
            print(
                f'{ICON_ERROR} GitHub CLI is not authenticated for github.com'
                + (f' (account: {login})' if login else '')
                + '.',
                file=sys.stderr,
            )
            if detail:
                print(f'  {ICON_INFO} {detail}', file=sys.stderr)
            print(
                f'  {ICON_INFO} Complete login in the browser when prompted '
                f'(this tool uses: {self.gh_executable}).',
                file=sys.stderr,
            )
            self.gh(['auth', 'login', '--hostname', 'github.com', '--web',
                     '--git-protocol', 'https', '--scopes', ','.join(required_scopes)])
            return

        granted = self._parse_github_scopes(host.get('scopes'))
        missing = [scope for scope in required_scopes if scope not in granted]
        if missing:
            self.progress(
                f'Adding missing GitHub token scope(s): {", ".join(missing)}',
            )
            self.gh(['auth', 'refresh', '--hostname', 'github.com',
                     '-s', ','.join(missing)])

    def ensure_git_version(self) -> None:
        """Ensure that git version is enough."""
        version = self.git(['version'], stdout=PIPE).rpartition(' ')[2]
        version_msg = f'git version {MINIMUM_GIT_VERSION} or newer is required.'
        if version < MINIMUM_GIT_VERSION:
            # The message clarifies why update-git-for-windows is called
            print(f'{ICON_ERROR} {version_msg}')
        if version < MINIMUM_UPDATABLE_GIT_VERSION or (
                version < MINIMUM_GIT_VERSION and self.git(['update-git-for-windows'], check=False) == 1):
            raise Exception(f'{ICON_ERROR} {version_msg}')
