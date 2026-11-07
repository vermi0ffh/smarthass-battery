import json
from collections.abc import Callable
from pathlib import Path

import pytest

from review.engines import EngineError, check_engine, detect_engine, run_engine
from review.findings import FINDINGS_SCHEMA


def test_claude_runs_read_only_with_the_schema_and_returns_its_structured_output(
    tmp_path: Path, fake_cli: Callable[[str, str], None]
) -> None:
    answer = {"type": "result", "is_error": False, "structured_output": {"findings": []}, "total_cost_usd": 0.12}
    fake_cli("claude", f"echo '{json.dumps(answer)}'")

    result = run_engine("claude", "the prompt", FINDINGS_SCHEMA, tmp_path, "sonnet", timeout_s=30)

    assert (result.output, result.cost_usd) == ({"findings": []}, 0.12)
    args = (tmp_path / "args").read_text().splitlines()
    assert args[args.index("--tools") + 1] == "Read,Grep,Glob"
    assert json.loads(args[args.index("--json-schema") + 1]) == FINDINGS_SCHEMA
    assert args[args.index("--model") + 1] == "sonnet"
    assert (tmp_path / "stdin").read_text() == "the prompt"


def test_claude_uses_sonnet_unless_another_model_is_given(tmp_path: Path, fake_cli: Callable[[str, str], None]) -> None:
    answer = {"is_error": False, "structured_output": {"findings": []}}
    fake_cli("claude", f"echo '{json.dumps(answer)}'")
    run_engine("claude", "p", FINDINGS_SCHEMA, tmp_path, None, timeout_s=30)
    args = (tmp_path / "args").read_text().splitlines()
    assert args[args.index("--model") + 1] == "sonnet"


@pytest.mark.parametrize(
    "script, message",
    [
        ("echo 'not json'", "printed no JSON"),
        ("""echo '{"is_error": true, "result": "budget exceeded"}'""", "budget exceeded"),
        ("""echo '{"is_error": false}'""", "no structured output"),
        ("echo boom >&2; exit 3", "exited with 3: boom"),
        ("echo '[]'", "not an object"),
    ],
)
def test_claude_failures_raise_with_the_reason(
    tmp_path: Path, fake_cli: Callable[[str, str], None], script: str, message: str
) -> None:
    fake_cli("claude", script)
    with pytest.raises(EngineError, match=message):
        run_engine("claude", "p", FINDINGS_SCHEMA, tmp_path, None, timeout_s=30)


def test_codex_runs_in_a_read_only_sandbox_and_returns_its_final_message(
    tmp_path: Path, fake_cli: Callable[[str, str], None]
) -> None:
    # The final message goes to the file given after --output-last-message
    script = (
        'while [ $# -gt 0 ]; do [ "$1" = "--output-last-message" ] && out="$2"; shift; done\n'
        """echo '{"findings": []}' > "$out\""""
    )
    fake_cli("codex", script)

    result = run_engine("codex", "the prompt", FINDINGS_SCHEMA, tmp_path, None, timeout_s=30)

    assert result.output == {"findings": []}
    args = (tmp_path / "args").read_text().splitlines()
    assert args[:4] == ["exec", "--sandbox", "read-only", "--output-schema"]
    assert args[-1] == "-"


def test_an_agent_over_its_time_limit_is_stopped(tmp_path: Path, fake_cli: Callable[[str, str], None]) -> None:
    fake_cli("claude", "sleep 5")
    with pytest.raises(EngineError, match="timed out"):
        run_engine("claude", "p", FINDINGS_SCHEMA, tmp_path, None, timeout_s=0.5)


@pytest.mark.parametrize(
    "env, engine",
    [({}, "claude"), ({"CODEX_THREAD_ID": "t"}, "codex"), ({"CODEX_THREAD_ID": "t", "CLAUDECODE": "1"}, "claude")],
)
def test_the_engine_defaults_to_the_agent_running_the_review(
    monkeypatch: pytest.MonkeyPatch, env: dict[str, str], engine: str
) -> None:
    for name in ("CODEX_THREAD_ID", "CLAUDECODE"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    assert detect_engine() == engine


def test_an_unknown_or_missing_engine_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match="unknown engine 'gemini'"):
        check_engine("gemini")
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(ValueError, match="'claude' is not installed"):
        check_engine("claude")
