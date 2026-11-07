from review.findings import BaselineComparison, Finding
from review.report import EXIT_BLOCKING, EXIT_OK, AxisRun, Report, format_report


def finding(severity: str, file: str = "a.py", line: int | None = 3) -> Finding:
    return Finding(axis="naming", severity=severity, file=file, line=line, rule="rule-8", summary="s", detail="d")


def report(kept: list[Finding], runs: list[AxisRun] | None = None, derogations_applied: bool = True) -> Report:
    return Report(
        engine="claude",
        base="origin/main",
        merge_base="abc1234def",
        files=["a.py"],
        runs=runs or [AxisRun(key="naming", label="Naming", findings=kept, cost_usd=0.1)],
        kept=kept,
        dismissed=[],
        derogations_applied=derogations_applied,
    )


def test_blocking_findings_fail_the_run_unless_the_derogations_could_not_be_applied() -> None:
    assert report([finding("important")]).exit_code() == EXIT_OK
    assert report([finding("blocking")]).exit_code() == EXIT_BLOCKING
    assert report([finding("blocking")], derogations_applied=False).exit_code() == EXIT_OK


def test_findings_are_printed_by_severity_with_axis_location_and_rule() -> None:
    text = format_report(report([finding("advice"), finding("blocking", line=None)]))
    assert text.index("## BLOCKING (1)") < text.index("## ADVICE (1)")
    assert "- [Naming] a.py {rule-8} — s" in text
    assert "- [Naming] a.py:3 {rule-8} — s" in text


def test_a_failed_agent_is_reported_as_partial_coverage_not_as_nothing_found() -> None:
    runs = [
        AxisRun(key="naming", label="Naming", findings=[]),
        AxisRun(key="tests", label="Tests", findings=None, error="claude timed out after 900 s"),
    ]
    text = format_report(report([], runs=runs))
    assert "Axis 'tests' failed: claude timed out after 900 s" in text
    assert "Partial coverage: 1 agent(s) of 2 failed." in text


def test_dismissed_findings_unknown_rules_and_unapplied_derogations_are_signalled() -> None:
    unknown = Finding(axis="naming", severity="advice", file="a.py", line=1, rule="rule-99", summary="s", detail="d")
    result = report([unknown], derogations_applied=False)
    result.dismissed = [finding("blocking")]
    result.unknown_rule_findings = [unknown]
    text = format_report(result)
    assert "(1 finding(s) dismissed by a derogation of review/derogations.yaml)" in text
    assert "1 finding(s) with a rule id not in AGENTS.md" in text
    assert "The derogations could not be applied" in text
    serialized = result.to_dict()
    assert serialized["dismissed"] == [finding("blocking").to_dict()]
    assert serialized["unknown_rule_findings"] == [unknown.to_dict()]
    assert serialized["derogations_applied"] is False


def test_failed_agents_are_listed_in_the_json_report() -> None:
    runs = [AxisRun(key="tests", label="Tests", findings=None, error="boom")]
    assert report([], runs=runs).to_dict()["agents_failed"] == [{"axis": "tests", "error": "boom"}]


def test_baseline_comparison_and_cost_are_reported_and_serialized() -> None:
    result = report([finding("advice")])
    result.baseline = BaselineComparison(new=["naming|a.py|rule-8"], still_there=[], gone=["tests|b.py|-"])
    text = format_report(result)
    assert "Against the baseline: 1 new · 0 already seen · 1 gone" in text
    assert "NEW  naming  a.py  rule-8" in text
    assert "Cost: $0.10" in text
    assert result.to_dict()["baseline"] == {"new": ["naming|a.py|rule-8"], "still_there": [], "gone": ["tests|b.py|-"]}
