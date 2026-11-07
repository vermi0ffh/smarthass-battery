import json
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from review.cli import main
from review.report import EXIT_BLOCKING, EXIT_OK, EXIT_UNRELIABLE

# As many rules as the real AGENTS.md, which the axes cite
AGENTS_MD = "# AGENTS.md\n\n## Rules\n\n" + "".join(f"{n}. **Rule {n}**: text.\n" for n in range(1, 28))
BLOCKING = {"severity": "blocking", "file": "app.py", "line": 1, "rule": "rule-8", "summary": "French", "detail": "d"}
# Fails the naming axis, answers one blocking finding on the others
CLAUDE = f"""grep -q "Your axis: naming" "$(dirname "$0")/../stdin" && exit 1
echo '{json.dumps({"is_error": False, "structured_output": {"findings": [BLOCKING]}, "total_cost_usd": 0.5})}'"""


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=repo, check=True, capture_output=True
    )


@pytest.fixture
def repo(tmp_path: Path, fake_cli: Callable[[str, str], None]) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "AGENTS.md").write_text(AGENTS_MD, encoding="utf-8")
    (root / ".gitignore").write_text("bin/\nreview/results/\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "base")
    (root / "app.py").write_text("x = 1  # bonjour\n", encoding="utf-8")
    fake_cli("claude", CLAUDE)
    return root


def review(root: Path, *args: str) -> int:
    # One agent at a time: the fake CLI records its stdin in a single file
    return main(["--engine", "claude", "--base", "main", "--jobs", "1", *args], root=root)


def report(root: Path) -> dict:
    return json.loads((root / "review" / "results" / "report.json").read_text(encoding="utf-8"))


def test_a_failed_axis_gives_partial_coverage_and_the_others_findings_still_block(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert review(repo, "--axes", "readability,naming") == EXIT_BLOCKING
    result = report(repo)
    assert [f["axis"] for f in result["findings"]] == ["readability"]
    assert [a["axis"] for a in result["agents_failed"]] == ["naming"]
    assert result["cost_usd"] == 0.5
    assert "Partial coverage: 1 agent(s) of 2 failed." in capsys.readouterr().out
    assert (repo / "review" / "results" / "naming.prompt.md").exists()


def test_no_agent_result_makes_the_review_unreliable(repo: Path) -> None:
    assert review(repo, "--axes", "naming") == EXIT_UNRELIABLE


def test_a_derogation_dismisses_the_finding_and_the_run_passes(repo: Path) -> None:
    (repo / "review").mkdir()
    (repo / "review" / "derogations.yaml").write_text(
        "derogations:\n  - rule: rule-8\n    paths: ['*.py']\n    reason: test\n", encoding="utf-8"
    )
    assert review(repo, "--axes", "readability") == EXIT_OK
    assert (len(report(repo)["findings"]), len(report(repo)["dismissed"])) == (0, 1)


def test_security_findings_are_never_dismissed(repo: Path) -> None:
    (repo / "review").mkdir()
    (repo / "review" / "derogations.yaml").write_text(
        "derogations:\n  - rule: rule-8\n    reason: test\n", encoding="utf-8"
    )
    assert review(repo, "--axes", "security") == EXIT_BLOCKING


def test_unreadable_derogations_are_not_applied_and_do_not_block(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (repo / "review").mkdir()
    (repo / "review" / "derogations.yaml").write_text("derogations: [", encoding="utf-8")
    assert review(repo, "--axes", "readability") == EXIT_OK
    assert report(repo)["derogations_applied"] is False
    assert "derogations NOT applied" in capsys.readouterr().out


def test_baseline_is_saved_then_compared(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    review(repo, "--axes", "readability", "--baseline")
    assert (repo / "review" / "results" / "baseline-claude.json").exists()
    capsys.readouterr()
    review(repo, "--axes", "readability")
    assert "Against the baseline: 0 new · 1 already seen · 0 gone" in capsys.readouterr().out


def test_no_python_change_means_nothing_to_review(repo: Path) -> None:
    (repo / "app.py").unlink()
    assert review(repo, "--axes", "readability") == EXIT_OK
    assert not (repo / "review" / "results").exists()


@pytest.mark.parametrize("args", [["--base", "no-such-branch"], ["--axes", "no-such-axis"], ["--engine", "gemini"]])
def test_a_review_that_cannot_start_is_unreliable_not_blocking(repo: Path, args: list[str]) -> None:
    assert review(repo, *args) == EXIT_UNRELIABLE


def test_agents_md_without_the_rules_the_axes_cite_makes_the_review_unreliable(repo: Path) -> None:
    (repo / "AGENTS.md").write_text("# AGENTS.md\n\n## Rules\n\n1. **Only one**.\n", encoding="utf-8")
    assert review(repo, "--axes", "readability") == EXIT_UNRELIABLE
