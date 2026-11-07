---
label: Naming and design patterns
rules: [rule-8, rule-9, rule-10]
docs: []
---
# Your axis: naming and design patterns

Check that:

- Names of modules, classes, functions, attributes and variables are explicit, consistent with their real role, in
  English (rule 8) and follow PEP 8 and the conventions already used in the codebase and in Home Assistant's own
  integrations (rule 9).
- Quantities carry their unit in the name: `_kwh`, `_w`, `_l`, `_c`, `_pct`, `_s`… (rule 10).
- The design patterns used are applied in a case suited to their original intent; propose a better suited one when
  a pattern is misused or oversized.
- The abstractions introduced are justified by a real need, not premature.
- Names do not lie about what the code does: a property with a side effect, an `is_*` that does not return a bool,
  a too generic name hiding a blurred responsibility.
- Python introspection is not used to work around the design (`getattr`/`setattr` with computed names, `__dict__`).
