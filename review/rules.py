"""Rule identifiers of AGENTS.md (`rule-<n>`), the labels the findings are filtered on."""

import re

_RULE_LINE = re.compile(r"^(\d+)\. (.+)$")
_BOLD_TITLE = re.compile(r"^\*\*(.+?)\*\*")


def parse_rules(agents_md: str) -> dict[str, str]:
    """Map each numbered rule of the "## Rules" section to a short title, in order."""
    rules: dict[str, str] = {}
    in_rules = False
    for line in agents_md.splitlines():
        if line.startswith("## "):
            in_rules = line.strip() == "## Rules"
            continue
        match = _RULE_LINE.match(line) if in_rules else None
        if match:
            rules[f"rule-{match.group(1)}"] = _title(match.group(2))
    return rules


def _title(text: str) -> str:
    bold = _BOLD_TITLE.match(text)
    if bold:
        return bold.group(1).rstrip(".:")
    # A rule without a bold title (e.g. rule 22): its first clause
    return re.split(r"[;:]|\. ", text, maxsplit=1)[0].replace("**", "").rstrip(".")
