import json
import os
import shutil
import sys
import time
from subprocess import PIPE
from tempfile import NamedTemporaryFile, TemporaryDirectory

sys.path.append(os.getcwd())
from cli import Cli
from constants import *
from input import Input
from utils import group_files
from validation import validate_project_structure

def onerror(func, path, exc_info):
    import stat
    if not os.access(path, os.W_OK):
        os.chmod(path, stat.S_IWUSR)
        func(path)
    else:
        raise


def fork():
    gh(['repo', 'fork', BASE_REPO, '--default-branch-only'])
    time.sleep(2)  # Wait for repo to be created


args = Input()
project_path = args.project_path
branch_name = project_name = args.project_name
if args.metadata:
    (project_path / 'metadata.json').write_text(json.dumps(args.metadata))

validate_project_structure(project_name, project_path)

# Setup git and gh cli
cli = Cli()
cli.ensure_git_version()
git = cli.git
gh = cli.gh
gh(['config', 'set', 'prompt', 'disabled'])
auth_status = json.loads(gh(['auth', 'status', '--hostname', 'github.com', '--json', 'hosts', '--jq', '.hosts | add']))
if auth_status[0]['state'] != 'success' or 'workflow' not in auth_status[0]['scopes']:
    gh(['auth', 'login', '--hostname', 'github.com', '--web', '--git-protocol', 'https', '--scopes', 'workflow'])
user = gh(['api', 'user', '--jq', '.login'])
email = gh(['api', 'user', '--jq', '.email'])

# Ensure fork exists and is in sync with the source repo
if gh(['repo', 'view', f'{user}/{REPO_NAME}', '--json', 'isFork', '--jq', '.isFork']) == 'false':
    fork()
elif gh(['repo', 'sync', f'{user}/{REPO_NAME}', '--force', '--branch', MAIN_BRANCH], check=False) != 0:
    print('Your fork is out of sync with the source repository. Authenticate again to allow deleting the forked repo, so a new one can be created.')
    gh(['auth', 'refresh', '--hostname', 'github.com', '-s', 'workflow,delete_repo'])
    gh(['repo', 'delete', f'{user}/{REPO_NAME}', '--yes'])
    fork()

cli.git_dir = git_dir = project_path.parent / GIT_DIR / project_name
if git_dir.exists():
    shutil.rmtree(git_dir, onerror=onerror)
else:
    git_dir.parent.mkdir(exist_ok=True)
try:  # Always remove git_dir after this block
    # Initialize local git
    with TemporaryDirectory() as tmpdir:
        cli.cwd = tmpdir
        # Clone repo empty and shallow; --no-single-branch is required to allow this copy to fetch other branches later
        git(['clone', '--no-checkout', '--depth', '1', '--no-single-branch', f'--separate-git-dir={git_dir}',
             f'{HOST}/{user}/{REPO_NAME}.git', tmpdir])
        git(['remote', 'add', '-t', MAIN_BRANCH, 'upstream', BASE_REPO_URL])
        git(['config', 'advice.updateSparsePath', 'false'])
        git(['config', 'core.safecrlf', 'false'])
        git(['config', 'user.email', email])
        git(['config', 'gc.auto', '0'])
        git(['config', 'maintenance.auto', 'false'])

        # Prevent git from processing tracked files that are outside the project
        git(['sparse-checkout', 'set', '--no-cone', '!/*', f'/{project_name}/'])

        # Switch to the project branch
        branch_ref = f'refs/heads/{branch_name}'
        if git(['ls-remote', '--exit-code', '--quiet', 'origin', branch_ref], check=False) == 2:
            # Remote branch does not exist
            git(['switch', '-c', branch_name, MAIN_BRANCH])
        else:
            # Remote branch exists
            git(['switch', branch_name])
        commits_ahead = int(git(['rev-list', '--count', branch_ref, f'^refs/heads/{MAIN_BRANCH}'], stdout=PIPE))
        commit_verb = 'Add' if commits_ahead <= 0 else 'Modify'

    # Push project content to the user's remote (origin)
    cli.cwd = repo_root = project_path.parent
    # Handle deletions
    ignore_paths = [f':^{project_path / dir}' for dir in GIT_IGNORED_DIRS]
    diff_names_deleted = git(['diff', '--name-only', '--diff-filter=D', '--relative', '--', str(project_path), *ignore_paths], stdout=PIPE)
    if diff_names_deleted:
        with NamedTemporaryFile('w', delete=False) as pathspec:
            pathspec.write(diff_names_deleted)
            pathspec.close()
            git(['rm', f'--pathspec-from-file={pathspec.name}'])
            os.remove(pathspec.name)
    # Divide push to groups, each with a size less than 2GB
    git(['add', '--intent-to-add', '--', project_name, *ignore_paths])
    diff_names = git(['diff', '--name-only', '--relative', '--', str(project_path), *ignore_paths], stdout=PIPE)
    gh_push_limit = (2 * 1024 * 1024 * 1024)  # 2 GB
    file_groups = list(group_files(repo_root, diff_names, gh_push_limit - 1)) if diff_names else []
    if file_groups:
        number_of_chunks = len(file_groups)
        for index, group in enumerate(file_groups):
            with NamedTemporaryFile('w', delete=False) as pathspec:
                pathspec.write('\n'.join(group))
                pathspec.close()
                git(['add', f'--pathspec-from-file={pathspec.name}'])
                os.remove(pathspec.name)
            if index == 0 == number_of_chunks - 1:
                commit_msg = commit_verb + ' files'
            else:
                commit_msg = commit_verb + f' chunk {index + 1} of {number_of_chunks}'
            git(['commit', '--no-verify', '-m', commit_msg])
            git(['push', '-u', 'origin', 'HEAD'])
    elif diff_names_deleted:
        git(['commit', '-m', 'Delete files'])
        git(['push', '-u', 'origin', 'HEAD'])

    # Create or reopen a pull request to Infineon and view it
    head_branch = f'{user}:{branch_name}'
    pr_state = gh(['pr', 'view', head_branch, '--json', 'state', '--jq', '.state'], check=False)
    if not pr_state or pr_state == 'CLOSED':
        gh(['pr', 'create', '--base', 'main', '--head', head_branch, '--web', '--title', f'Accelerator {project_name}'])
    else:
        gh(['pr', 'view', head_branch, '--web'], check=False)
finally:
    # Clean up local git
    shutil.rmtree(git_dir, onerror=onerror)
    if not any(git_dir.parent.iterdir()):
        git_dir.parent.rmdir()
