from subprocess import CompletedProcess, run, PIPE

from constants import *

# Define convenient functions to operate on the git tree
CliResult = CompletedProcess | str | int

MINIMUM_UPDATABLE_GIT_VERSION = '2.16.2'  # update-git-for-windows option
MINIMUM_GIT_VERSION = '2.43'  # git show-ref --exists


class Cli:
    def __init__(self, project_name: str):
        self.cwd = None
        self.project_name = project_name

    def run(self, args: list, *popenargs, cwd=None, check=True, stdout=None, **kwargs) -> CliResult:
        print(' '.join(args))
        result = run(args, *popenargs, cwd=cwd or self.cwd, check=check, stdout=stdout, **kwargs)
        if stdout == PIPE:
            output = result.stdout.decode().strip()
            print('-> ' + output[:512])
            return output
        elif not check:
            print(f'-> {result.returncode}')
            return result.returncode
        else:
            return result

    def git(self, args: list, *popenargs, **kwargs) -> CliResult:
        return self.run(['git', f'--git-dir={GIT_DIR}\\{self.project_name}'] + args, *popenargs, **kwargs)


    def gh(self, args: list, *popenargs, **kwargs) -> CliResult:
        if args[0] == 'pr':
            # All PR commands interact with Infineon's repo (the fork's base repo)
            args.extend(['--repo', BASE_REPO])
        if '--jq' in args:
            # Commands with JQ are assumed to have a query that outputs a string value
            kwargs['stdout'] = PIPE
        return self.run(['gh'] + args, *popenargs, **kwargs)

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
