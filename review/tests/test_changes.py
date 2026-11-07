import subprocess
from pathlib import Path

import pytest

from review.changes import collect_changes, default_base


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=repo, check=True, capture_output=True
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / ".gitignore").write_text("ignored.py\n")
    (tmp_path / "kept.py").write_text("x = 1\n")
    (tmp_path / "deleted.py").write_text("y = 1\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-q", "-m", "base")
    git(tmp_path, "checkout", "-q", "-b", "feature")
    return tmp_path


def test_changes_cover_the_branch_commits_the_working_tree_and_new_files(repo: Path) -> None:
    (repo / "committed.py").write_text("a = 1\n")
    git(repo, "add", "committed.py")
    git(repo, "commit", "-q", "-m", "Add committed")
    (repo / "kept.py").write_text("x = 2\n")  # changed, not committed
    (repo / "new.py").write_text("n = 1\n")  # untracked
    (repo / "ignored.py").write_text("i = 1\n")  # git-ignored
    (repo / "notes.md").write_text("doc\n")
    (repo / "deleted.py").unlink()

    changes = collect_changes(repo, "main")

    assert changes.python_files == ("committed.py", "kept.py", "new.py")
    assert changes.other_files == ("notes.md",)
    assert changes.uncommitted == {"kept.py", "new.py", "notes.md", "deleted.py"}
    assert "+a = 1" in changes.diff and "+x = 2" in changes.diff and "+n = 1" in changes.diff
    assert "Add committed" in changes.commits
    assert changes.label("new.py") == "new.py (not committed)"
    assert changes.label("committed.py") == "committed.py"


def test_nothing_changed_on_the_base_branch_itself(repo: Path) -> None:
    git(repo, "checkout", "-q", "main")
    changes = collect_changes(repo, "main")
    assert (changes.python_files, changes.diff, changes.commits) == ((), "", "")


def test_base_defaults_to_main_without_a_remote(repo: Path) -> None:
    assert default_base(repo) == "main"
