# Ubuntu Preview: install, check, try

This source-install path requires Python 3.11 or newer. Preview follows
[Simplicity by Default](PREVIEW_UX.md). These steps install only the base package;
no provider accounts, signing credentials, services, or optional integrations
are needed.

## 1. Install in a virtual environment

On Ubuntu, install the standard Python tools if they are missing:

```bash
sudo apt update
sudo apt install git python3 python3-venv python3-pip
```

Then install Preview in its own environment (no `sudo pip`):

```bash
git clone --branch preview https://github.com/spikediegel-prog/Pulpo-Preview.git Pulpo-preview
cd Pulpo-preview
python3 --version
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
pulpo doctor
```

Record `git rev-parse HEAD` with feedback. Downloadable tester kits and feedback
forms live in [Pulpo Preview Testers](https://github.com/spikediegel-prog/Pulpo-Preview-Testers).
If Python is older than 3.11, stop and use a supported Python environment.
If creating the environment reports missing `ensurepip`, install
`python3-venv` for the selected Python version and retry. In a new terminal,
return to this checkout and run `source .venv/bin/activate` again.

## 2. Read the doctor result

Expect `Synthetic audit check .... PASS` and `Authority changes ........ NONE`.
Doctor uses the existing setup verifier with conservative settings: a valid
64-row synthetic audit must pass and a tampered stored hash must fail. It
does not load or save tuning profiles, calibrate, inspect live governance
state, start services, contact an authority, or request a permit. Normal Python
import caching may create `__pycache__` files.

`pulpo doctor --json` prints a report to standard output for troubleshooting.
Exit status 0 means the self-check passed; 1 means verification failed. Stop on
failure and share the report and source SHA. A pass is evidence only for this
synthetic check, not production readiness or deployed authority.

## 3. Try the existing guided demo

From the source checkout, with the virtual environment active:

```bash
python scripts/demo_orchestrator.py
```

The default output explains each checked result in plain language. To print
the machine-readable result for troubleshooting:

```bash
python scripts/demo_orchestrator.py --json
```

Read that JSON result in this order:

1. `target_mismatch_denied` is `target_hash_mismatch`: changed target identity
   stops before the demo authority is polled.
2. `first_permit_consume` is `true` and `replay_permit_consume` is `false`:
   the exact authorized capability is one-use.
3. `revoked_preissued_directive_permit` is `false`: revocation blocks use.
4. `audit_valid` is `true`: the in-memory demo audit verifies.

The existing demo uses test-only HMAC authority and an in-memory kernel. It
exercises synthetic governance transitions through the existing orchestrator;
it does not deploy anything or prove independent human authority, protected
storage, or external containment. The demo depends on checkout-only test
fixtures and is not shipped as an installed package command.
If a boundary check fails, the demo exits with status 1 and reports the failure
instead of printing a success summary. Checks remain active under `python -O`.

Optional later: `pulpo setup` performs bounded calibration and saves a local
performance profile. It is not required to try doctor or the demo.
Use `deactivate` when finished.
