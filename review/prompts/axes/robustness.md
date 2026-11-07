---
label: Robustness and error handling
rules: [rule-2, rule-4, rule-10, rule-12]
docs: [doc/agents/architecture.md, doc/agents/model.md]
---
# Your axis: robustness and error handling

The integration runs unattended inside Home Assistant: a failure must not crash Home Assistant's event loop, must
not turn into a wrong estimate silently, and must be visible in the log.

Check that:

- Edge cases are handled: an entity `unavailable` or `unknown`, removed, in another unit, a non-numeric state; a
  restart in the middle of a heating; a meter reset (daily) or a spurious jump; persisted data from an older version
  or truncated; an external service unreachable, slow or answering garbage.
- An unknown value stays unknown: `None` and never `0` for a missing measure, an unavailable input pauses what
  depends on it (rule 10); cumulative meters go through the model's meter function (rule 12).
- Nothing blocks the event loop (rule 4): no blocking I/O, no synchronous HTTP, a timeout on every external call.
- Exceptions are not silently swallowed, nor turned into a too generic one that loses the context.
- Listeners, timers and subscriptions are removed when the entry is unloaded; the state is saved on unload.
