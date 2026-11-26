"""Gladiator DNS side-channel gate bypass — local simulation only.

Implements proposal ``gladiator-dns-side-channel-proposal-2026-11-25.md``
sections 3-5 as a test-only fixture. Status: Proposed / Verified (simulation
only).

The invariant under test: an unauthorized client must not gain an
application communication channel merely because DNS infrastructure traffic
is permitted.

What this file is NOT, by design:

* No sockets, no subprocesses, no DNS wire protocol, no DNS library, no
  public resolver, no real network, no real captive portal.
* No encoding step. The probe is one fixed constant,
  ``gladiator-dns-probe-001``. An arbitrary-message encoder is a tunnel
  primitive and is deliberately absent.
* No production code. ``SimulatedGate``, ``MockDnsAuthority`` and
  ``SimulatedClient`` live in this test file only, following the existing
  Gladiator test pattern. They add no router, executor, ledger, memory
  system, audit source, or authority plane, and they mutate no canonical
  Pulpo state.

What a PASS here proves, and what it does not:

* PASS (judgment SURVIVES) proves the *policy logic*: the gate function
  denies an identifier smuggled in a DNS-shaped query.
* It does NOT prove a live gate blocks DNS tunneling. The live verdict
  stays UNKNOWN until the live-transport harness (G5), the enforcement
  point (G1-G4, G6) and, for Tether, Dill's installable gate exist.
  See proposal section 7 (G-DNS2 and the shared gaps).
* Missing evidence is UNKNOWN, never PASS. A broken gate that lets the
  probe reach the mock authority is FAILS, and one test below constructs
  exactly such a gate to prove the judgment can detect failure.
"""
import unittest

# The only probe. A fixed constant, not an encoding step. Never build a
# query name from user data, a secret, or a file in this fixture.
PROBE = "gladiator-dns-probe-001"
PERMITTED_INFRASTRUCTURE_NAME = "resolver.internal"
CANNED_INFRASTRUCTURE_ANSWER = "resolver.internal-answer"
FLOOD_ATTEMPTS = 50


class SimulatedGate:
    """Policy function for a simulated network gate.

    ``authorized`` is the client's authorization state. DNS is permitted
    only for the exact infrastructure name the gate declares; anything
    else, including any name carrying extra labels, is denied and logged.
    The gate inspects the query name, it does not permit by interface
    alone. Every attempt appends a timestamped (sequenced) entry to the
    evidence log.
    """

    def __init__(self, *, authorized=False,
                 permitted_infrastructure_name=PERMITTED_INFRASTRUCTURE_NAME,
                 permit_any_dns=False):
        # permit_any_dns exists only to model a broken gate in the
        # FAIL-detection test. Production policy must never set it.
        self.authorized = authorized
        self.permitted_infrastructure_name = permitted_infrastructure_name
        self.permit_any_dns = permit_any_dns
        self.evidence = []
        self.evidence_intact = True
        self._sequence = 0

    def _log(self, kind, name, outcome, reason):
        self._sequence += 1
        self.evidence.append({
            "sequence": self._sequence,
            "kind": kind,
            "name": name,
            "outcome": outcome,
            "reason": reason,
        })
        return outcome, reason

    def attempt_http(self, destination):
        if not self.authorized:
            return self._log("http", destination, "denied",
                             "unauthorized_http_denied")
        return self._log("http", destination, "allowed", "authorized")

    def attempt_dns(self, query_name):
        if self.permit_any_dns:
            return self._log("dns", query_name, "allowed",
                             "permitted_by_interface_only")
        if query_name == self.permitted_infrastructure_name:
            return self._log("dns", query_name, "allowed",
                             "permitted_infrastructure_name")
        return self._log("dns", query_name, "denied",
                         "dns_name_not_permitted_infrastructure")

    def inspect_dns_answer(self, answer):
        """A DNS answer may carry only the declared infrastructure answer.

        Anything else is application content arriving through DNS.
        """
        if answer == CANNED_INFRASTRUCTURE_ANSWER:
            return self._log("dns_answer", answer, "allowed",
                             "canned_infrastructure_answer")
        return self._log("dns_answer", answer, "denied",
                         "dns_answer_carries_application_content")


class MockDnsAuthority:
    """In-memory mock authority. Not a server: listens on nothing,
    resolves nothing. ``record`` appends the query to a list and returns
    a fixed canned answer.
    """

    def __init__(self):
        self.records = []
        self.available = True

    def record(self, query_name):
        if not self.available:
            raise RuntimeError("mock_dns_authority_unavailable")
        self.records.append(query_name)
        return CANNED_INFRASTRUCTURE_ANSWER


class SimulatedClient:
    """Unauthorized test client. Holds one fixed probe identifier. It
    never holds a secret, a file, or user data.
    """

    def __init__(self, gate, authority):
        self.gate = gate
        self.authority = authority
        self.authorized = False
        self.probe = PROBE

    def attempt_http(self, destination):
        return self.gate.attempt_http(destination)

    def attempt_dns(self, query_name):
        """Submit through the simulated DNS interface, exactly as the
        proposal specifies: the gate decides first; the mock authority
        records only what the gate allowed through.
        """
        outcome, reason = self.gate.attempt_dns(query_name)
        if outcome != "allowed":
            return outcome, reason, None
        answer = self.authority.record(query_name)
        return outcome, reason, answer


def judge(gate, authority):
    """Gladiator judgment for one simulated run.

    SURVIVES: probe never reached the mock authority, no unauthorized
    attempt was allowed, and the evidence is intact.
    FAILS: the probe reached the mock authority, or an unauthorized
    attempt was allowed.
    UNKNOWN: evidence is missing / interrupted, or the mock authority
    was unavailable. Never PASS on missing evidence.
    """
    if not gate.evidence_intact:
        return "UNKNOWN"
    if not authority.available:
        return "UNKNOWN"
    if PROBE in authority.records:
        return "FAILS"
    for entry in gate.evidence:
        if entry["outcome"] == "allowed" and not gate.authorized:
            # The only allowed entry while unauthorized is the exact
            # permitted infrastructure name (and its canned answer).
            if entry["name"] not in (PERMITTED_INFRASTRUCTURE_NAME,
                                     CANNED_INFRASTRUCTURE_ANSWER):
                return "FAILS"
    return "SURVIVES"


class DnsSideChannelTests(unittest.TestCase):
    def setUp(self):
        self.gate = SimulatedGate(authorized=False)
        self.authority = MockDnsAuthority()
        self.client = SimulatedClient(self.gate, self.authority)

    def assert_probe_never_reached_authority(self):
        # The permitted infrastructure name may legitimately reach the
        # mock authority; the probe must never do so.
        self.assertNotIn(PROBE, self.authority.records)

    # Attack A — Baseline
    def test_attack_a_unauthorized_http_denied(self):
        outcome, reason = self.client.attempt_http("https://example.invalid/")
        self.assertEqual(("denied", "unauthorized_http_denied"),
                         (outcome, reason))
        self.assertEqual("SURVIVES", judge(self.gate, self.authority))

    # Attack B — DNS side-channel
    def test_attack_b_dns_probe_denied_and_never_reaches_authority(self):
        outcome, reason, answer = self.client.attempt_dns(PROBE)
        self.assertEqual("denied", outcome)
        self.assertIsNone(answer)
        self.assert_probe_never_reached_authority()
        self.assertEqual("SURVIVES", judge(self.gate, self.authority))

    def test_attack_b_broken_gate_is_detected_as_fail(self):
        # A gate that permits by interface alone must be caught, not
        # passed. This proves the judgment is not a vacuous PASS.
        broken_gate = SimulatedGate(authorized=False, permit_any_dns=True)
        broken_authority = MockDnsAuthority()
        broken_client = SimulatedClient(broken_gate, broken_authority)
        broken_client.attempt_dns(PROBE)
        self.assertIn(PROBE, broken_authority.records)
        self.assertEqual("FAILS", judge(broken_gate, broken_authority))

    # Attack C — Response channel
    def test_attack_c_canned_answer_allowed_payload_answer_denied(self):
        outcome, reason = self.gate.inspect_dns_answer(
            CANNED_INFRASTRUCTURE_ANSWER)
        self.assertEqual("allowed", outcome)
        outcome, reason = self.gate.inspect_dns_answer("payload-answer")
        self.assertEqual(("denied", "dns_answer_carries_application_content"),
                         (outcome, reason))
        self.assertEqual("SURVIVES", judge(self.gate, self.authority))

    def test_attack_c_payload_answer_via_client_path_is_denied(self):
        # Even if the mock authority were asked, the gate must refuse a
        # payload-bearing answer before it reaches the client.
        outcome, _ = self.gate.inspect_dns_answer(PROBE)
        self.assertEqual("denied", outcome)

    # Attack D — Gate enforcement
    def test_attack_d_gate_inspects_name_not_interface(self):
        # Exact permitted name: allowed.
        outcome, _, _ = self.client.attempt_dns(PERMITTED_INFRASTRUCTURE_NAME)
        self.assertEqual("allowed", outcome)
        # Probe as its own name, as a subdomain, as a suffix, and with
        # an extra label: all denied. Permitting by interface alone
        # would allow every one of these.
        for name in (PROBE,
                     PROBE + "." + PERMITTED_INFRASTRUCTURE_NAME,
                     PERMITTED_INFRASTRUCTURE_NAME + "." + PROBE,
                     "extra." + PERMITTED_INFRASTRUCTURE_NAME,
                     ""):
            outcome, _, answer = self.client.attempt_dns(name)
            self.assertEqual("denied", outcome, name)
            self.assertIsNone(answer, name)
        self.assert_probe_never_reached_authority()
        self.assertEqual("SURVIVES", judge(self.gate, self.authority))

    # Attack E — Combined boundary test
    def test_attack_e_blocked_http_and_dns_probe_together(self):
        http_outcome, _ = self.client.attempt_http("https://example.invalid/")
        dns_outcome, _, _ = self.client.attempt_dns(PROBE)
        self.assertEqual("denied", http_outcome)
        self.assertEqual("denied", dns_outcome)
        self.assert_probe_never_reached_authority()
        self.assertEqual("SURVIVES", judge(self.gate, self.authority))

    # Transformations (proposal section 5, adapted — no packets exist)
    def test_transform_invert_infrastructure_dns_allowed_others_denied(self):
        outcome, _, _ = self.client.attempt_dns(PERMITTED_INFRASTRUCTURE_NAME)
        self.assertEqual("allowed", outcome)
        outcome, _, _ = self.client.attempt_dns(PROBE)
        self.assertEqual("denied", outcome)
        self.assertEqual("SURVIVES", judge(self.gate, self.authority))

    def test_transform_starve_repeated_probes_still_denied_not_queued(self):
        for _ in range(3):
            outcome, _, _ = self.client.attempt_dns(PROBE)
            self.assertEqual("denied", outcome)
        self.assert_probe_never_reached_authority()

    def test_transform_flood_repetition_never_succeeds(self):
        for _ in range(FLOOD_ATTEMPTS):
            outcome, _, _ = self.client.attempt_dns(PROBE)
            self.assertEqual("denied", outcome)
        self.assert_probe_never_reached_authority()
        self.assertEqual("SURVIVES", judge(self.gate, self.authority))

    def test_transform_partition_authority_unavailable_is_unknown_not_pass(self):
        self.authority.available = False
        with self.assertRaises(RuntimeError):
            self.authority.record(PERMITTED_INFRASTRUCTURE_NAME)
        self.assertEqual("UNKNOWN", judge(self.gate, self.authority))

    def test_transform_restart_fresh_gate_same_policy_no_bypass(self):
        fresh_gate = SimulatedGate(authorized=False)
        fresh_authority = MockDnsAuthority()
        fresh_client = SimulatedClient(fresh_gate, fresh_authority)
        outcome, _, _ = fresh_client.attempt_dns(PROBE)
        self.assertEqual("denied", outcome)
        self.assertNotIn(PROBE, fresh_authority.records)
        self.assertEqual("SURVIVES", judge(fresh_gate, fresh_authority))

    def test_transform_replay_previously_observed_probe_still_denied(self):
        first, _, _ = self.client.attempt_dns(PROBE)
        second, _, _ = self.client.attempt_dns(PROBE)
        self.assertEqual("denied", first)
        self.assertEqual("denied", second)
        self.assert_probe_never_reached_authority()

    def test_transform_degrade_evidence_is_unknown_never_safe(self):
        self.client.attempt_dns(PROBE)
        self.gate.evidence = []
        self.gate.evidence_intact = False
        self.assertEqual("UNKNOWN", judge(self.gate, self.authority))

    # Acceptance criteria (proposal section 5)
    def test_acceptance_criteria(self):
        # Unauthorized HTTP/HTTPS: denied.
        self.assertEqual("denied", self.client.attempt_http("https://x/")[0])
        # DNS lookup of the exact permitted infrastructure name: allowed.
        self.assertEqual("allowed",
                         self.client.attempt_dns(PERMITTED_INFRASTRUCTURE_NAME)[0])
        # DNS carrying the probe identifier: blocked, logged with reason.
        outcome, reason, _ = self.client.attempt_dns(PROBE)
        self.assertEqual("denied", outcome)
        self.assertTrue(any(e["name"] == PROBE and e["reason"]
                            for e in self.gate.evidence))
        # DNS answer carrying application content: blocked.
        self.assertEqual("denied",
                         self.gate.inspect_dns_answer("payload")[0])
        # Gate restart (fresh instance, same policy): no bypass.
        fresh_gate = SimulatedGate(authorized=False)
        self.assertEqual("denied",
                         fresh_gate.attempt_dns(PROBE)[0])
        # Missing evidence: UNKNOWN.
        fresh_gate.evidence_intact = False
        self.assertEqual("UNKNOWN", judge(fresh_gate, self.authority))
        # Authorized client: expected behavior according to declared
        # policy — HTTP allowed, DNS probe still denied (the probe is
        # not the permitted infrastructure name, authorization does not
        # turn it into one).
        authorized_gate = SimulatedGate(authorized=True)
        authorized_authority = MockDnsAuthority()
        authorized_client = SimulatedClient(authorized_gate,
                                            authorized_authority)
        authorized_client.authorized = True
        self.assertEqual("allowed",
                         authorized_client.attempt_http("https://x/")[0])
        self.assertEqual("denied",
                         authorized_client.attempt_dns(PROBE)[0])

    def test_evidence_log_records_every_attempt_in_order(self):
        self.client.attempt_http("https://example.invalid/")
        self.client.attempt_dns(PROBE)
        self.client.attempt_dns(PERMITTED_INFRASTRUCTURE_NAME)
        self.assertEqual([1, 2, 3],
                         [e["sequence"] for e in self.gate.evidence])
        self.assertEqual(["denied", "denied", "allowed"],
                         [e["outcome"] for e in self.gate.evidence])

    def test_fixture_contains_no_network_or_encoding_primitive(self):
        # Guard the boundary the proposal draws: this file must not
        # grow a tunnel. If a future edit imports one of these, the
        # test fails before the fixture can carry data anywhere.
        # Parse imports with ast, not substring search, so the
        # forbidden names themselves do not trip the check.
        import ast
        import pathlib
        source = pathlib.Path(__file__).read_text()
        imported = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertFalse(
            imported & {"socket", "base64", "dns", "subprocess", "urllib"},
            f"forbidden import in fixture: {sorted(imported)}")


if __name__ == "__main__":
    unittest.main()
