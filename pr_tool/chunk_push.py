"""Where each commit chunk is pushed, so an open pull request changes only once.

The accelerators PR build starts on every push to the branch of an open pull
request. A large submission is pushed in several chunks, and each chunk would
start its own build on a project that is not finished yet.

When a pull request is already open and there is more than one chunk, the
chunks go to a side branch instead. The pull request branch is pushed once,
after the last chunk, so the build runs on the finished submission. This module
only decides the ``git push`` arguments; the caller runs them.
"""

from __future__ import annotations

from dataclasses import dataclass

OPEN_PR_STATE = 'OPEN'
# Project branches are named after folders, so they never contain a slash. A side
# branch under this prefix cannot be the branch of another project, and the stale
# side branch deleted before a run can never be one either.
STAGING_PREFIX = 'pr-tool-chunks/'


def direct_push_args(*, force_with_lease: bool = False) -> list[str]:
    """Arguments that push the current commit to the branch of the same name."""
    args = ['push', '-u', 'origin', 'HEAD']
    if force_with_lease:
        args.insert(1, '--force-with-lease')
    return args


def staging_branch_name(branch_name: str) -> str:
    """Side branch that holds the chunks of ``branch_name`` until the last one."""
    return f'{STAGING_PREFIX}{branch_name}'


def should_stage_chunks(pr_state: str | None, push_count: int) -> bool:
    """True when chunks must stay off the branch of an open pull request.

    One push is already a single update. A branch without an open pull request
    starts no build, so its chunks can go straight to the branch.
    """
    return pr_state == OPEN_PR_STATE and push_count > 1


@dataclass(frozen=True)
class ChunkPushPlan:
    """How the chunks of one submission are pushed."""

    branch_name: str
    # ``None`` pushes every chunk straight to ``branch_name``.
    staging_branch: str | None = None
    # Set after the fork branch was reset, so the push replaces the old history.
    force_with_lease: bool = False

    @classmethod
    def create(
        cls,
        branch_name: str,
        pr_state: str | None,
        push_count: int,
        *,
        branch_was_reset: bool = False,
    ) -> 'ChunkPushPlan':
        if should_stage_chunks(pr_state, push_count):
            return cls(branch_name, staging_branch=staging_branch_name(branch_name))
        return cls(branch_name, force_with_lease=branch_was_reset)

    @property
    def staged(self) -> bool:
        return self.staging_branch is not None

    @property
    def chunk_push_args(self) -> list[str]:
        """Push for each chunk: the side branch when staged, else the branch itself."""
        if self.staging_branch is not None:
            return ['push', 'origin', f'HEAD:refs/heads/{self.staging_branch}']
        return direct_push_args(force_with_lease=self.force_with_lease)

    @property
    def final_push_args(self) -> list[str] | None:
        """The one push that updates the pull request branch, or ``None`` if not staged.

        Every object is already on the fork from the side branch, so this push
        sends no file data.
        """
        return direct_push_args() if self.staged else None

    @property
    def delete_staging_args(self) -> list[str] | None:
        """Push that removes the side branch, or ``None`` if not staged."""
        if self.staging_branch is None:
            return None
        return ['push', 'origin', '--delete', self.staging_branch]
