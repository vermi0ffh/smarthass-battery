---
label: Security and personal data
rules: [rule-21, rule-22]
docs: []
derogable: false
---
# Your axis: security and personal data

This axis cannot be waived: its findings are never dismissed by a derogation.

Check that:

- No sensitive data (token, password, API key, credential) is hard-coded in the code or the tests, and no secret or
  personal file is added (rule 21).
- No personal data is added (rule 22): an exact location, an e-mail address, a personal URL or host name, a person's
  name, real entity ids or an unanonymized Home Assistant export where placeholders would do.
- Inputs coming from outside (Home Assistant states and attributes, service calls, external APIs, persisted data)
  are validated before use.
- Dangerous functions are absent: `eval`, `exec`, `pickle` on external data, `yaml.load` without a safe loader.
- Logs never contain a token or sensitive personal data.
- Calls to external services do not introduce an obvious attack surface (unvalidated URL, TLS verification disabled,
  unbounded download).
