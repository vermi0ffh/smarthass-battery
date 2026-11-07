# AGENTS.md

Guidance for anyone — human or coding agent (Claude Code, Codex, …) — changing this repository. This file is the
entry point: it holds **every rule to respect**; the detailed documentation lives in [`doc/`](doc/).
`CLAUDE.md` only points here.

## Overview

**Smart Hass - Battery** is a **Home Assistant custom integration** (installed with HACS) that estimates the energy
really stored in a home battery from the measures Home Assistant already has: the state of charge its BMS reports,
the battery's DC power or energy meters, its cells' voltages. A BMS's state of charge is often wrong by a few kWh
in the middle of the range (it runs ahead while charging, lags while discharging, holds on plateaus): the
integration counts the energy that flows in and out since the last physical landmark — the battery full (a cell at
its full voltage) or empty (the state of charge crossing the empty threshold) — and learns the battery's round-trip
efficiency and usable energy on each cycle. It exposes the result as entities: stored energy, room to full, a
corrected state of charge, the learned parameters.

It **reads and estimates only**: it never drives the inverter or the battery. What drives them (an automation, an
energy planner such as Smart Hass - Energy Optimizer, a charge regulator) only reads its entities.

## Repository layout

| Path | Content |
|------|---------|
| `custom_components/smart_hass_battery/` | The integration: `model/` (the battery model, pure Python: `meter.py`). The Home Assistant glue (tracker, platforms, config flow) comes in a later version |
| `tests/` | `tests/model/` (pure model, no Home Assistant; `tests/model/data/` holds recorded histories), `tests/integration/` (with `pytest-homeassistant-custom-component`) |
| `review/` | AI code review (`make review`): axis prompts, derogations, engines |
| `doc/` | Documentation: `doc/agents/` (technical, for agents, English), `doc/en/` and `doc/fr/` (for humans) |

## Documentation index

| File | Read it when you touch… |
|------|-------------------------|
| [doc/agents/architecture.md](doc/agents/architecture.md) | The layers, the entities and their contract, persistence |
| [doc/agents/model.md](doc/agents/model.md) | The battery model: energy counting, landmarks, learning, meters, parameters and the measures behind them |
| [doc/agents/testing.md](doc/agents/testing.md) | Test families, fixtures, recorded histories, what each test file covers |
| [doc/agents/review.md](doc/agents/review.md) | `make review`: axes, rule identifiers, derogations, engines |
| [doc/en/contributing.md](doc/en/contributing.md) ([fr](doc/fr/contributing.md)) | Workflow, commit messages, pull requests, changed tests, backward compatibility, releases |

## Commands

```bash
make install     # dev venv (Python 3.14, the version of Home Assistant: `uv python install 3.14`)
make test        # every test — before every commit
make test-model  # the model's tests only (fast, no Home Assistant)
make lint        # ruff check + format check (make lint-fix / make format to fix)
make typecheck   # mypy on the integration
make review      # AI review of the changed Python files, one agent per axis (before a PR)
```

## Rules

These rules are mandatory. A change that must break one of them says so explicitly in its commit message and pull
request, with the reason. A rule's number is its identifier in `make review` (`rule-<n>`, see
[doc/agents/review.md](doc/agents/review.md)): renumbering the rules updates the review axes and derogations.

### Architecture

1. **The model is pure Python**: `model/` imports only the standard library; no Home Assistant, no I/O, no reading
   the clock (every update receives its time). The physics lives there, testable without Home Assistant.
2. **Home Assistant stays in the glue**: `tracker.py` subscribes to the configured entities' state changes, converts
   their states (`unavailable`, `unknown`, units) into model inputs and persists the model's state; the platforms
   only expose the tracker's values. No business rule in the platforms or the config flow.
3. **Read only**: the integration never calls a service that acts on a device or on another integration's entity.
   Its own services (e.g. `mark_full`) only change its own estimate.
4. **Asynchronous and non-blocking**: nothing blocks the event loop (no blocking I/O, no `time.sleep`, no
   synchronous HTTP). An external service, if one is ever used, goes through Home Assistant's `aiohttp` session with
   a timeout; when it fails, the integration keeps working on a fallback and retries later.
5. **Independent of the other Smart Hass projects**: it never imports Smart Hass - Energy Optimizer (nor the
   reverse); they talk only through Home Assistant entities.
6. **Installation data is configuration, not code**: entities, volume, set point, powers, initial values come from
   the config flow (options), with a documented default; nothing about one house is hard-coded.

### Code

7. **Python 3.14** (the version Home Assistant requires), the Home Assistant version pinned by
   `pytest-homeassistant-custom-component` in `requirements_test.txt`. `make lint` (ruff check and `ruff format
   --check`, 120 columns) and `make typecheck` (mypy on `custom_components/`) pass with no new suppression. Type
   hints on every new function.
8. **Language**: identifiers, comments, docstrings, log messages and commit messages in **English**. User-facing
   texts go through `strings.json` and `translations/` (`en.json`, `fr.json`), kept in sync; agent documentation in
   English, human documentation in both English (`doc/en/`) and French (`doc/fr/`).
9. **Match the surrounding code**: its naming, idiom and comment density. Comments explain *why*; a value taken from
   an observation cites it (date and measure, e.g. "round trip 0.964 over 8 daily cycles, 2026-10-29 to 11-06").
10. **Units and unknowns**: units in names (`_kwh`, `_w`, `_v`, `_pct`, `_s`); `None` means unknown — never 0
    for a missing measure. An unavailable input pauses what depends on it; it is never read as a zero.
11. **Time**: timezone-aware datetimes only (`homeassistant.util.dt`); durations from the timestamps of the events,
    not from the wall clock at processing time; the model never reads the clock (rule 1).
12. **Cumulative meters** (the battery's energy in and out) are read only through the model's meter function: daily
    or spurious resets, jitter and impossible jumps are handled there, once.

### Tests

13. **Every behavior change comes with a test**; a bug fix comes with a test that fails without the fix.
14. **Right family**: `tests/model/` = the pure model, no Home Assistant; anything that needs Home Assistant (config
    flow, entities, events, restore, services) goes in `tests/integration/` (see
    [doc/agents/testing.md](doc/agents/testing.md)). A model change validated on a real house replays a recorded
    history (states exported from Home Assistant), anonymized, in `tests/model/data/`.
15. **`make lint`, `make typecheck` and `make test` pass before every commit.**
16. **A changed or removed test is justified**: never weaken an assertion, widen a tolerance, skip or delete a test
    just to make it pass. Changing an existing test's expectation requires, in the commit message and the PR, why the
    old expectation was wrong or why the behavior change is wanted, with figures for a model change.
17. **Tests check observable behavior, without introspection**: no access to a private member, no monkeypatching of
    a private function, no bypassing of a constructor. Test the model through its public API and the integration
    through Home Assistant (states, services, config entries).

### Documentation

18. **Documentation changes in the same commit as the behavior**: a new or changed option, entity or service → the
    user documentation (`doc/en/` and `doc/fr/`) and the translations; a model change → `doc/agents/model.md`; a new
    rule → this file and, if it concerns contributors, `doc/{en,fr}/contributing.md`.
19. Documentation describes the **current** behavior; history belongs to git. A dated measure is kept only as the
    justification of a value or a choice.

### Compatibility

20. **Backward compatibility (no break)**: what worked before a change keeps working after it.
    - Config entries: a changed schema bumps the entry's version and migrates the old entries
      (`async_migrate_entry`); a new option has a default that keeps the old behavior.
    - Stored state (`helpers.storage.Store`): a changed format bumps its version and reads the old one; a restart
      never loses the estimate or the calibration.
    - Entities are a contract: `unique_id`, meaning, unit, `device_class` and `state_class` of an entity stay; a
      change is a breaking change, announced in the changelog with what to do.
    - The minimum Home Assistant version (`hacs.json`) is raised only on purpose, in its own commit.

### Git, privacy and security

21. **Never commit secrets or personal files**: tokens, Home Assistant exports that are not anonymized.
22. **No personal data in the repository**: no e-mail address, no token, no personal URL, no exact location; the
    recorded histories of the tests keep only the measures (entity ids renamed, dates kept).
23. **One topic per commit**, message in English `Summary` (no prefix: the author is the commit's), body explaining why and
    what, with the measured facts — see [doc/en/contributing.md](doc/en/contributing.md#commit-messages).
    **A refactoring commit does not touch the tests**: unchanged tests passing are what proves the behavior is kept.
24. **Agents**: commit only when asked, push only when asked, never change the git configuration, never rewrite
    published history, no tool attribution in commits or pull requests (no `Co-Authored-By:` for the agent, no
    "Generated with …", no session link).

### Estimates that drive decisions

25. **A change to the estimate is validated before it ships**: the stored energy, the room to full and the corrected
    state of charge drive the battery through the user's automations, charge regulator or planner. A change to the
    model or its calibration is replayed on at least one recorded history covering a full cycle (a full charge and a
    discharge to the empty threshold) and compared with the previous version, figures in the PR; a new
    self-calibration arrives with a switch (an option) until validated.
