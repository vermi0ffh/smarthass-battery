"""What the review looks at: the branch's changes against its base, committed or not."""

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ChangeSet:
    base: str
    merge_base: str
    python_files: tuple[str, ...]
    other_files: tuple[str, ...]  # listed to the agents (documentation updated…), content not in the diff
    uncommitted: frozenset[str]
    diff: str
    commits: str  # messages and stats of the branch's commits

    def label(self, path: str) -> str:
        return path + (" (not committed)" if path in self.uncommitted else "")


def _git(root: Path, *args: str, ok_codes: tuple[int, ...] = (0,)) -> str:
    # quotePath off: a non-ASCII path is printed as is, not quoted (which would hide its .py suffix)
    command = ["git", "-c", "core.quotePath=false", *args]
    result = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)
    if result.returncode not in ok_codes:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def default_base(root: Path) -> str:
    """`origin/main` when the remote branch is known, so unpushed commits are reviewed; otherwise `main`."""
    known = _git(root, "rev-parse", "--verify", "--quiet", "origin/main", ok_codes=(0, 1)).strip()
    return "origin/main" if known else "main"


def collect_changes(root: Path, base: str) -> ChangeSet:
    """Files changed since the merge base with `base`: the branch's commits, the working tree and new files."""
    merge_base = _git(root, "merge-base", base, "HEAD").strip()
    # Merge base against the working tree: committed and uncommitted changes, deleted files left out
    tracked = _lines(_git(root, "diff", "--name-only", "--diff-filter=ACMR", merge_base))
    untracked = _lines(_git(root, "ls-files", "--others", "--exclude-standard"))
    uncommitted = set(_lines(_git(root, "diff", "--name-only", "HEAD"))) | set(untracked)
    changed = sorted(set(tracked) | set(untracked))
    python_files = [path for path in changed if path.endswith(".py")]
    other_files = [path for path in changed if not path.endswith(".py")]

    diff_parts = []
    tracked_python = [path for path in python_files if path in tracked]
    if tracked_python:
        diff_parts.append(_git(root, "diff", merge_base, "--", *tracked_python))
    for path in python_files:
        if path not in tracked:
            # --no-index exits with 1 when the files differ, which they always do here
            diff_parts.append(_git(root, "diff", "--no-index", "--", "/dev/null", path, ok_codes=(0, 1)))

    commits = _git(root, "log", "--stat", "--format=%n%h %s%n%n%b", f"{merge_base}..HEAD")
    return ChangeSet(
        base=base,
        merge_base=merge_base,
        python_files=tuple(python_files),
        other_files=tuple(other_files),
        uncommitted=frozenset(uncommitted),
        diff="".join(diff_parts),
        commits=commits.strip(),
    )


def _lines(output: str) -> list[str]:
    return [line for line in output.splitlines() if line]
