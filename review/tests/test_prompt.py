from pathlib import Path

import pytest

from review.axes import Axis
from review.changes import ChangeSet
from review.prompt import build_prompt

CHANGES = ChangeSet(
    base="origin/main",
    merge_base="abc1234def",
    python_files=("custom_components/smart_hass_battery/a.py", "custom_components/smart_hass_battery/b.py"),
    other_files=("doc/en/README.md",),
    uncommitted=frozenset({"custom_components/smart_hass_battery/b.py"}),
    diff="+x = 1\n",
    commits="abc1234 Add a",
)
RULES = {"rule-1": "Dependency rule", "rule-2": "New port", "rule-3": "HA through ports"}


def axis(docs: tuple[str, ...] = ()) -> Axis:
    return Axis(key="arch", label="Architecture", rules=("rule-3",), docs=docs, derogable=True, body="# Your axis")


def test_prompt_holds_rules_axis_docs_rule_ids_language_and_changes(tmp_path: Path) -> None:
    (tmp_path / "doc").mkdir()
    (tmp_path / "doc" / "architecture.md").write_text("Layers.", encoding="utf-8")

    prompt = build_prompt(tmp_path, axis(("doc/*.md",)), "AGENTS RULES", RULES, CHANGES, "French")

    for part in [
        "AGENTS RULES",
        "## doc/architecture.md\n\nLayers.",
        "# Your axis",
        "Write `summary` and `detail` in French",
    ]:
        assert part in prompt
    # The axis' own rules are listed first
    assert prompt.index("`rule-3` — HA through ports") < prompt.index("`rule-1` — Dependency rule")
    assert "- custom_components/smart_hass_battery/b.py (not committed)" in prompt
    assert "- doc/en/README.md" in prompt
    assert "abc1234 Add a" in prompt
    assert "```diff\n+x = 1\n" in prompt


def test_an_axis_citing_a_rule_missing_from_agents_md_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cites rules missing from AGENTS.md: rule-3"):
        build_prompt(tmp_path, axis(), "", {"rule-1": "Dependency rule"}, CHANGES, "English")


def test_a_documentation_pattern_matching_nothing_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no documentation matches 'doc/missing.md'"):
        build_prompt(tmp_path, axis(("doc/missing.md",)), "", RULES, CHANGES, "English")
