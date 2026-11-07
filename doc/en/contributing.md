# Contributing

*[Version française](../fr/contributing.md)*

How to propose a change, for a human or a coding agent. The rules themselves are in [AGENTS.md](../../AGENTS.md#rules);
this page describes the workflow. Contributions are made under the project's license, Apache 2.0
([LICENSE](../../LICENSE)).

## Workflow

1. **Understand before changing**: read `AGENTS.md` and the `doc/agents/` page of the area you touch. For a behavior
   seen at home, start from the data (Home Assistant history of the relay, power, meters and of the integration's
   entities) and state the observed problem with its figures.
2. **Branch** from `main` (`git switch -c <topic>`), one topic per branch.
3. **Write the test first** when fixing a bug (it must fail without the fix), then the change.
4. **Run** `make test-model` while working, then `make lint`, `make typecheck` and `make test` before committing.
5. **Update the documentation** in the same commit: `doc/agents/` for the technical description, `doc/en/` and
   `doc/fr/` and the translations for what users read, both languages together.
6. **Review** with `make review` (AI review of the changed Python files, committed or not, see
   [doc/agents/review.md](../agents/review.md)): fix the blocking findings, weigh the others.
7. **Commit** (see below) and open a pull request (see below). The CI runs lint, typecheck, all tests, hassfest
   (Home Assistant's validator) and the HACS validation.

## Commit messages

In English:

```
Short summary, no final period

Why: the observed problem, with the measures (date, values, entity).
What: what changes, the options and entities involved.
Measured effect: the estimate before → after on a recorded history, when applicable.
```

- No prefix (no initials, no tag): the author is the commit's.
- Body lines wrapped around 100 columns.
- No tool attribution: coding agents add no trailer or line naming their tool to commits or pull requests (no
  `Co-Authored-By:` for the agent, no "Generated with …", no session link). A person who co-wrote the change is
  credited with `Co-authored-by:`.
- **One topic per commit.** A refactoring and a behavior change are two commits.
- **A refactoring commit does not touch the tests**: the unchanged tests passing prove the behavior is kept.

## Pull requests

Title in English, `[type] Short summary, no final period`, where `type` says what the pull request contains:

| Type | Content |
|------|---------|
| `feature` | A new behavior or capability (an entity, an attribute, an option, a learned value…) |
| `bugfix` | A fix of a wrong behavior, with the test that fails without it |
| `hotfix` | An urgent fix of a problem seen in production, to merge and deploy right away |
| `maintenance` | No behavior change for the user: refactoring, tests, documentation, CI, tooling, dependencies |
| `perf` | A faster or lighter computation with the same result, with the measure before → after |
| `release` | A version of the integration: `version`, `CHANGELOG.md` and the `vX.Y.Z` tag (see below) |
| `revert` | The cancellation of a merged pull request, with why it is withdrawn |

A pull request mixing several types is split; its commits keep the commit message form above.

Description:

```markdown
## Problem
What was observed (data, dates, figures) or what is missing.

## Change
What changes and why this approach.

## Compatibility
New or changed options and their default; entities added or changed; stored state whose format changes. State that
an installation configured before this PR works unchanged after it (or, for a deliberate change, what the user must
do).

## Validation
- `make lint`, `make typecheck`, `make test`: OK
- New tests: …
- Estimate: replayed on … (history, dates): level and energy to full before → after

## Changed tests
For each existing test whose expectation changed or which was removed: see below. "None" otherwise.
```

## When an existing test changes

A test that breaks is first assumed to have found a regression. Changing it is allowed only when the old expectation
was wrong or the behavior change is intended. For each such test, the PR (and the commit body) states:

- **Test**: `path::test_name`.
- **Before → after**: the expected value or behavior, old and new.
- **Why**: why the old expectation no longer holds, with figures for a model change.
- **What still guarantees the behavior**: the assertion kept or the new test covering it.

Forbidden without that justification: widening a tolerance, weakening or removing an assertion, adding `skip` /
`xfail`, deleting a test.

## Changes to the estimate

The stored energy, the room to full and the corrected state of charge drive batteries through the users' automations
and energy planners (rule 25 of `AGENTS.md`):

1. A change to the model or its calibration is replayed on at least one recorded history covering a full cycle
   (a full charge and a discharge to the empty threshold), anonymized in `tests/model/data/`.
2. The PR compares the estimate before → after on it, with figures.
3. A new calibration arrives behind an option until it is validated on real installations.

## Backward compatibility

Nothing that worked before a change may break after it:

- **Config entries**: a changed schema bumps the entry's version and migrates the old entries; a new option has a
  default keeping the old behavior.
- **Stored state**: a changed format bumps its version and the previous one stays readable; a restart never loses the
  estimate or the calibration.
- **Entities**: `unique_id`, meaning, unit, `device_class` and `state_class` stay; a change is announced in the
  changelog as a breaking change, with what to do.

## Releasing

Versions follow semantic versioning (`0.x` until the options and entities are stable). To release `X.Y.Z`: bump
`version` in `custom_components/smart_hass_battery/manifest.json` and `pyproject.toml`, describe the version in
`CHANGELOG.md`, then tag `vX.Y.Z` and publish a GitHub release (HACS offers the releases).

## Review checklist

- [ ] Rules of `AGENTS.md` respected (pure model, Home Assistant in the tracker, read only, configuration not code,
      units, time)
- [ ] Code, comments, logs and commit messages in English; translations in `en.json` and `fr.json`
- [ ] Tests added in the right family; a bug fix has a test that fails without it
- [ ] Changed tests justified; refactoring commits do not touch tests
- [ ] Previous config entries, stored state and entities still work
- [ ] Estimate changes replayed on a recorded history
- [ ] Documentation updated (`AGENTS.md`, `doc/agents/`, `doc/en/` and `doc/fr/`, `CHANGELOG.md`); a quality scale rule
      now met is marked `done` in `quality_scale.yaml`
- [ ] No secret, token or personal data
