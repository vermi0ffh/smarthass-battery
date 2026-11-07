import json
from pathlib import Path

import pytest

from review.findings import (
    Finding,
    apply_derogations,
    compare_with_baseline,
    load_baseline_keys,
    load_derogations,
    parse_findings,
)


def finding(
    axis: str = "naming", file: str = "custom_components/smart_hass_battery/a.py", rule: str | None = "rule-8"
) -> Finding:
    return Finding(axis=axis, severity="blocking", file=file, line=3, rule=rule, summary="s", detail="d")


def test_findings_are_parsed_from_the_structured_output() -> None:
    output = {
        "findings": [
            {"severity": "advice", "file": "a.py", "line": None, "rule": None, "summary": "s", "detail": "d"},
        ]
    }
    assert parse_findings("tests", output) == [
        Finding(axis="tests", severity="advice", file="a.py", line=None, rule=None, summary="s", detail="d")
    ]


def test_an_empty_rule_is_no_rule_and_a_non_integer_line_is_unknown() -> None:
    output = {
        "findings": [{"severity": "advice", "file": "a.py", "line": "12", "rule": "", "summary": "s", "detail": "d"}]
    }
    [parsed] = parse_findings("tests", output)
    assert (parsed.rule, parsed.line) == (None, None)


@pytest.mark.parametrize("output", [None, {}, {"findings": [{"severity": "critical"}]}])
def test_output_off_the_schema_is_refused(output: object) -> None:
    with pytest.raises(ValueError):
        parse_findings("tests", output)


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "derogations.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_derogation_dismisses_findings_of_its_rule_in_its_paths_only(tmp_path: Path) -> None:
    derogations = load_derogations(
        write(tmp_path, "derogations:\n  - rule: rule-8\n    paths: ['tools/*']\n    reason: legacy\n"), {"rule-8"}
    )
    covered = finding(file="tools/simulator/engine.py")
    other_path = finding(file="custom_components/smart_hass_battery/a.py")
    other_rule = finding(file="tools/x.py", rule="rule-9")
    kept, dismissed = apply_derogations([covered, other_path, other_rule], derogations, set())
    assert (kept, dismissed) == ([other_path, other_rule], [covered])


def test_derogation_without_paths_applies_everywhere_but_never_to_a_non_derogable_axis(tmp_path: Path) -> None:
    derogations = load_derogations(write(tmp_path, "derogations:\n  - rule: rule-23\n    reason: r\n"), {"rule-23"})
    naming, security = finding(rule="rule-23"), finding(axis="security", rule="rule-23")
    assert apply_derogations([naming, security], derogations, {"security"}) == ([security], [naming])


def test_a_finding_without_rule_escapes_every_derogation(tmp_path: Path) -> None:
    derogations = load_derogations(write(tmp_path, "derogations:\n  - rule: rule-8\n    reason: r\n"), {"rule-8"})
    unlabelled = finding(rule=None)
    assert apply_derogations([unlabelled], derogations, set()) == ([unlabelled], [])


def test_missing_or_empty_derogations_file_means_none(tmp_path: Path) -> None:
    assert load_derogations(tmp_path / "absent.yaml", set()) == []
    assert load_derogations(write(tmp_path, "derogations: []\n"), set()) == []


@pytest.mark.parametrize(
    "text",
    [
        "derogations: [rule: rule-8\n",  # invalid YAML
        "- rule: rule-8\n",  # not a mapping
        "derogations:\n  - rule: [rule-8]\n    reason: r\n",  # rule not a string
        "derogations:\n  - rule: rule-8\n    paths: [1]\n    reason: r\n",  # pattern not a string
        "derogations:\n  - rule: rule-8\n",  # no reason
        "derogations:\n  - rule: rule-99\n    reason: r\n",  # unknown rule
        "derogations:\n  - rule: rule-8\n    paths: tools/*\n    reason: r\n",  # paths not a list
    ],
)
def test_malformed_derogations_file_is_refused_as_a_whole(tmp_path: Path, text: str) -> None:
    with pytest.raises(ValueError):
        load_derogations(write(tmp_path, text), {"rule-8"})


def test_baseline_compares_by_axis_file_and_rule_not_by_wording(tmp_path: Path) -> None:
    baseline_file = tmp_path / "baseline.json"
    previous = [finding(), finding(file="gone.py")]
    baseline_file.write_text(json.dumps({"findings": [f.to_dict() for f in previous]}), encoding="utf-8")
    reworded = Finding(**{**finding().to_dict(), "summary": "other words", "line": 40})
    comparison = compare_with_baseline([reworded, finding(rule="rule-9")], load_baseline_keys(baseline_file) or [])
    assert comparison.new == ["naming|custom_components/smart_hass_battery/a.py|rule-9"]
    assert comparison.still_there == ["naming|custom_components/smart_hass_battery/a.py|rule-8"]
    assert comparison.gone == ["naming|gone.py|rule-8"]


def test_no_baseline_file_means_no_comparison(tmp_path: Path) -> None:
    assert load_baseline_keys(tmp_path / "absent.json") is None


@pytest.mark.parametrize("text", ['{"findings": [', '{"findings": [{"axis": "a"}]}', "[]"])
def test_an_unreadable_baseline_is_refused(tmp_path: Path, text: str) -> None:
    path = tmp_path / "baseline.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="unreadable baseline"):
        load_baseline_keys(path)
