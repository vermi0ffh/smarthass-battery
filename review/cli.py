"""`make review`: one agent per axis on the branch's Python changes, findings filtered by the derogations."""

import argparse
import contextlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from review.axes import Axis, load_axes
from review.changes import ChangeSet, collect_changes, default_base
from review.engines import EngineError, check_engine, detect_engine, run_engine
from review.findings import (
    FINDINGS_SCHEMA,
    Derogation,
    apply_derogations,
    compare_with_baseline,
    load_baseline_keys,
    load_derogations,
    parse_findings,
)
from review.prompt import build_prompt
from review.report import EXIT_OK, EXIT_UNRELIABLE, AxisRun, Report, format_report
from review.rules import parse_rules

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = Path("review") / "results"  # relative to the repository root, as the derogations file
DEROGATIONS_FILE = Path("review") / "derogations.yaml"

# Beyond this size "nothing found" can no longer be told from attention diluted over a too large diff (on the
# PHP projects this review comes from, 412 KB over 109 files gave 7 findings, none on three of six axes).
DEFAULT_MAX_DIFF_KB = 150


def main(argv: list[str] | None = None, root: Path = ROOT) -> int:
    """Runs the review of the repository at `root`; returns the exit code (see doc/agents/review.md)."""
    args = _parse_args(argv)
    engine = args.engine or detect_engine()
    results_dir = root / RESULTS_DIR
    try:
        check_engine(engine)
        axes = load_axes(only=args.axes.split(",") if args.axes else None)
        base = args.base or default_base(root)
        changes = collect_changes(root, base)
        if not changes.python_files:
            print(f"No Python file changed against {base}.")
            return EXIT_OK
        agents_md = (root / "AGENTS.md").read_text(encoding="utf-8")
        rules = parse_rules(agents_md)
        prompts = {axis.key: build_prompt(root, axis, agents_md, rules, changes, args.language) for axis in axes}
    except (ValueError, RuntimeError, OSError) as error:
        # A review that could not start is not a review that blocks
        print(f"review: {error}")
        return EXIT_UNRELIABLE

    _print_header(engine, changes, args.max_diff_kb)
    derogations = _load_derogations(root / DEROGATIONS_FILE, set(rules))
    results_dir.mkdir(parents=True, exist_ok=True)
    runs = _run_axes(axes, prompts, engine, args.model, args.timeout, args.jobs or len(axes), root, results_dir)
    if all(run.findings is None for run in runs):
        print(f"review: none of the {len(runs)} agents produced a result — report not reliable.")
        for run in runs:
            print(f"  {run.key}: {run.error}")
        print(f"Prompts and raw outputs: {results_dir}")
        return EXIT_UNRELIABLE

    # Deterministic filtering, done here and not by the model
    findings = [finding for run in runs for finding in run.findings or []]
    kept, dismissed = apply_derogations(findings, derogations or [], {axis.key for axis in axes if not axis.derogable})
    baseline_file = results_dir / f"baseline-{engine}.json"
    baseline_keys = _load_baseline_keys(baseline_file)
    report = Report(
        engine=engine,
        base=base,
        merge_base=changes.merge_base,
        files=list(changes.python_files),
        runs=runs,
        kept=kept,
        dismissed=dismissed,
        derogations_applied=derogations is not None,
        unknown_rule_findings=[finding for finding in kept if finding.rule and finding.rule not in rules],
        baseline=compare_with_baseline(kept, baseline_keys) if baseline_keys is not None else None,
    )
    _write_outputs(report, results_dir, baseline_file if args.baseline else None)
    return report.exit_code()


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="make review", description=__doc__)
    parser.add_argument("--base", help="base branch or revision (default: origin/main, else main)")
    parser.add_argument("--axes", help="comma-separated axes to run (default: all, see review/prompts/axes/)")
    parser.add_argument("--engine", help="claude or codex (default: the agent running it, else claude)")
    parser.add_argument("--model", help="model passed to the engine (default: sonnet for claude, codex's own)")
    parser.add_argument("--language", default="English", help="language of the findings (default: English)")
    parser.add_argument("--jobs", type=int, default=0, help="agents run in parallel (default: all)")
    parser.add_argument("--timeout", type=float, default=900, help="seconds allowed per agent (default: 900)")
    parser.add_argument("--max-diff-kb", type=int, default=DEFAULT_MAX_DIFF_KB, help="warn above this diff size")
    parser.add_argument("--baseline", action="store_true", help="save this run as the baseline to compare with")
    return parser.parse_args(argv)


def _print_header(engine: str, changes: ChangeSet, max_diff_kb: int) -> None:
    diff_kb = len(changes.diff.encode()) // 1024
    print(f"Engine : {engine}")
    print(f"Base   : {changes.base} (merge base {changes.merge_base[:7]})")
    print(f"Diff   : {diff_kb} KB over {len(changes.python_files)} file(s)")
    if diff_kb > max_diff_kb:
        print(f"⚠️  Large diff ({diff_kb} KB > {max_diff_kb} KB): every agent gets the whole diff, and beyond this")
        print("    size an axis that finds nothing does not prove there is nothing. Prefer reviewing by slices")
        print("    (BASE=<commit>), and check what each agent received in review/results/.")
    print("Files reviewed:")
    for path in changes.python_files:
        print(f"  - {changes.label(path)}")
    print()


def _load_derogations(path: Path, known_rules: set[str]) -> list[Derogation] | None:
    """The derogations, None when the file is unreadable (then nothing is dismissed and nothing blocks)."""
    try:
        return load_derogations(path, known_rules)
    except (ValueError, OSError) as error:
        print(f"⚠️  {error} — derogations NOT applied.")
        return None


def _load_baseline_keys(path: Path) -> list[str] | None:
    """A broken baseline only loses the comparison, not the report of agents already paid for."""
    try:
        return load_baseline_keys(path)
    except (ValueError, OSError) as error:
        print(f"⚠️  {error} — no comparison with the baseline.")
        return None


def _run_axes(
    axes: list[Axis],
    prompts: dict[str, str],
    engine: str,
    model: str | None,
    timeout_s: float,
    jobs: int,
    root: Path,
    results_dir: Path,
) -> list[AxisRun]:
    runs: dict[str, AxisRun] = {}
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = [
            pool.submit(_run_axis, axis, prompts[axis.key], engine, model, timeout_s, root, results_dir)
            for axis in axes
        ]
        for future in as_completed(futures):
            run = future.result()
            runs[run.key] = run
            status = f"{len(run.findings)} finding(s)" if run.findings is not None else f"FAILED ({run.error})"
            print(f"  {run.key:<26} {run.duration_s:6.0f} s  {status}", flush=True)
    return [runs[axis.key] for axis in axes]


def _run_axis(
    axis: Axis, prompt: str, engine: str, model: str | None, timeout_s: float, root: Path, results_dir: Path
) -> AxisRun:
    """Runs one agent; never raises, so one failed axis does not lose the others' report."""
    raw_file = results_dir / f"{axis.key}.raw.txt"
    started = time.monotonic()
    run = AxisRun(key=axis.key, label=axis.label)
    try:
        (results_dir / f"{axis.key}.prompt.md").write_text(prompt, encoding="utf-8")
        result = run_engine(engine, prompt, FINDINGS_SCHEMA, root, model, timeout_s)
        raw_file.write_text(result.raw, encoding="utf-8")
        run.cost_usd = result.cost_usd
        run.findings = parse_findings(axis.key, result.output)
    except EngineError as error:
        with contextlib.suppress(OSError):  # only an inspection aid: the error is reported anyway
            raw_file.write_text(error.raw, encoding="utf-8")
        run.error = str(error)
    except ValueError as error:
        run.error = f"output does not follow the schema: {error}"
    except Exception as error:  # any other failure: reported as partial coverage, never lost
        run.error = f"{type(error).__name__}: {error}"
    run.duration_s = time.monotonic() - started
    return run


def _write_outputs(report: Report, results_dir: Path, baseline_file: Path | None) -> None:
    print()
    print(format_report(report))
    print()
    report_json = json.dumps(report.to_dict(), indent=2, ensure_ascii=False)
    report_file = results_dir / "report.json"
    _write_atomically(report_file, report_json)
    print(f"JSON report: {report_file}")
    if baseline_file is not None:
        _write_atomically(baseline_file, report_json)
        print(f"Baseline saved: {baseline_file}")


def _write_atomically(path: Path, text: str) -> None:
    """An interrupted write leaves the previous file, never a truncated one (the baseline is read back)."""
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)
