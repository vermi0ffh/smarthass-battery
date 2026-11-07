# AI code review: `make review`

`make review` sends the Python changes of the current branch to a team of agents, one per **axis** (readability,
architecture, tests…), each checking them against the rules of [AGENTS.md](../../AGENTS.md#rules). The findings are
then filtered by the project's derogations — mechanically, never by the model — and aggregated into one report. It
runs before a pull request (workflow step 6 of [contributing](../en/contributing.md#workflow)); it does not replace
`make lint`, `make typecheck` and `make test`, whose findings the agents are told not to repeat.

## Layout

```
review/
  __main__.py, cli.py     ← the command (python -m review)
  changes.py              ← what is reviewed (git)
  axes.py, prompt.py      ← the axes and the prompt of each agent
  engines.py              ← claude / codex CLIs, read-only, structured output
  findings.py             ← schema, derogations, baseline
  report.py               ← terminal report, report.json, exit code
  rules.py                ← rule ids parsed from AGENTS.md
  prompts/preamble.md     ← role, severities, output format: common to every axis
  prompts/axes/*.md       ← one file per axis
  derogations.yaml        ← accepted deviations
  results/                ← report.json, each agent's prompt and raw output, baselines (git-ignored)
```

## What is reviewed

The Python files changed since the merge base of `HEAD` with `BASE` (default `origin/main`, else `main`): the commits
of the branch, the uncommitted changes (staged or not) and the new untracked files — git-ignored files excepted,
deleted files left out. On `main` with everything pushed, only the uncommitted work is reviewed; `BASE=HEAD~3`
reviews the last three commits.

The prompts go to the engine's service (Anthropic for claude, OpenAI for codex): an untracked file that is not
git-ignored is sent in full, so keep local scratch files with a secret out of the tree or in `.gitignore`. The list
of files is printed before the agents start.

Each agent gets, in this order: the preamble, `AGENTS.md`, the documentation of its axis (front matter `docs`), the
list of rule identifiers (its axis' first), the axis prompt, the language of the findings, then the changes: the
Python files (marked "not committed" when so), the names of the other changed files (so the documentation axis
knows which docs changed), the branch's commit messages and stats (rules 16 and 23), and the full diff. The agent
can read any file of the repository with read-only tools (`Read`, `Grep`, `Glob` for claude; the read-only sandbox
for codex).

Above `--max-diff-kb` (150 KB) a warning is printed: every agent receives the whole diff, and on a large diff an axis
that finds nothing does not prove there is nothing. Review by slices with `BASE=<commit>`.

## Running

```bash
make review                                  # every axis, findings in English
make review REVIEW_LANG=French               # findings in another language (any language name)
make review AXES=tests,architecture          # some axes only
make review BASE=HEAD~2 MODEL=opus           # another base, another model (default: sonnet for claude)
make review ENGINE=codex                     # default: the agent running it (CODEX_THREAD_ID), else claude
make review BASELINE=1                       # also save the run as the baseline
python -m review --help                      # --jobs, --timeout (900 s per agent), --max-diff-kb
```

The agents run in parallel; each prompt is 50–100 KB before the diff, and the claude engine prints the cost. The claude
engine uses `sonnet` unless `MODEL` says otherwise: on 2026-10-18 (in Smart Hass - Energy Optimizer, where it comes from), the
nine axes on a 50 KB diff took 46 s and cost $6.02 with Claude Code's default model, one axis with sonnet on a 31 KB
diff $0.20, with findings of the same kind.
Codex uses its own default model.

Exit code: `1` when a blocking finding remains, `2` when the review is not reliable (no agent produced a result, or
it could not start: unknown axis or engine, unknown base, an axis citing a rule missing from AGENTS.md), `0`
otherwise — including when the derogations file could not be read: the derogations are
then not applied, which is reported, and blocking findings do not fail the run (an accepted deviation must not
block because the file is broken).

## Axes

| Axis | Rules | Checks |
|------|-------|--------|
| `readability` | 9 | dead or duplicated code, too long or complex functions, magic, useless comments, over-engineering |
| `robustness` | 2, 4, 10, 12 | edge cases (`unavailable`, other units, restarts, meter resets), swallowed exceptions, blocking calls, listeners removed |
| `architecture` | 1–3, 5, 6 | pure model, HA semantics in the tracker only, read only, independence, configuration not code |
| `naming` | 8–10 | explicit English names, units in names, patterns suited to their intent, premature abstraction, introspection |
| `tests` | 13, 14, 16, 17, 23 | relevance, missing tests, right family, observable behavior without introspection, changed tests justified, refactoring commits without tests |
| `security` | 21, 22 | secrets, personal data, input validation, dangerous functions, logs — **not derogable** |
| `time-async` | 4, 11 | aware datetimes, durations from events, non-blocking event loop, timers replaced and cancelled, no double counting |
| `compatibility-estimates` | 3, 20, 25 | config entries migrated, stored state read back, entities as a contract, estimate changes replayed and switchable |
| `documentation` | 8, 18, 19 | user documentation and translations in both languages, `doc/agents/`, AGENTS.md, current behavior only |

An axis is a Markdown file of `review/prompts/axes/` with a YAML front matter:

```markdown
---
label: Quality and relevance of the tests     # shown in the report
rules: [rule-16, rule-17]                     # the axis' rules, listed first to the agent
docs: [doc/agents/testing.md]                 # glob patterns inlined in the prompt (a pattern matching nothing fails)
derogable: true                               # false: findings never dismissed (security)
---
# Your axis: …
```

Adding an axis is adding a file; its prompt says what to check, in the project's terms, and refers to the rules by
number. `review/tests/test_rules.py` checks that every axis cites existing rules and documentation.

## Rule identifiers and derogations

A finding carries the identifier of the rule it applies, `rule-<n>` for rule *n* of AGENTS.md, or `null` when it
follows from no rule. The list is parsed from the "## Rules" section of AGENTS.md (`rules.py`) and given explicitly
to every agent: left implicit, identifiers are seldom filled in, and the derogations depend on them. A finding with
an identifier that does not exist is kept and counted in the report. Renumbering the rules changes the identifiers:
update the axes' front matter and `derogations.yaml` in the same commit.

`review/derogations.yaml` lists the deviations the project accepts:

```yaml
derogations:
  - rule: rule-8
    paths: ["custom_components/*/translations/*"]   # fnmatch on the repository path, '*' also matches '/'; no paths = everywhere
    reason: why the project accepts it
```

A finding is dismissed when its rule and its file match a derogation, unless its axis is not derogable. The
derogations are **not** given to the agents: knowing them, agents censor themselves, and the deterministic filter is
never exercised — losing both reproducibility and the count of what was dismissed (printed with the report). An
unlabelled finding escapes every derogation. A malformed file, or a derogation of an unknown rule, is refused as a
whole.

## Reading the report

The terminal report groups the findings by severity — `blocking` (a bug, a regression, a rule broken without
justification: fix before merge), `important` (real debt: fix or plan), `advice` — each with its axis, location,
rule, summary and detail. `review/results/report.json` holds the same, plus the dismissed findings and the failed
agents.

- A failed agent (timeout, CLI error, output off the schema) is reported as **partial coverage**, never as
  "nothing found". Its prompt and raw output are in `review/results/<axis>.prompt.md` / `.raw.txt`.
- The findings are a model's opinion: a blocking finding that is wrong is answered in the PR, not obeyed. A
  deviation the project accepts for good goes in `derogations.yaml`, with its reason.
- **Baseline**: a model's findings vary between runs, so a baseline dismisses nothing; it compares runs while tuning
  the prompts. `BASELINE=1` saves the run as `review/results/baseline-<engine>.json`; the next runs print the new /
  still there / gone findings, identified by axis, file and rule (the wording changes, these do not).

## Engines

| Engine | Command | Notes |
|--------|---------|-------|
| `claude` | `claude -p --model sonnet --output-format json --json-schema … --tools Read,Grep,Glob --permission-mode dontAsk --no-session-persistence` | the prompt on stdin; reads `structured_output`, reports `total_cost_usd`. Claude Code also loads `CLAUDE.md` (hence AGENTS.md a second time) |
| `codex` | `codex exec --sandbox read-only --output-schema <file> --output-last-message <file> -` | the prompt on stdin; reads the final message as JSON. Not yet run on this project |

Adding an engine is a function in `engines.py` that takes the prompt and the schema and returns the structured
output, read-only.
