"""WSL-only presentation contracts. No reads, scans, commands or authority."""
from dataclasses import dataclass
import platform


def is_wsl():
    return platform.system() == "Linux" and "microsoft" in platform.release().lower()


@dataclass(frozen=True)
class ReadinessItem:
    key: str
    title: str
    state: str
    detail: str
    action: str


def reviewed_udm_setup(guide):
    """Match only current non-secret form values to a reviewed session handoff.

    Do not call guide.config(): it probes paths. Certificate trust, files and
    credentials are never inspected here. Closing/editing the guide removes this
    observation; a saved file elsewhere is not discovered or implicitly loaded.
    """
    if guide is None or guide.window is None or "collect" not in guide.saved:
        return False
    from .udm_setup import UdmSetup
    try:
        setup, _ = guide.saved["collect"]
        current = UdmSetup(guide.fields["origin"].get().strip(), "collect",
            guide.fields["inventory_output"].get(), guide.fields["ca"].get() or None,
            guide.fields["site"].get().strip())
        return type(setup) is UdmSetup and current == setup
    except (ValueError, TypeError, KeyError):
        return False


def readiness_items(sources, *, udm_reviewed=False):
    """Interpret existing SourceHealth values; no aggregate ready/enforced claim."""
    result = [ReadinessItem("runtime", "WSL Control Center", "Recorded",
        "This checklist is running in a Linux kernel identified as WSL. This observes the local UI runtime, not a canonical service, collector or governed deployment.", "diagnostics")]
    for source in sources:
        core = source.key in {"Governance", "Evidence"}
        if not source.selected:
            state = "Needs setup" if core else "Optional"
        elif source.problem:
            state = "Needs attention"
        elif not source.cached or source.read is None:
            state = "Unknown"
        elif not core and source.issues:
            state = "Unknown"  # An accepted file with no collection result is not connector readiness.
        elif source.freshness in {"Stale", "Clock mismatch"}:
            state = "Needs attention"
        else:
            state = "Recorded"
        note = ("Core observation for this checklist. " if core else "Optional connector; it is not required to open or use Control Center. ")
        note += f"Local read: {source.read_status}. Source time: {source.freshness}.\n"
        if source.key == "Governance":
            note += "Governance metadata has no export timestamp: freshness stays Unknown even when this local setup step is Recorded.\n"
        note += "\nCoverage\n" + source.coverage + "\n\nStill Unknown\n" + source.unknowns
        if source.issues:
            note += "\n\nReported checks / read issues\n" + "\n".join(source.issues)
        note += "\n\nNext step\n" + source.next_step
        action = source.key.lower() if core else "connections"
        result.append(ReadinessItem(source.key, source.key + (" export" if core else " · optional"), state, note, action))
    udm = next(source for source in sources if source.key == "UniFi UDM")
    tls_report = any("TLS validation failed" in issue for issue in udm.issues)
    result.extend((
        ReadinessItem("udm_trust", "UDM certificate trust · optional", "Needs attention" if tls_report else "Unknown",
            ("The selected source reports TLS validation failure. Its source time is " + udm.freshness + ".\n\n" if tls_report else "No independent certificate-trust observation is available in these exports.\n\n") +
            "A public CA filename, saved setup or successful source-reported read does not establish independently verified trust here. "
            "Use Guided UDM setup to review an independently trusted public certificate and IP-address matching. "
            "Certificate verification stays enabled. Do not bypass TLS or provide private keys/API keys to this window.", "udm"),
        ReadinessItem("udm_site", "UDM site UUID · optional", "Recorded" if udm_reviewed else "Unknown",
            ("A canonical site UUID is supplied in a reviewed collect setup that matches the current guide fields. "
             "This is session-local configuration, not proof of discovery, site access or current file availability. "
             "Editing/closing the guide removes this observation.\n\n" if udm_reviewed else
             "No matching reviewed collect setup is available in this session. An inventory export does not contain a site UUID; it cannot fill this gap.\n\n") +
            "Open Guided UDM setup. After trusted site discovery, explicitly select the intended site UUID and review/save the non-secret collect handoff. "
            "No setup file, certificate, credential or provider is read by this checklist.", "udm"),
        ReadinessItem("assurance", "Governance assurance and consequences", "Unknown",
            "Setup observations are separate from enforcement verification. Current deployed policy/grants, exact approval/permit bindings, "
            "correlated execution and established external consequences are not provided by these exports. "
            "Decision Explorer inspects individual redacted references; it cannot reconstruct a complete action chain. "
            "Missing evidence never authorizes retry. No checklist action approves, executes, revokes or resolves anything.", "decisions"),
    ))
    return tuple(result)
