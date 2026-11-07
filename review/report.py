"""The review report: printed to the terminal and written to review/results/report.json."""

from dataclasses import asdict, dataclass, field
from typing import Any

from review.findings import SEVERITIES, BaselineComparison, Finding

EXIT_OK, EXIT_BLOCKING, EXIT_UNRELIABLE = 0, 1, 2


@dataclass
class AxisRun:
    key: str
    label: str
    findings: list[Finding] | None = None  # None: the agent failed, which is not "nothing found"
    error: str | None = None
    cost_usd: float | None = None
    duration_s: float = 0.0


@dataclass
class Report:
    engine: str
    base: str
    merge_base: str
    files: list[str]
    runs: list[AxisRun]
    kept: list[Finding]
    dismissed: list[Finding]
    derogations_applied: bool
    unknown_rule_findings: list[Finding] = field(default_factory=list)
    baseline: BaselineComparison | None = None

    @property
    def failed_runs(self) -> list[AxisRun]:
        return [run for run in self.runs if run.findings is None]

    @property
    def blocking_count(self) -> int:
        return sum(1 for finding in self.kept if finding.severity == "blocking")

    def exit_code(self) -> int:
        # Unapplied derogations would make accepted deviations block: report them, do not fail on them
        if self.blocking_count and self.derogations_applied:
            return EXIT_BLOCKING
        return EXIT_OK

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "base": self.base,
            "merge_base": self.merge_base,
            "files": self.files,
            "derogations_applied": self.derogations_applied,
            "agents_total": len(self.runs),
            "agents_failed": [{"axis": run.key, "error": run.error} for run in self.failed_runs],
            "cost_usd": self.cost_usd,
            "unknown_rule_findings": [finding.to_dict() for finding in self.unknown_rule_findings],
            "baseline": asdict(self.baseline) if self.baseline else None,
            "dismissed": [finding.to_dict() for finding in self.dismissed],
            "findings": [finding.to_dict() for finding in self.kept],
        }

    @property
    def cost_usd(self) -> float | None:
        costs = [run.cost_usd for run in self.runs if run.cost_usd is not None]
        return round(sum(costs), 4) if costs else None


def format_report(report: Report) -> str:
    labels = {run.key: run.label for run in report.runs}
    lines = [f"=== Review report ({len(report.files)} file(s), engine {report.engine}, base {report.base}) ==="]
    for severity in SEVERITIES:
        findings = sorted(
            (f for f in report.kept if f.severity == severity), key=lambda f: (f.file, f.line or 0, f.axis)
        )
        if not findings:
            continue
        lines += ["", f"## {severity.upper()} ({len(findings)})", ""]
        for finding in findings:
            location = finding.file + (f":{finding.line}" if finding.line else "")
            rule = f" {{{finding.rule}}}" if finding.rule else ""
            lines.append(f"- [{labels.get(finding.axis, finding.axis)}] {location}{rule} — {finding.summary}")
            lines += [f"  {line}" for line in finding.detail.splitlines()]
            lines.append("")
    if not report.kept:
        lines += ["", "No finding: nothing to report on the changed files."]
    if report.dismissed:
        lines += ["", f"({len(report.dismissed)} finding(s) dismissed by a derogation of review/derogations.yaml)"]
    if report.unknown_rule_findings:
        lines += [
            "",
            f"⚠️  {len(report.unknown_rule_findings)} finding(s) with a rule id not in AGENTS.md (not derogable).",
        ]
    if report.baseline is not None:
        comparison = report.baseline
        lines += [
            "",
            f"Against the baseline: {len(comparison.new)} new · {len(comparison.still_there)} already seen"
            f" · {len(comparison.gone)} gone",
        ]
        lines += [f"  NEW  {key.replace('|', '  ')}" for key in comparison.new]
    for run in report.failed_runs:
        lines += ["", f"⚠️  Axis '{run.key}' failed: {run.error}"]
    if report.failed_runs:
        lines.append(f"⚠️  Partial coverage: {len(report.failed_runs)} agent(s) of {len(report.runs)} failed.")
    if not report.derogations_applied:
        lines += ["", "⚠️  The derogations could not be applied: blocking findings do not fail the run."]
    if report.cost_usd is not None:
        lines += ["", f"Cost: ${report.cost_usd:.2f}"]
    return "\n".join(lines)
