---
label: Readability and complexity
rules: [rule-9]
docs: []
---
# Your axis: readability and complexity

Check that:

- The diff introduces no dead, duplicated or useless code: unused variables or parameters, unreachable branches,
  logic that already exists elsewhere in the repository or in Home Assistant's helpers and should have been reused.
- The functions changed or added are not too long or too complex and could not be simplified or split.
- The code is understandable without excessive effort: clear names, simple control flow, no hidden side effect or
  non-obvious temporal coupling, no dict passed around instead of a dataclass.
- The comments added carry useful information (the *why*, the measure a value comes from — rule 9) and do not
  restate the code.
- There is no over-engineering: options or parameters added for a hypothetical need nobody asked for.
