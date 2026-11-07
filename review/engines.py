"""Agent engines: the coding-agent CLIs that run one axis' prompt, read-only, with a structured output."""

import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EngineResult:
    output: Any  # the structured output, to be checked against the findings schema
    raw: str  # what the CLI printed, kept in review/results/ for inspection
    cost_usd: float | None


class EngineError(RuntimeError):
    def __init__(self, message: str, raw: str = "") -> None:
        super().__init__(message)
        self.raw = raw


# Model used when none is given: on 2026-10-18 the nine axes cost $6.02 with Claude Code's default model on a 50 KB
# diff, one axis $0.20 with sonnet on 31 KB, with findings of the same kind
DEFAULT_MODELS = {"claude": "sonnet"}


def detect_engine() -> str:
    """The engine of the agent running `make review`, else claude."""
    if os.environ.get("CODEX_THREAD_ID") and not os.environ.get("CLAUDECODE"):
        return "codex"
    return "claude"


def check_engine(engine: str) -> None:
    """Raises ValueError for an unknown engine or a CLI that is not installed."""
    if engine not in ENGINES:
        raise ValueError(f"unknown engine '{engine}' (available: {', '.join(ENGINES)})")
    if shutil.which(engine) is None:
        raise ValueError(f"'{engine}' is not installed or not in the PATH")


def run_engine(
    engine: str, prompt: str, schema: dict[str, Any], root: Path, model: str | None, timeout_s: float
) -> EngineResult:
    return _RUNNERS[engine](prompt, schema, root, model or DEFAULT_MODELS.get(engine), timeout_s)


def _run_claude(prompt: str, schema: dict[str, Any], root: Path, model: str | None, timeout_s: float) -> EngineResult:
    command = [
        "claude",
        "-p",
        "--output-format",
        "json",
        "--json-schema",
        json.dumps(schema),
        # Read-only tools, and nothing that would wait for a permission prompt
        "--tools",
        "Read,Grep,Glob",
        "--permission-mode",
        "dontAsk",
        "--no-session-persistence",
    ]
    if model:
        command += ["--model", model]
    raw = _run(command, prompt, root, timeout_s)
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as error:
        raise EngineError(f"claude printed no JSON: {error}", raw) from error
    if not isinstance(result, dict):
        raise EngineError("claude printed JSON that is not an object", raw)
    if result.get("is_error"):
        raise EngineError(f"claude failed: {result.get('result') or result.get('subtype')}", raw)
    output = result.get("structured_output")
    if output is None:
        raise EngineError("claude returned no structured output", raw)
    return EngineResult(output=output, raw=raw, cost_usd=result.get("total_cost_usd"))


def _run_codex(prompt: str, schema: dict[str, Any], root: Path, model: str | None, timeout_s: float) -> EngineResult:
    with tempfile.TemporaryDirectory(prefix="review-codex-") as tmp:
        schema_path = Path(tmp) / "schema.json"
        output_path = Path(tmp) / "output.json"
        schema_path.write_text(json.dumps(schema), encoding="utf-8")
        command = [
            "codex",
            "exec",
            "--sandbox",
            "read-only",
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(output_path),
        ]
        if model:
            command += ["--model", model]
        command.append("-")  # the prompt on stdin
        raw = _run(command, prompt, root, timeout_s)
        if not output_path.exists():
            raise EngineError("codex wrote no final message", raw)
        last_message = output_path.read_text(encoding="utf-8")
    try:
        output = json.loads(last_message)
    except json.JSONDecodeError as error:
        raise EngineError(f"codex's final message is not JSON: {error}", raw + last_message) from error
    return EngineResult(output=output, raw=raw + last_message, cost_usd=None)


def _run(command: list[str], prompt: str, root: Path, timeout_s: float) -> str:
    try:
        result = subprocess.run(
            command, input=prompt, cwd=root, capture_output=True, text=True, timeout=timeout_s, check=False
        )
    except subprocess.TimeoutExpired as error:
        partial = "".join(_text(stream) for stream in (error.stdout, error.stderr))
        raise EngineError(f"{command[0]} timed out after {timeout_s:.0f} s", partial) from error
    except OSError as error:
        raise EngineError(f"{command[0]} could not be run: {error}") from error
    if result.returncode != 0:
        raise EngineError(
            f"{command[0]} exited with {result.returncode}: {result.stderr.strip()[-500:]}",
            result.stdout + result.stderr,
        )
    return result.stdout


def _text(stream: str | bytes | None) -> str:
    if isinstance(stream, bytes):
        return stream.decode(errors="replace")
    return stream or ""


_RUNNERS: dict[str, Callable[[str, dict[str, Any], Path, str | None, float], EngineResult]] = {
    "claude": _run_claude,
    "codex": _run_codex,
}
ENGINES = tuple(_RUNNERS)
