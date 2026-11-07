---
label: Quality and relevance of the tests
rules: [rule-13, rule-14, rule-16, rule-17, rule-23]
docs: [doc/agents/testing.md]
---
# Your axis: quality and relevance of the tests

Check that:

- The tests added or changed are relevant: they check a real and useful behavior, and are neither redundant with
  each other nor with existing tests.
- No test is missing for a significant behavior introduced or changed by the diff — the nominal case **and** the
  edge cases (rule 13). A bug fix comes with a test that fails without the fix.
- Each test is in the right family (rule 14): `tests/model/` is the pure model, no Home Assistant; config flow,
  entities, events, restore and services are in `tests/integration/`.
- The tests use no introspection (rule 17): no access to a private member, no monkeypatching of a private function,
  no bypassing of a constructor. Report it as `blocking` and propose a test of the observable behavior.
- A changed or removed existing test is justified in the commit message (rule 16). A commit presented as a
  refactoring does not touch the tests (rule 23).
- The number of tests is proportionate to the complexity and risk of the code.
