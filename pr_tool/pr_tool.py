import json
import os
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

args = Input()
project_path = args.project_path
branch_name = project_name = args.project_name
if args.metadata:
    (project_path / 'metadata.json').write_text(json.dumps(args.metadata))

validate_project_structure(project_name, project_path)

# Setup git and gh cli
cli = Cli(project_name)
cli.ensure_git_version()
git = cli.git
gh = cli.gh
gh(['config', 'set', 'prompt', 'disabled'])
gh(['auth', 'login', '--hostname', 'github.com', '--web', '--git-protocol', 'https', '--scopes', 'workflow'])
user = gh(['api', 'user', '--jq', '.login'])
email = gh(['api', 'user', '--jq', '.email'])

# Ensure repo is cloned
cli.cwd = git_path = project_path.parent
git_dir = git_path / GIT_DIR / project_name
origin_url = f'{HOST}/{user}/{REPO_NAME}.git'
if git(['remote', 'get-url', 'origin'], check=False, stdout=PIPE) != origin_url:
    gh(['repo', 'fork', BASE_REPO, '--default-branch-only'])
    time.sleep(2)  # Wait for repo to be created
    git_dir.parent.mkdir(exist_ok=True)
    with TemporaryDirectory() as tmpdir:
        # Clone repo empty
        git(['clone', '--no-checkout', '--filter=blob:none', '--depth', '1', '--no-single-branch', '--sparse',
             f'--separate-git-dir={git_dir}', origin_url, tmpdir])
    git(['remote', 'add', '-t', MAIN_BRANCH, 'upstream', BASE_REPO_URL])
    git(['config', 'advice.updateSparsePath', 'false'])
    git(['config', 'core.safecrlf', 'false'])
    git(['config', 'user.email', email])
gh(['repo', 'sync', f'{user}/{REPO_NAME}', '--force', '--branch', MAIN_BRANCH])
# Ignore everything (including files in root) but the project
git(['sparse-checkout', 'set', '--no-cone', '!/*', f'/{project_name}/'])
git(['gc'])

branch_ref = f'refs/heads/{branch_name}'
if git(['ls-remote', '--exit-code', '--quiet', 'origin', branch_ref], check=False) == 2:
    # Remote branch does not exist
    if git(['show-ref', '--verify', '--quiet', branch_ref], check=False) == 0:
        # Local branch exists
        git(['switch', branch_name])
    else:
        # Local branch also does not exist
        git(['switch', '-c', branch_name, MAIN_BRANCH])
else:
    # Remote branch exists
    git(['switch', branch_name])
    pull_required = int(git(['rev-list', '--count', f'origin/{branch_name}', f'^refs/heads/{branch_name}'], stdout=PIPE)) > 0
    if pull_required:
        stash_name = f'Update {branch_name}'
        git(['stash', 'push', '--message', stash_name, '--', f'{project_name}/'])
        git(['pull', 'origin', branch_name])
        git(['stash', 'apply', f'stash^{{/{stash_name}}}'], check=False)
commits_ahead = int(git(['rev-list', '--count', branch_ref, f'^refs/heads/{MAIN_BRANCH}'], stdout=PIPE))
commit_verb = 'Add' if commits_ahead <= 0 else 'Modify'

# Push project content to the user's remote (origin)

# Handle deletions
diff_names_deleted = git(['diff', '--name-only', '--diff-filter=D', '--relative', str(project_path)], stdout=PIPE)
if diff_names_deleted:
    with NamedTemporaryFile('w', delete=False) as pathspec:
        pathspec.write(diff_names_deleted)
        pathspec.close()
        git(['rm', f'--pathspec-from-file={pathspec.name}'])
        os.remove(pathspec.name)
# Divide push to groups, each with a size less than 2GB
git(['add', '--intent-to-add', project_name])
diff_names = git(['diff', '--name-only', '--relative', str(project_path)], stdout=PIPE)
gh_push_limit = (2 * 1024 * 1024 * 1024)  # 2 GB
file_groups = list(group_files(git_path, diff_names, gh_push_limit - 1)) if diff_names else []
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
    git(['commit', '-m', commit_msg])
    git(['push', '-u', 'origin', 'HEAD'])
else:
    if diff_names_deleted:
        git(['commit', '-m', commit_verb + ' files'])
        git(['push', '-u', 'origin', 'HEAD'])

# Create or reopen a pull request to Infineon and view it
head_branch = f'{user}:{branch_name}'
pr_state = gh(['pr', 'view', head_branch, '--json', 'state', '--jq', '.state'], check=False)
if not pr_state or pr_state == 'CLOSED':
    gh(['pr', 'create', '--base', 'main', '--head', head_branch, '--web', '--title', f'Starter Model {project_name}'])
else:
    gh(['pr', 'view', head_branch, '--web'], check=False)
