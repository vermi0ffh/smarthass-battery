---
label: Documentation
rules: [rule-8, rule-18, rule-19]
docs: [doc/agents/*.md]
---
# Your axis: documentation

The documentation changes in the same commit as the behavior (rule 18). The other changed files listed in the
context tell you which documentation the change already updates; read them.

Check that:

- A new or changed option, entity or service is documented in `doc/en/README.md` **and** `doc/fr/README.md`, and its
  texts are in `strings.json`, `translations/en.json` and `translations/fr.json` (rule 8).
- A model change is reflected in `doc/agents/model.md`; a new module, entity or persisted field in
  `doc/agents/architecture.md`; a new test file in `doc/agents/testing.md`.
- A new rule is in AGENTS.md and, if it concerns contributors, in `doc/en/contributing.md` and
  `doc/fr/contributing.md`.
- The documentation changed describes the current behavior; history belongs to git, except a dated measure that
  justifies a value (rule 19).
- Docstrings of the changed public functions still match what they do.
