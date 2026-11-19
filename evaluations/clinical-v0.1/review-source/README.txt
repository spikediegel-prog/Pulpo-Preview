PULPO CLINICAL EVALUATION KIT v0.1
Review candidate — synthetic lab only — 25 October 2026

Start with Clinical-Control-Center.html in evidence/qualified-wsl-run/canonical/.
It is an offline, readable report of an actual synthetic evaluation. Open the
Preview report beside it to compare the two pinned implementations.

For the existing native Pulpo Control Center with a clinical observer page:
  python3 control_center_clinical.py --report evidence/qualified-wsl-run/canonical/report.json

For a new evaluation (from this directory, Python 3.11+):
  python3 evaluate.py --engine canonical --out runs/central-clinics-01
  python3 evaluate.py --engine preview --out runs/preview-01
For all bounded tests:
  python3 validate_all.py --out runs/validation-01
Each destination must be new. No pip install, network connection, service,
elevated account or installed Pulpo update is required. Ubuntu desktop needs
working Tkinter for the native UI; a CLI-only guest can use the HTML reports.

WHAT IS INCLUDED
- The unchanged canonical and Preview Python packages at the exact source pins
  in SOURCE-PINS.json, with selected regression tooling and upstream attribution.
- The existing native Control Center package plus an external clinical observer
  extension. Its visual theme, navigation, diagnostics and observation boundaries
  are reused. The original UI sources are unchanged.
- Strict synthetic topology configuration; ESXi, Hyper-V and WSL examples.
- Simulated WSUS-style governance: propose a site/ring/update window, verify a
  fixture approval, activate the canonical directive, issue and consume an exact
  intent permit, observe a fixture patch state, revoke, expire and test negatives.
- Exported canonical audit, scenario results, configuration, source provenance,
  checksums, native UI construction evidence and the test logs.
- Optional generated FHIR-like Bundle JSON and DICOM metadata JSON simulations.
  These are not servers, EHR connectors, DICOM files, image readers or PACS tests.

READ NEXT
SETUP-VM-WSL.txt       Disposable ESXi / Hyper-V / WSL setup and operator workflow
EVALUATION-GUIDE.txt   Configuration, scenarios, acceptance and evidence handling
IMPLEMENTATION.txt    Code findings, implemented/proposed boundaries and limits
TEST-REPORT.txt       Exact test results and environment limitations
REVIEW-RECORD.txt     Authority/change record and adversarial transformation review

This kit never connects to Athena, Phreesia, Carestream, PACS, Microsoft 365 or
WSUS. It generates synthetic identifiers; it accepts no clinical uploads,
production endpoints or credentials. Its test runner is not an agent service.
The fixture signer uses upstream publicly known test material and cannot stand
in for independent human approval. No real signing credential is included.

No production repository, installed runtime, VM configuration or provider state
was changed. No branch was pushed, PR merged, release published or deployment
performed. Review this package before any further integration.

The package checksum manifest is MANIFEST-SHA256.json. verify_package.py checks
it with Python's standard library. A digest is not a signature or provenance
attestation; distribute the ZIP's SHA256 through your own trusted review channel.
