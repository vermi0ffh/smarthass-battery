"""Findings of the agents, the project's derogations, and the comparison with a baseline run."""

import fnmatch
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

SEVERITIES = ("blocking", "important", "advice")

FINDINGS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {"type": "string", "enum": list(SEVERITIES)},
                    "file": {"type": "string"},
                    "line": {"type": ["integer", "null"]},
                    "rule": {"type": ["string", "null"]},
                    "summary": {"type": "string"},
                    "detail": {"type": "string"},
                },
                "required": ["severity", "file", "line", "rule", "summary", "detail"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["findings"],
    "additionalProperties": False,
}


def finding_key(axis: str, file: str, rule: str | None) -> str:
    """Identity of a finding across runs: the wording of a model varies, the axis, file and rule do not."""
    return f"{axis}|{file}|{rule or '-'}"


@dataclass(frozen=True)
class Finding:
    axis: str
    severity: str
    file: str
    line: int | None
    rule: str | None
    summary: str
    detail: str

    def key(self) -> str:
        return finding_key(self.axis, self.file, self.rule)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_findings(axis: str, output: Any) -> list[Finding]:
    """Findings of one agent's structured output; raises ValueError when it does not follow the schema."""
    if not isinstance(output, dict) or not isinstance(output.get("findings"), list):
        raise ValueError("the output has no 'findings' list")
    findings = []
    for item in output["findings"]:
        if not isinstance(item, dict) or item.get("severity") not in SEVERITIES:
            raise ValueError(f"malformed finding: {item!r}")
        line = item.get("line")
        findings.append(
            Finding(
                axis=axis,
                severity=item["severity"],
                file=str(item.get("file", "")),
                line=line if isinstance(line, int) else None,
                rule=item.get("rule") or None,
                summary=str(item.get("summary", "")),
                detail=str(item.get("detail", "")),
            )
        )
    return findings


@dataclass(frozen=True)
class Derogation:
    rule: str
    paths: tuple[str, ...]  # fnmatch patterns on the repository path ('*' also matches '/'); empty = every file
    reason: str

    def covers(self, finding: Finding) -> bool:
        if finding.rule != self.rule:
            return False
        return not self.paths or any(fnmatch.fnmatch(finding.file, pattern) for pattern in self.paths)


def load_derogations(path: Path, known_rules: set[str]) -> list[Derogation]:
    """The derogations file; raises ValueError on a malformed entry or an unknown rule (nothing is half-applied)."""
    if not path.exists():
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as error:
        raise ValueError(f"{path}: invalid YAML: {error}") from error
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a mapping with a 'derogations' list")
    entries = data.get("derogations") or []
    if not isinstance(entries, list):
        raise ValueError(f"{path}: 'derogations' must be a list")
    derogations = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("rule"), str) or not entry.get("reason"):
            raise ValueError(f"{path}: each derogation needs a rule and a reason: {entry!r}")
        if entry["rule"] not in known_rules:
            raise ValueError(f"{path}: unknown rule '{entry['rule']}'")
        paths = entry.get("paths") or []
        if not isinstance(paths, list) or not all(isinstance(pattern, str) for pattern in paths):
            raise ValueError(f"{path}: 'paths' of {entry['rule']} must be a list of patterns")
        derogations.append(Derogation(rule=entry["rule"], paths=tuple(paths), reason=str(entry["reason"])))
    return derogations


def apply_derogations(
    findings: list[Finding], derogations: list[Derogation], non_derogable_axes: set[str]
) -> tuple[list[Finding], list[Finding]]:
    """Split the findings into (kept, dismissed by a derogation)."""
    kept: list[Finding] = []
    dismissed: list[Finding] = []
    for finding in findings:
        waived = finding.axis not in non_derogable_axes and any(d.covers(finding) for d in derogations)
        (dismissed if waived else kept).append(finding)
    return kept, dismissed


@dataclass(frozen=True)
class BaselineComparison:
    new: list[str]
    still_there: list[str]
    gone: list[str]


def load_baseline_keys(path: Path) -> list[str] | None:
    """Finding keys of a saved report; None when there is no baseline, ValueError when it is unreadable."""
    if not path.exists():
        return None
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        return [finding_key(f["axis"], f["file"], f.get("rule")) for f in report["findings"]]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise ValueError(f"{path}: unreadable baseline ({error!r})") from error


def compare_with_baseline(findings: list[Finding], baseline_keys: list[str]) -> BaselineComparison:
    """The finding keys of this run against a previous run's: a baseline compares runs, it dismisses nothing."""
    current = {finding.key() for finding in findings}
    previous = set(baseline_keys)
    return BaselineComparison(
        new=sorted(current - previous), still_there=sorted(current & previous), gone=sorted(previous - current)
    )
