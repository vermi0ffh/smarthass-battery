"""Builds one axis' prompt: preamble, project rules, the axis' documentation, rule ids, the axis, the changes."""

from pathlib import Path

from review.axes import Axis
from review.changes import ChangeSet

PREAMBLE_FILE = Path(__file__).parent / "prompts" / "preamble.md"


def axis_docs(root: Path, axis: Axis) -> list[Path]:
    """The documentation files of the axis, in the order of its patterns; a pattern matching nothing raises."""
    paths: list[Path] = []
    for pattern in axis.docs:
        matches = sorted(root.glob(pattern))
        if not matches:
            raise ValueError(f"axis '{axis.key}': no documentation matches '{pattern}'")
        paths += [path for path in matches if path not in paths]
    return paths


def build_prompt(
    root: Path, axis: Axis, agents_md: str, rules: dict[str, str], changes: ChangeSet, language: str
) -> str:
    # The derogations are deliberately not given to the agents: knowing them, agents censor themselves and the
    # deterministic filtering downstream is never exercised — losing both reproducibility and the count of what
    # it dismissed.
    sections = [PREAMBLE_FILE.read_text(encoding="utf-8").strip(), "# Project rules (AGENTS.md)", agents_md.strip()]

    docs = axis_docs(root, axis)
    if docs:
        sections.append("# Documentation of your axis")
        for path in docs:
            sections.append(f"## {path.relative_to(root)}\n\n{path.read_text(encoding='utf-8').strip()}")

    # Listed explicitly: left scattered in AGENTS.md, the identifiers are seldom picked up by the agents, and the
    # whole derogation filtering depends on them.
    unknown = [rule for rule in axis.rules if rule not in rules]
    if unknown:
        raise ValueError(f"axis '{axis.key}' cites rules missing from AGENTS.md: {', '.join(unknown)}")
    others = [rule for rule in rules if rule not in axis.rules]
    ids = "\n".join(f"- `{rule}` — {rules[rule]}" for rule in [*axis.rules, *others])
    sections.append(
        "# Available rule identifiers\n\n"
        "These are the only valid identifiers for `rule`. Those of your axis come first.\n\n" + ids
    )

    sections.append(axis.body)
    sections.append(f"# Language\n\nWrite `summary` and `detail` in {language}.")
    sections.append(_changes_section(changes))
    return "\n\n".join(sections) + "\n"


def _changes_section(changes: ChangeSet) -> str:
    def listing(paths: tuple[str, ...]) -> str:
        if not paths:
            return "(none)"
        return "\n".join(f"- {changes.label(path)}" for path in paths)

    return "\n\n".join(
        [
            f"# Changes against `{changes.base}` (merge base {changes.merge_base[:7]})",
            "## Changed Python files\n\n" + listing(changes.python_files),
            "## Other changed files\n\n" + listing(changes.other_files),
            "## Commits of the branch\n\n" + (f"```\n{changes.commits}\n```" if changes.commits else "(none)"),
            f"## Full diff\n\n```diff\n{changes.diff}\n```",
        ]
    )
