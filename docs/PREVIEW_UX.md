# Preview UX: Simplicity by Default

Keep Pulpo as simple as possible. Add complexity only when a necessary step
protects correctness, authority boundaries, or a demonstrated user need.

For Preview, apply this philosophy to installation, diagnostics, demos, and
future documentation:

- Give the user one clear next step and explain the expected result.
- Reuse the existing package, setup self-check, and canonical control paths.
- Keep calibration and advanced tuning optional.
- Explain failures and proof limits in plain language.
- Never simplify away governance checks or add another router, executor,
  ledger, or authority service for convenience.

Ubuntu is the first Preview UX target. Start with a virtual environment,
a bounded doctor check, and the existing synthetic demo. Add packaging or
automation only when this path demonstrates a need for it.

Status: **Proposed** Preview design guidance; this does not change canonical
Pulpo policy or claim production readiness.
