import json
import os
import shutil
import sys
import time
from pathlib import Path
from subprocess import PIPE
from tempfile import NamedTemporaryFile, TemporaryDirectory

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from cli import Cli
from constants import (
    GIT_DIR,
    HOST,
    ICON_ABORT,
    ICON_ERROR,
    ICON_INFO,
    ICON_PROGRESS,
    ICON_PULL_REQUEST,
    ICON_SUCCESS,
    ICON_WARNING,
    DEEPCRAFT,
    MAIN_BRANCH,
    TARGET_REPOS,
)
from input import Input, confirm
from metadata import confirm_metadata, finalize_metadata, format_metadata_json, get_metadata_schema
from submission_exclusions import (
    build_submission_exclude_pathspecs,
    filter_submission_paths,
)
from target_repo import validate_target_repos_registry
from utils import group_files
from validation import validate_loaded_metadata, validate_project_structure
from metadata.schemas import validate_metadata_schemas

def onerror(func, path, exc_info):
    import stat
    if not os.access(path, os.W_OK):
        os.chmod(path, stat.S_IWUSR)
        func(path)
    else:
        raise


def cleanup_git_scratch(git_dir: Path) -> None:
    """Remove separate-git-dir scratch and any now-empty parent folders up to .git_deepcraft."""
    if git_dir.exists():
        shutil.rmtree(git_dir, onerror=onerror)
    current = git_dir.parent
    while current.name != GIT_DIR:
        if not current.exists() or any(current.iterdir()):
            return
        current.rmdir()
        current = current.parent
    if current.exists() and not any(current.iterdir()):
        current.rmdir()


def fork(base_repo: str) -> None:
    gh(['repo', 'fork', base_repo, '--default-branch-only'])
    time.sleep(2)  # Wait for repo to be created


def _is_commit_sha(value: str) -> bool:
    return len(value) == 40 and all(c in '0123456789abcdef' for c in value.lower())


def ensure_fork_matches_upstream(user, target_repo) -> None:
    """`gh repo sync --force` can leave the fork ahead of upstream (stale merge commits).

    Compare the fork's and upstream's main SHA and force-reset the fork's ref via the
    GitHub API when they differ, so the project branch is created from a clean base.
    """
    upstream_sha = gh(['api', f'repos/{target_repo.base_repo}/commits/{MAIN_BRANCH}',
                       '--jq', '.sha'], check=False)
    fork_sha = gh(['api', f'repos/{user}/{target_repo.repo_name}/commits/{MAIN_BRANCH}',
                   '--jq', '.sha'], check=False)
    if not _is_commit_sha(upstream_sha) or not _is_commit_sha(fork_sha):
        return
    if upstream_sha == fork_sha:
        return
    cli.progress('Fork still ahead of upstream; resetting fork main to upstream...')
    gh(['api', '-X', 'PATCH',
        f'repos/{user}/{target_repo.repo_name}/git/refs/heads/{MAIN_BRANCH}',
        '-f', f'sha={upstream_sha}', '-F', 'force=true'], check=False)


def print_header(title: str, *, icon: str = '') -> None:
    sep = '=' * 60
    label = f'{icon} {title}' if icon else title
    print(f'\n{sep}')
    print(f'  {label}')
    print(sep)


# ── Tool start ────────────────────────────────────────────────
validate_target_repos_registry(TARGET_REPOS)
validate_metadata_schemas(set(TARGET_REPOS))

try:
    args = Input()
except ValueError as exc:
    print(f'{ICON_ERROR} Error: {exc}', file=sys.stderr)
    sys.exit(1)

print_header(f'{DEEPCRAFT} Pull Request Tool', icon=ICON_PULL_REQUEST)

try:
    target_repo = args.target_repo
    project_path = args.project_path
    branch_name = project_name = args.project_name
    metadata_path = project_path / 'metadata.json'

    # Initial summary
    print_header('Project Summary', icon=ICON_INFO)
    print(f'  Target        : {target_repo.label} ({args.repo_key})')
    print(f'  Repository    : {target_repo.base_repo}')
    print(f'  Project path  : {project_path}')
    print(f'  Project name  : {project_name}')
    print(f'  Branch        : {branch_name}')
    has_existing_metadata = metadata_path.exists()
    meta_status = (
        f'{ICON_SUCCESS} found' if has_existing_metadata
        else f'{ICON_INFO} not found — will be created'
    )
    print(f'  Project layout: {target_repo.project_layout}')
    print(f'  metadata.json : {meta_status}')
    readme_status = (
        f'{ICON_SUCCESS} found' if (project_path / 'README.md').is_file()
        else f'{ICON_WARNING} missing (required)'
    )
    print(f'  README.md     : {readme_status}')
    print()
    if not confirm('Proceed with this project and repository?'):
        print(f'{ICON_ABORT} Aborted by user.')
        sys.exit(0)
    print()

    if args.metadata:
        metadata = args.metadata
    elif metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f'Could not read existing {metadata_path}: {exc}') from exc
        metadata = validate_loaded_metadata(
            metadata,
            get_metadata_schema(args.repo_key),
            lambda current, field_keys: args.collect_metadata(
                use_cli_args=False,
                previous=current,
                only_fields=field_keys,
            ),
            project_name,
        )
    else:
        metadata = None

    # Metadata review / collection
    metadata_schema = get_metadata_schema(args.repo_key)
    print_header('Metadata Collection', icon=ICON_INFO)
    while metadata:
        metadata = finalize_metadata(metadata, metadata_schema)
        print('\nProject metadata.json overview:')
        print(format_metadata_json(metadata).rstrip('\n'))
        answer = confirm_metadata()
        if answer == 'yes':
            metadata_path.write_text(
                format_metadata_json(metadata),
                encoding='utf-8',
            )
            print(f'{ICON_SUCCESS} Saved metadata.json')
            break
        if answer == 'abort':
            print(f'{ICON_ABORT} Aborted by user.')
            sys.exit(0)
        print(f'{ICON_INFO} Restarting metadata collection... (press Enter to keep previous values)')
        args.metadata = args.collect_metadata(use_cli_args=False, previous=metadata)
        metadata = args.metadata
    validate_project_structure(project_name, project_path, target_repo)
except ValueError as exc:
    print(f'{ICON_ERROR} Error: {exc}', file=sys.stderr)
    sys.exit(1)

print_header('Forking & Syncing Repository', icon=ICON_PROGRESS)
print(f'  {ICON_INFO} Checking git version, authenticating, and preparing fork...')

# Setup git and gh cli
cli = Cli(verbose=args.verbose, base_repo=target_repo.base_repo)
gh_label = Path(cli.gh_executable).name if cli.gh_source == 'bundled' else cli.gh_executable
print(f'  GitHub CLI    : {gh_label} ({cli.gh_source}, {cli.gh_version()})')
if args.verbose:
    print(f'  {ICON_INFO} Verbose mode  : on (all git/gh commands will be printed)')
print()

cli.ensure_git_version()
git = cli.git
gh = cli.gh
gh(['config', 'set', 'prompt', 'disabled'])
cli.ensure_github_auth(required_scopes=('workflow',))
user = gh(['api', 'user', '--jq', '.login'])
email = gh(['api', 'user', '--jq', '.email'])

# Ensure fork exists and is in-sync with the source repo
cli.progress('Checking fork...')
if gh(['repo', 'view', f'{user}/{target_repo.repo_name}', '--json', 'name'], check=False) != 0:
    cli.progress('Creating fork...')
    fork(target_repo.base_repo)
elif gh(['repo', 'sync', f'{user}/{target_repo.repo_name}', '--force', '--branch', MAIN_BRANCH], check=False) != 0:
    print(f'{ICON_WARNING} Your fork is out of sync with the source repository. Authenticate again to allow deleting the forked repo, so a new one can be created.')
    cli.progress('Recreating fork...')
    gh(['auth', 'refresh', '--hostname', 'github.com', '-s', 'workflow,delete_repo'])
    gh(['repo', 'delete', f'{user}/{target_repo.repo_name}', '--yes'])
    fork(target_repo.base_repo)
else:
    ensure_fork_matches_upstream(user, target_repo)

cli.git_dir = git_dir = project_path.parent / GIT_DIR / target_repo.key / project_name
if git_dir.exists():
    shutil.rmtree(git_dir, onerror=onerror)
else:
    git_dir.parent.mkdir(parents=True, exist_ok=True)
try:  # Always remove git_dir after this block
    # Initialize local git
    cli.progress('Preparing local git workspace...')
    with TemporaryDirectory() as tmpdir:
        cli.cwd = tmpdir
        # Clone repo empty and shallow; --no-single-branch is required to allow this copy to fetch other branches later
        git(['clone', '--no-checkout', '--depth', '1', '--no-single-branch', f'--separate-git-dir={git_dir}',
             f'{HOST}/{user}/{target_repo.repo_name}.git', tmpdir])
        git(['remote', 'add', '-t', MAIN_BRANCH, 'upstream', target_repo.base_repo_url])
        git(['config', 'advice.updateSparsePath', 'false'])
        git(['config', 'core.safecrlf', 'false'])
        git(['config', 'user.email', email])
        git(['config', 'gc.auto', '0'])
        git(['config', 'maintenance.auto', 'false'])

        # Prevent git from processing tracked files that are outside the project
        git(['sparse-checkout', 'set', '--no-cone', '!/*', f'/{project_name}/'])

        # Switch to the project branch
        branch_ref = f'refs/heads/{branch_name}'
        branch_is_new = git(['ls-remote', '--exit-code', '--quiet', 'origin', branch_ref], check=False) == 2
        if branch_is_new:
            git(['switch', '-c', branch_name, MAIN_BRANCH])
        else:
            git(['switch', branch_name])
        commits_ahead = int(git(['rev-list', '--count', branch_ref, f'^refs/heads/{MAIN_BRANCH}'], stdout=PIPE))
        commit_verb = 'Add' if commits_ahead <= 0 else 'Modify'

    # Print execution summary
    print_header('Creating / Updating Pull Request', icon=ICON_PROGRESS)
    print(f'  GitHub user   : {user}')
    print(f'  Fork          : {user}/{target_repo.repo_name}')
    print(f'  Branch        : {branch_name} ({"new" if branch_is_new else "existing"})')
    print(f'  Mode          : {commit_verb} files')
    print()

    # Push project content to the user's remote (origin)
    cli.cwd = repo_root = project_path.parent
    cli.work_tree = repo_root
    try:
        # Handle deletions
        ignore_paths = [f':^{project_path.name}/{dir}' for dir in target_repo.git_ignored_dirs]
        ignore_paths.extend(build_submission_exclude_pathspecs(project_path))
        diff_names_deleted = filter_submission_paths(
            git(['diff', '--name-only', '--diff-filter=D', '--relative', '--', str(project_path), *ignore_paths], stdout=PIPE),
            project_path,
        )
        if diff_names_deleted:
            with NamedTemporaryFile('w', delete=False) as pathspec:
                pathspec.write(diff_names_deleted)
                pathspec.close()
                git(['rm', f'--pathspec-from-file={pathspec.name}'])
                os.remove(pathspec.name)
        # Divide push to groups, each with a size less than 2GB
        git(['add', '--intent-to-add', '--', project_path.name, *ignore_paths])
        diff_names = filter_submission_paths(
            git(['diff', '--name-only', '--relative', '--', str(project_path), *ignore_paths], stdout=PIPE),
            project_path,
        )
        gh_push_limit = (2 * 1024 * 1024 * 1024)  # 2 GB
        names = [name for name in diff_names.splitlines() if name.strip()]
        # GitHub caps the PR file list at 3,000 entries. Commit root-level project
        # files (README.md, metadata.json, *.improj, ...) first so they stay visible
        # to reviewers ahead of large Data/ directories that follow.
        root_files = [name for name in names if name.count('/') <= 1]
        data_files = [name for name in names if name.count('/') > 1]
        commit_batches: list[tuple[str, list[str]]] = []
        if root_files:
            commit_batches.append(('project files', root_files))
        if data_files:
            data_chunks = list(group_files(repo_root, '\n'.join(data_files), gh_push_limit - 1))
            if len(data_chunks) == 1:
                commit_batches.append(('data files', data_chunks[0]))
            else:
                total = len(data_chunks)
                for index, chunk in enumerate(data_chunks, start=1):
                    commit_batches.append((f'data chunk {index} of {total}', chunk))
        if commit_batches:
            count = len(commit_batches)
            cli.progress(f'Pushing changes ({count} commit{"s" if count != 1 else ""})...')
            for label, group in commit_batches:
                with NamedTemporaryFile('w', delete=False) as pathspec:
                    pathspec.write('\n'.join(group))
                    pathspec.close()
                    git(['add', f'--pathspec-from-file={pathspec.name}'])
                    os.remove(pathspec.name)
                git(['commit', '--no-verify', '-m', f'{commit_verb} {label}'])
                git(['push', '-u', 'origin', 'HEAD'])
        elif diff_names_deleted:
            cli.progress('Pushing deletions...')
            git(['commit', '-m', 'Delete files'])
            git(['push', '-u', 'origin', 'HEAD'])
        else:
            print('\n' + '=' * 60)
            print(f'  {ICON_INFO} No changes detected — nothing to push.')
            print('=' * 60 + '\n')

        # Create or reopen a pull request to Infineon and view it
        cli.progress('Opening pull request in browser...')
        head_branch = f'{user}:{branch_name}'
        pr_state = gh(['pr', 'view', head_branch, '--json', 'state', '--jq', '.state'], check=False)
        if pr_state in ('OPEN', 'MERGED'):
            gh(['pr', 'view', head_branch, '--web'], check=False)
        else:
            gh(['pr', 'create', '--base', MAIN_BRANCH, '--head', head_branch, '--web',
                '--title', target_repo.pr_title(project_name)])

        print_header('Pull Request Submitted Successfully', icon=ICON_SUCCESS)
        print('  Your project has been pushed and the pull request is')
        print('  open in your browser. Thank you for your submission!')
        print()
    except Exception as exc:
        print_header('Pull Request Failed', icon=ICON_ERROR)
        print(f'  {ICON_ERROR} Something went wrong while creating/updating the PR.')
        print(f'  {ICON_ERROR} Error: {exc}')
        print()
        print(f'  {ICON_INFO} Please check the output above for details and try')
        print('  again. Re-running the tool on the same project is')
        print('  safe — it will pick up where it left off.')
        print()
        sys.exit(1)
except KeyboardInterrupt:
    print_header('Process Aborted', icon=ICON_ABORT)
    print(f'  {ICON_ABORT} Interrupted by user (Ctrl+C).')
    print(f'  {ICON_INFO} Cleaning up temporary git state before exit...')
    print()
    sys.exit(130)
finally:
    cleanup_git_scratch(git_dir)
