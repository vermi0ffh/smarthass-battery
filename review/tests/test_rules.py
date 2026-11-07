from pathlib import Path

from review.axes import load_axes
from review.rules import parse_rules

ROOT = Path(__file__).resolve().parents[2]

AGENTS_MD = """# AGENTS.md

## Commands

1. **Not a rule**: a numbered list outside the rules.

## Rules

### Architecture

1. **Dependency rule**: `domain ← ports`.
   continued line.
2. **Python 3.12.** lint passes.

### Documentation

3. Documentation describes the **current** behavior; history belongs to git.

## Afterwards

4. **Not a rule either**: after the section.
"""


def test_rules_are_numbered_items_of_the_rules_section_titled_by_their_bold_text() -> None:
    assert parse_rules(AGENTS_MD) == {
        "rule-1": "Dependency rule",
        "rule-2": "Python 3.12",
        "rule-3": "Documentation describes the current behavior",
    }


def test_agents_md_rules_are_numbered_without_gap() -> None:
    rules = parse_rules((ROOT / "AGENTS.md").read_text(encoding="utf-8"))
    assert list(rules) == [f"rule-{n}" for n in range(1, len(rules) + 1)]
    assert all(rules.values())


def test_every_axis_cites_rules_of_agents_md_and_existing_documentation() -> None:
    rules = parse_rules((ROOT / "AGENTS.md").read_text(encoding="utf-8"))
    for axis in load_axes():
        assert set(axis.rules) <= set(rules), axis.key
        for pattern in axis.docs:
            assert list(ROOT.glob(pattern)), f"{axis.key}: {pattern}"
