"""Bounded digital-commerce contracts subordinate to Pulpo's kernel.

This module does not implement a registrar adapter, credential store, payment
rail, approval service, or second audit ledger.  It binds one exact domain
purchase object to the existing GovernanceKernel intent and permit path, then
keeps payment, delivery, acceptance, and value evidence distinct.
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import TYPE_CHECKING, Any, Callable, Protocol

from .custody import CustodyViolation
from .kernel import GovernanceKernel, Intent

if TYPE_CHECKING:
    from .custody_domain import GovernedDomainAttempt, GovernedDomainAttemptCoordinator


PILOT_PURCHASE_CEILING_CENTS = 3_000


# Identity the live commerce path uses when it claims a custody attempt and
# when it records its own first-party observation of the provider result.
# This is the trusted in-process executor, not an independent observer: a
# live-path reconciliation records what the provider synchronously returned
# to this executor. It must never be mistaken for the independent
# observation IndependentDomainReconciler requires.
LIVE_CUSTODY_EXECUTOR_ID = "pulpo.commerce.live"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _hash(value: Any) -> str:
    return sha256(_canonical(value)).hexdigest()


class CommerceViolation(ValueError):
    """A purchase object or state transition violated the commerce contract."""


def _require_sha256(value: str, field: str) -> None:
    if len(value) != 64 or value != value.lower() or any(character not in "0123456789abcdef" for character in value):
        raise CommerceViolation(f"{field} must be a lowercase SHA-256 digest")


@dataclass(frozen=True)
class DomainPurchaseRequest:
    request_id: str
    principal: str
    acceptable_domains: tuple[str, ...]
    max_purchase_cents: int
    max_renewal_cents: int
    approved_registrar: str
    owner_ref: str
    privacy_required: bool
    prohibited_upsells: tuple[str, ...]
    expires_at_ns: int
    auto_renew_enabled: bool = False

    def __post_init__(self) -> None:
        if not self.request_id or not self.principal or not self.acceptable_domains:
            raise CommerceViolation("request identity, principal, and domains are required")
        if len(set(self.acceptable_domains)) != len(self.acceptable_domains):
            raise CommerceViolation("acceptable domains must be unique")
        if any(not item or item != item.lower() for item in self.acceptable_domains):
            raise CommerceViolation("acceptable domains must be normalized lowercase names")
        if not 0 <= self.max_purchase_cents <= PILOT_PURCHASE_CEILING_CENTS:
            raise CommerceViolation("purchase ceiling exceeds the $30 pilot boundary")
        if self.max_renewal_cents < 0:
            raise CommerceViolation("renewal ceiling must be non-negative")
        if not self.approved_registrar or self.approved_registrar != self.approved_registrar.lower():
            raise CommerceViolation("approved registrar must be normalized")
        if not self.owner_ref.startswith("owner://"):
            raise CommerceViolation("owner must be an opaque owner reference")
        if len(set(self.prohibited_upsells)) != len(self.prohibited_upsells):
            raise CommerceViolation("prohibited upsells must be unique")
        if any(not item or item != item.lower() for item in self.prohibited_upsells):
            raise CommerceViolation("prohibited upsells must be normalized")
        if self.expires_at_ns <= 0:
            raise CommerceViolation("request expiration is required")
        if type(self.auto_renew_enabled) is not bool:
            raise CommerceViolation("auto_renew_enabled must be boolean")

    @property
    def request_hash(self) -> str:
        return _hash(asdict(self))


@dataclass(frozen=True)
class DomainQuote:
    quote_id: str
    domain: str
    registrar: str
    purchase_price_cents: int
    renewal_price_cents: int
    owner_ref: str
    privacy_enabled: bool
    upsells: tuple[str, ...]
    expires_at_ns: int

    def __post_init__(self) -> None:
        if not self.quote_id or not self.domain or not self.registrar:
            raise CommerceViolation("quote identity, domain, and registrar are required")
        if self.domain != self.domain.lower() or self.registrar != self.registrar.lower():
            raise CommerceViolation("quote domain and registrar must be normalized")
        if self.purchase_price_cents < 0 or self.renewal_price_cents < 0:
            raise CommerceViolation("quote prices must be non-negative")
        if not self.owner_ref.startswith("owner://"):
            raise CommerceViolation("quote owner must be an opaque owner reference")
        if len(set(self.upsells)) != len(self.upsells):
            raise CommerceViolation("quote upsells must be unique")
        if any(not item or item != item.lower() for item in self.upsells):
            raise CommerceViolation("quote upsells must be normalized")
        if self.expires_at_ns <= 0:
            raise CommerceViolation("quote expiration is required")

    @property
    def quote_hash(self) -> str:
        return _hash(asdict(self))


@dataclass(frozen=True)
class DomainPurchaseOrder:
    request_id: str
    request_hash: str
    quote_id: str
    quote_hash: str
    principal: str
    domain: str
    registrar: str
    purchase_price_cents: int
    renewal_price_cents: int
    owner_ref: str
    privacy_required: bool
    prohibited_upsells: tuple[str, ...]
    credential_ref: str
    expires_at_ns: int
    auto_renew_enabled: bool = False

    def __post_init__(self) -> None:
        if not self.request_id or not self.quote_id or not self.principal:
            raise CommerceViolation("order identity and principal are required")
        _require_sha256(self.request_hash, "request_hash")
        _require_sha256(self.quote_hash, "quote_hash")
        if not self.domain or not self.registrar:
            raise CommerceViolation("order domain and registrar are required")
        if self.domain != self.domain.lower() or self.registrar != self.registrar.lower():
            raise CommerceViolation("order domain and registrar must be normalized")
        if not 0 <= self.purchase_price_cents <= PILOT_PURCHASE_CEILING_CENTS:
            raise CommerceViolation("order exceeds the $30 pilot boundary")
        if self.renewal_price_cents < 0:
            raise CommerceViolation("order renewal must be non-negative")
        if not self.owner_ref.startswith("owner://") or self.owner_ref == "owner://":
            raise CommerceViolation("order owner must be an opaque owner reference")
        if len(set(self.prohibited_upsells)) != len(self.prohibited_upsells):
            raise CommerceViolation("order prohibited upsells must be unique")
        if any(not item or item != item.lower() for item in self.prohibited_upsells):
            raise CommerceViolation("order prohibited upsells must be normalized")
        if not self.credential_ref.startswith("credential://") or self.credential_ref == "credential://":
            raise CommerceViolation("credential must be an opaque credential reference")
        if self.expires_at_ns <= 0:
            raise CommerceViolation("order expiration is required")
        if type(self.auto_renew_enabled) is not bool:
            raise CommerceViolation("order auto_renew_enabled must be boolean")

    @property
    def order_hash(self) -> str:
        return _hash(asdict(self))


@dataclass(frozen=True)
class QuoteAssessment:
    outcome: str
    reason: str
    request_id: str
    quote_id: str
    assessment_hash: str
    order: DomainPurchaseOrder | None = None


def assess_quote(
    request: DomainPurchaseRequest,
    quote: DomainQuote,
    *,
    credential_ref: str,
    now_ns: int,
) -> QuoteAssessment:
    """Deterministically validate one quote against the signed request shape."""

    reason = "policy_satisfied"
    if now_ns >= request.expires_at_ns:
        reason = "request_expired"
    elif now_ns >= quote.expires_at_ns:
        reason = "quote_expired"
    elif quote.domain not in request.acceptable_domains:
        reason = "domain_not_approved"
    elif quote.registrar != request.approved_registrar:
        reason = "registrar_not_approved"
    elif quote.purchase_price_cents > request.max_purchase_cents:
        reason = "purchase_price_exceeded"
    elif quote.renewal_price_cents > request.max_renewal_cents:
        reason = "renewal_price_exceeded"
    elif quote.owner_ref != request.owner_ref:
        reason = "owner_mismatch"
    elif request.privacy_required and not quote.privacy_enabled:
        reason = "privacy_required"
    elif set(quote.upsells).intersection(request.prohibited_upsells):
        reason = "prohibited_upsell"
    elif not credential_ref.startswith("credential://"):
        reason = "credential_reference_invalid"

    order = None
    if reason == "policy_satisfied":
        order = DomainPurchaseOrder(
            request_id=request.request_id,
            request_hash=request.request_hash,
            quote_id=quote.quote_id,
            quote_hash=quote.quote_hash,
            principal=request.principal,
            domain=quote.domain,
            registrar=quote.registrar,
            purchase_price_cents=quote.purchase_price_cents,
            renewal_price_cents=quote.renewal_price_cents,
            owner_ref=quote.owner_ref,
            privacy_required=request.privacy_required,
            prohibited_upsells=request.prohibited_upsells,
            credential_ref=credential_ref,
            expires_at_ns=min(request.expires_at_ns, quote.expires_at_ns),
            auto_renew_enabled=request.auto_renew_enabled,
        )

    material = {
        "outcome": "allow" if order else "deny",
        "reason": reason,
        "request": asdict(request),
        "quote": asdict(quote),
        "credential_ref": credential_ref,
    }
    return QuoteAssessment(
        outcome=material["outcome"],
        reason=reason,
        request_id=request.request_id,
        quote_id=quote.quote_id,
        assessment_hash=_hash(material),
        order=order,
    )


def purchase_intent(order: DomainPurchaseOrder) -> Intent:
    """Bind the exact order to Pulpo's canonical intent and permit mechanism."""

    return Intent(
        principal=order.principal,
        action="purchase_domain",
        resource=f"commerce:domain:{order.order_hash}",
        cost=order.purchase_price_cents,
        session_id=f"commerce:{order.request_id}",
    )


@dataclass(frozen=True)
class RegistrarResult:
    payment_id: str | None
    charged_cents: int | None
    receipt_hash: str | None
    registration_id: str | None
    domain: str | None
    registrar: str | None


class RegistrarAdapter(Protocol):
    def purchase(self, order: DomainPurchaseOrder, *, max_charge_cents: int) -> RegistrarResult:
        """Execute one exact order while enforcing the supplied hard charge cap."""


@dataclass(frozen=True)
class PaymentEvidence:
    payment_id: str
    charged_cents: int
    receipt_hash: str

    def __post_init__(self) -> None:
        if not self.payment_id:
            raise CommerceViolation("payment identifier is required")
        if self.charged_cents < 0:
            raise CommerceViolation("payment charge must be non-negative")
        _require_sha256(self.receipt_hash, "receipt_hash")


@dataclass(frozen=True)
class DeliveryEvidence:
    registration_id: str
    domain: str
    registrar: str


@dataclass(frozen=True)
class VerificationEvidence:
    domain: str
    registrar: str
    owner_ref: str
    registration_years: int
    privacy_enabled: bool
    dns_state: str
    auto_renew_enabled: bool | None = None

    def __post_init__(self) -> None:
        if self.auto_renew_enabled is not None and type(self.auto_renew_enabled) is not bool:
            raise CommerceViolation("verification auto_renew_enabled must be boolean or None")


@dataclass(frozen=True)
class Reconciliation:
    reservation_id: str
    authorized_cents: int
    charged_cents: int
    variance_cents: int
    balanced: bool


@dataclass(frozen=True)
class BudgetReservation:
    reservation_id: str
    order_hash: str
    reserved_cents: int


class BudgetState(Protocol):
    """Budget-state interface used by the canonical commerce executor."""

    def require_active(
        self,
        reservation_id: str,
        order: DomainPurchaseOrder,
        *,
        now_ns: int,
    ) -> BudgetReservation:
        """Return the exact active reservation or fail closed."""

    def mark_attempted(self, reservation_id: str) -> None:
        """Atomically make an external attempt non-repeatable."""

    def reconcile(self, reservation_id: str, payment: PaymentEvidence) -> Reconciliation:
        """Consume an attempted reservation against verified payment evidence."""


class BudgetAccount:
    """In-memory budget reservation state for the bounded pilot."""

    def __init__(self, ceiling_cents: int = PILOT_PURCHASE_CEILING_CENTS) -> None:
        if not 0 <= ceiling_cents <= PILOT_PURCHASE_CEILING_CENTS:
            raise CommerceViolation("budget exceeds the $30 pilot boundary")
        self.ceiling_cents = ceiling_cents
        self.spent_cents = 0
        self._active: dict[str, BudgetReservation] = {}
        self._order_hashes: set[str] = set()
        self._attempted: set[str] = set()

    @property
    def reserved_cents(self) -> int:
        return sum(reservation.reserved_cents for reservation in self._active.values())

    @property
    def available_cents(self) -> int:
        return self.ceiling_cents - self.spent_cents - self.reserved_cents

    def reserve(self, order: DomainPurchaseOrder, *, now_ns: int) -> BudgetReservation:
        if now_ns <= 0 or now_ns >= order.expires_at_ns:
            raise CommerceViolation("order_expired")
        if order.order_hash in self._order_hashes:
            raise CommerceViolation("order_already_reserved")
        if order.purchase_price_cents > self.available_cents:
            raise CommerceViolation("insufficient_available_budget")
        reservation_id = _hash(
            {
                "order_hash": order.order_hash,
                "reserved_cents": order.purchase_price_cents,
                "ceiling_cents": self.ceiling_cents,
            }
        )
        reservation = BudgetReservation(reservation_id, order.order_hash, order.purchase_price_cents)
        self._active[reservation_id] = reservation
        self._order_hashes.add(order.order_hash)
        return reservation

    def require_active(self, reservation_id: str, order: DomainPurchaseOrder, *, now_ns: int) -> BudgetReservation:
        if now_ns <= 0 or now_ns >= order.expires_at_ns:
            raise CommerceViolation("order_expired")
        reservation = self._active.get(reservation_id)
        if reservation is None:
            raise CommerceViolation("reservation_unknown_or_consumed")
        if reservation_id in self._attempted:
            raise CommerceViolation("reservation_already_attempted")
        if reservation.order_hash != order.order_hash:
            raise CommerceViolation("reservation_order_mismatch")
        if reservation.reserved_cents != order.purchase_price_cents:
            raise CommerceViolation("reservation_amount_mismatch")
        return reservation

    def mark_attempted(self, reservation_id: str) -> None:
        if reservation_id not in self._active or reservation_id in self._attempted:
            raise CommerceViolation("reservation_not_active")
        self._attempted.add(reservation_id)

    def reconcile(self, reservation_id: str, payment: PaymentEvidence) -> Reconciliation:
        reservation = self._active.get(reservation_id)
        if reservation is None or reservation_id not in self._attempted:
            raise CommerceViolation("reservation_not_attempted")
        if payment.charged_cents > reservation.reserved_cents:
            raise CommerceViolation("charge_exceeded_reservation")
        del self._active[reservation_id]
        self.spent_cents += payment.charged_cents
        return Reconciliation(
            reservation_id=reservation_id,
            authorized_cents=reservation.reserved_cents,
            charged_cents=payment.charged_cents,
            variance_cents=reservation.reserved_cents - payment.charged_cents,
            balanced=True,
        )


class SQLiteBudgetAccount:
    """Restart-durable commerce state for one bounded pilot budget.

    This is operational state, not an audit ledger or payment rail.  SQLite
    transactions make reservation, attempt, and reconciliation transitions
    atomic across workers that share a protected database path.  The caller is
    still responsible for placing that path outside governed-worker mutation
    and rollback authority.
    """

    def __init__(
        self,
        path: str | Path,
        ceiling_cents: int = PILOT_PURCHASE_CEILING_CENTS,
    ) -> None:
        if not 0 <= ceiling_cents <= PILOT_PURCHASE_CEILING_CENTS:
            raise CommerceViolation("budget exceeds the $30 pilot boundary")
        if not str(path) or str(path) == ":memory:":
            raise CommerceViolation("durable budget requires a filesystem path")
        self.path = Path(path)
        if not self.path.parent.is_dir():
            raise CommerceViolation("budget store parent directory must already exist")
        if self.path.exists() and not self.path.is_file():
            raise CommerceViolation("budget store path must be a regular file")
        self.ceiling_cents = ceiling_cents
        try:
            with closing(self._connect()) as connection, connection:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS commerce_budget (
                        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                        ceiling_cents INTEGER NOT NULL CHECK (ceiling_cents >= 0),
                        spent_cents INTEGER NOT NULL CHECK (spent_cents >= 0)
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS commerce_reservations (
                        reservation_id TEXT PRIMARY KEY,
                        order_hash TEXT NOT NULL UNIQUE,
                        reserved_cents INTEGER NOT NULL CHECK (reserved_cents >= 0),
                        state TEXT NOT NULL CHECK (state IN ('active', 'attempted', 'reconciled')),
                        charged_cents INTEGER,
                        receipt_hash TEXT,
                        CHECK (
                            (state != 'reconciled' AND charged_cents IS NULL AND receipt_hash IS NULL)
                            OR
                            (state = 'reconciled' AND charged_cents IS NOT NULL AND receipt_hash IS NOT NULL)
                        )
                    )
                    """
                )
                row = connection.execute(
                    "SELECT ceiling_cents FROM commerce_budget WHERE singleton = 1"
                ).fetchone()
                if row is None:
                    connection.execute(
                        "INSERT INTO commerce_budget (singleton, ceiling_cents, spent_cents) VALUES (1, ?, 0)",
                        (ceiling_cents,),
                    )
                elif row[0] != ceiling_cents:
                    raise CommerceViolation("configured ceiling does not match durable budget")
        except CommerceViolation:
            raise
        except (OSError, sqlite3.Error) as error:
            raise CommerceViolation("durable budget store unavailable") from error

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0, isolation_level=None)
        try:
            connection.execute("PRAGMA synchronous=FULL")
        except BaseException:
            connection.close()
            raise
        return connection

    @property
    def spent_cents(self) -> int:
        try:
            with closing(self._connect()) as connection, connection:
                return int(
                    connection.execute(
                        "SELECT spent_cents FROM commerce_budget WHERE singleton = 1"
                    ).fetchone()[0]
                )
        except (OSError, sqlite3.Error, TypeError) as error:
            raise CommerceViolation("durable budget store unavailable") from error

    @property
    def reserved_cents(self) -> int:
        try:
            with closing(self._connect()) as connection, connection:
                return int(
                    connection.execute(
                        """
                        SELECT COALESCE(SUM(reserved_cents), 0)
                        FROM commerce_reservations
                        WHERE state IN ('active', 'attempted')
                        """
                    ).fetchone()[0]
                )
        except (OSError, sqlite3.Error, TypeError) as error:
            raise CommerceViolation("durable budget store unavailable") from error

    @property
    def available_cents(self) -> int:
        return self.ceiling_cents - self.spent_cents - self.reserved_cents

    def reserve(self, order: DomainPurchaseOrder, *, now_ns: int) -> BudgetReservation:
        if now_ns <= 0 or now_ns >= order.expires_at_ns:
            raise CommerceViolation("order_expired")
        reservation_id = _hash(
            {
                "order_hash": order.order_hash,
                "reserved_cents": order.purchase_price_cents,
                "ceiling_cents": self.ceiling_cents,
            }
        )
        try:
            with closing(self._connect()) as connection, connection:
                connection.execute("BEGIN IMMEDIATE")
                if connection.execute(
                    "SELECT 1 FROM commerce_reservations WHERE order_hash = ?",
                    (order.order_hash,),
                ).fetchone():
                    connection.rollback()
                    raise CommerceViolation("order_already_reserved")
                spent = connection.execute(
                    "SELECT spent_cents FROM commerce_budget WHERE singleton = 1"
                ).fetchone()[0]
                reserved = connection.execute(
                    """
                    SELECT COALESCE(SUM(reserved_cents), 0)
                    FROM commerce_reservations
                    WHERE state IN ('active', 'attempted')
                    """
                ).fetchone()[0]
                if order.purchase_price_cents > self.ceiling_cents - spent - reserved:
                    connection.rollback()
                    raise CommerceViolation("insufficient_available_budget")
                connection.execute(
                    """
                    INSERT INTO commerce_reservations
                        (reservation_id, order_hash, reserved_cents, state)
                    VALUES (?, ?, ?, 'active')
                    """,
                    (reservation_id, order.order_hash, order.purchase_price_cents),
                )
                connection.commit()
        except CommerceViolation:
            raise
        except (OSError, sqlite3.Error, TypeError) as error:
            raise CommerceViolation("durable budget store unavailable") from error
        return BudgetReservation(reservation_id, order.order_hash, order.purchase_price_cents)

    def reservation_for_order(self, order: DomainPurchaseOrder) -> BudgetReservation:
        """Read the original durable reservation, including after settlement.

        Execution handles retain their issuance values across attempt and
        reconciliation state changes. This lookup grants no execution right
        and does not reopen a consumed reservation.
        """
        try:
            with closing(self._connect()) as connection:
                row = connection.execute(
                    """
                    SELECT reservation_id, reserved_cents
                    FROM commerce_reservations WHERE order_hash = ?
                    """,
                    (order.order_hash,),
                ).fetchone()
        except (OSError, sqlite3.Error, TypeError) as error:
            raise CommerceViolation("durable budget store unavailable") from error
        if row is None:
            raise CommerceViolation("reservation_unknown")
        if type(row[1]) is not int or row[1] != order.purchase_price_cents:
            raise CommerceViolation("reservation_amount_mismatch")
        return BudgetReservation(row[0], order.order_hash, row[1])

    def require_active(
        self,
        reservation_id: str,
        order: DomainPurchaseOrder,
        *,
        now_ns: int,
    ) -> BudgetReservation:
        if now_ns <= 0 or now_ns >= order.expires_at_ns:
            raise CommerceViolation("order_expired")
        try:
            with closing(self._connect()) as connection, connection:
                row = connection.execute(
                    """
                    SELECT order_hash, reserved_cents, state
                    FROM commerce_reservations
                    WHERE reservation_id = ?
                    """,
                    (reservation_id,),
                ).fetchone()
        except (OSError, sqlite3.Error) as error:
            raise CommerceViolation("durable budget store unavailable") from error
        if row is None or row[2] == "reconciled":
            raise CommerceViolation("reservation_unknown_or_consumed")
        if row[2] == "attempted":
            raise CommerceViolation("reservation_already_attempted")
        if row[0] != order.order_hash:
            raise CommerceViolation("reservation_order_mismatch")
        if row[1] != order.purchase_price_cents:
            raise CommerceViolation("reservation_amount_mismatch")
        return BudgetReservation(reservation_id, row[0], row[1])

    def mark_attempted(self, reservation_id: str) -> None:
        try:
            with closing(self._connect()) as connection, connection:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    """
                    UPDATE commerce_reservations
                    SET state = 'attempted'
                    WHERE reservation_id = ? AND state = 'active'
                    """,
                    (reservation_id,),
                )
                if cursor.rowcount != 1:
                    connection.rollback()
                    raise CommerceViolation("reservation_not_active")
                connection.commit()
        except CommerceViolation:
            raise
        except (OSError, sqlite3.Error) as error:
            raise CommerceViolation("durable budget store unavailable") from error

    def reconcile(self, reservation_id: str, payment: PaymentEvidence) -> Reconciliation:
        try:
            with closing(self._connect()) as connection, connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    """
                    SELECT reserved_cents, state
                    FROM commerce_reservations
                    WHERE reservation_id = ?
                    """,
                    (reservation_id,),
                ).fetchone()
                if row is None or row[1] != "attempted":
                    connection.rollback()
                    raise CommerceViolation("reservation_not_attempted")
                if payment.charged_cents > row[0]:
                    connection.rollback()
                    raise CommerceViolation("charge_exceeded_reservation")
                connection.execute(
                    """
                    UPDATE commerce_reservations
                    SET state = 'reconciled', charged_cents = ?, receipt_hash = ?
                    WHERE reservation_id = ?
                    """,
                    (payment.charged_cents, payment.receipt_hash, reservation_id),
                )
                connection.execute(
                    """
                    UPDATE commerce_budget
                    SET spent_cents = spent_cents + ?
                    WHERE singleton = 1
                    """,
                    (payment.charged_cents,),
                )
                connection.commit()
        except CommerceViolation:
            raise
        except (OSError, sqlite3.Error, TypeError) as error:
            raise CommerceViolation("durable budget store unavailable") from error
        return Reconciliation(
            reservation_id=reservation_id,
            authorized_cents=row[0],
            charged_cents=payment.charged_cents,
            variance_cents=row[0] - payment.charged_cents,
            balanced=True,
        )


@dataclass
class CommerceOutcome:
    order_hash: str
    authorized: bool = False
    payment: PaymentEvidence | None = None
    delivery: DeliveryEvidence | None = None
    verification: VerificationEvidence | None = None
    reconciliation: Reconciliation | None = None
    accepted: bool = False
    valuable: bool = False
    value_observation: str | None = None
    capability_revoked: bool = False


def _live_observation_hash(order: DomainPurchaseOrder, result: RegistrarResult, *, reason: str) -> str:
    """Hash the provider result the live executor itself observed.

    First-party observation material only: the synchronous return of the
    provider call this executor made, plus the reason the outcome was
    classified that way. This is NOT an IndependentDomainObservation --
    there was no independent observer on the live path -- so the schema is
    deliberately distinct and the observer recorded on the custody
    transition is LIVE_CUSTODY_EXECUTOR_ID.
    """
    return _hash({
        "schema": "pulpo.live-purchase-observation.v0",
        "order_hash": order.order_hash,
        "payment_id": result.payment_id,
        "charged_cents": result.charged_cents,
        "receipt_hash": result.receipt_hash,
        "registration_id": result.registration_id,
        "domain": result.domain,
        "registrar": result.registrar,
        "reason": reason,
    })


class DomainCommerceExecutor:
    """Consume a Pulpo permit before invoking a registrar adapter exactly once.

    The live purchase path. When a `GovernedDomainAttemptCoordinator` is
    supplied, consumption runs through it: exact locked-target resolution,
    canonical consume, audit-tip verification, and one custody attempt, before
    any transmission right is released. Without one, the same direct consume
    runs, and both paths share the pre-purchase revalidation and the durable
    unknown-outcome record below. No new executor, no second ledger: unknown
    outcomes are events in the existing canonical audit.

    Coordinator path, custody lifecycle: the attempt is claimed and its one
    transmission right released before the provider call (executor
    LIVE_CUSTODY_EXECUTOR_ID -- the trusted in-process executor, not a
    worker), moved to reconciliation-required once the call returns or
    raises, and reconciled from the executor's own observation when the
    outcome is known: success on complete payment + complete delivery
    evidence with settled budget, failure when the provider's own return
    contradicts the authorization (charge outside the authorized amount).
    Incomplete evidence stays reconciliation-required -- it is unresolved,
    exactly as IndependentDomainReconciler classifies an incomplete
    observation -- and a refused purchase never claims or transmits, so
    the attempt stays authorized and the refusal event is its terminal
    record. Driving claim/transmit for a purchase handed to a worker
    would be fabrication; here the transmission IS this executor's own
    provider call, recorded under its own id.

    `evidence_projector`, when supplied, is called after every custody
    transition (authorize, claim, transmit, require-reconciliation,
    reconcile) so the convergence outbox drains before the next head
    advance -- the trigger blocks the next transition until the previous
    one is projected. `SQLiteCustodyEvidenceConvergence.project_all` is
    the existing projector. Constructing that convergence against the
    live store without wiring its projector here breaks the coordinator
    path by design (custody cannot advance on unprojected evidence).
    Before the provider call a projector failure refuses the purchase;
    after it, custody failures never rewrite the provider outcome -- the
    attempt stays in a non-terminal state and the incident channel
    reports it unresolved.
    """

    def __init__(
        self,
        attempted_order_hashes: set[str] | None = None,
        coordinator: GovernedDomainAttemptCoordinator | None = None,
        evidence_projector: Callable[[], None] | None = None,
    ) -> None:
        self.attempted_order_hashes = attempted_order_hashes if attempted_order_hashes is not None else set()
        self.coordinator = coordinator
        self.evidence_projector = evidence_projector

    def _record_purchase_event(
        self,
        kernel: GovernanceKernel,
        event: str,
        payload: dict[str, Any],
        now_ns: int,
    ) -> None:
        # Best effort only: the spent permit, the attempted reservation, and
        # the attempt set already block any retry, so a failed projection must
        # never mask the outcome the caller has to reconcile. The failure mode
        # is evidence-only, not a second execution right.
        try:
            kernel._state.append(event, payload, now_ns)  # noqa: SLF001 - existing canonical audit seam
        except Exception:
            pass

    def _purchase_payload(
        self,
        kernel: GovernanceKernel,
        order: DomainPurchaseOrder,
        intent: Intent,
        permit: str,
        reservation_id: str,
        *,
        reason: str,
        custody_attempt: GovernedDomainAttempt | None,
        error: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "order_hash": order.order_hash,
            "intent_hash": kernel.intent_hash(intent),
            # The permit itself is authority material; only its hash is evidence.
            "permit_hash": sha256(permit.encode()).hexdigest(),
            "reservation_id": reservation_id,
            "reason": reason,
        }
        if error is not None:
            payload["error"] = error
        if custody_attempt is not None:
            payload["custody_attempt_id"] = custody_attempt.attempt_id
        return payload

    def _project_custody_evidence(self) -> None:
        """Project pending custody transitions into the canonical audit.

        No-op without a wired projector. A failure raises
        CommerceViolation: before the provider call that refuses the
        purchase; after it, callers treat it as best-effort (see below).
        """
        if self.evidence_projector is not None:
            try:
                self.evidence_projector()
            except Exception as exc:
                raise CommerceViolation("custody_evidence_not_canonical") from exc

    def _claim_and_transmit(
        self,
        kernel: GovernanceKernel,
        order: DomainPurchaseOrder,
        intent: Intent,
        permit: str,
        reservation_id: str,
        custody_attempt: GovernedDomainAttempt,
        now_ns: int,
    ) -> None:
        """Claim the attempt and release its one transmission right.

        Runs before the provider call, while refusal is still clean: the
        authorization is projected first (the convergence trigger blocks
        the next head advance while an obligation is pending), then the
        custody clock is checked, then claim, then transmission with the
        live call's own provider request id. An expiry refusal records
        `purchase_revalidation_failed` carrying the attempt id, so the
        incident channel consumes the attempt into exactly one near-miss.
        Any other custody failure refuses the purchase with no provider
        call; the attempt stays in the non-terminal state it reached and
        the channel reports it unresolved.
        """
        assert self.coordinator is not None
        custody = self.coordinator.custody
        attempt_id = custody_attempt.attempt_id
        try:
            self._project_custody_evidence()
            head = custody.snapshot()
            if custody._custody_now(head) >= order.expires_at_ns:  # noqa: SLF001 - same trusted-clock seam TrustedDomainExecutor uses
                raise CustodyViolation("order_expired")
            custody.claim_attempt(
                expected_epoch=head.epoch,
                expected_state_root=head.state_root,
                attempt_id=attempt_id,
                executor_id=LIVE_CUSTODY_EXECUTOR_ID,
            )
            self._project_custody_evidence()
            head = custody.snapshot()
            custody.authorize_transmission(
                expected_epoch=head.epoch,
                expected_state_root=head.state_root,
                attempt_id=attempt_id,
                provider_request_id=f"domain:{attempt_id}:live",
                expires_at_ns=order.expires_at_ns,
            )
            self._project_custody_evidence()
        except CustodyViolation as exc:
            if str(exc) == "order_expired":
                self._record_purchase_event(
                    kernel,
                    "purchase_revalidation_failed",
                    self._purchase_payload(
                        kernel, order, intent, permit, reservation_id,
                        reason="order_expired", custody_attempt=custody_attempt,
                    ),
                    now_ns,
                )
                raise CommerceViolation("order_expired") from exc
            raise CommerceViolation(str(exc)) from exc

    def _require_custody_reconciliation(self, custody_attempt: GovernedDomainAttempt) -> None:
        """Move a transmitted attempt to reconciliation-required, then project."""
        assert self.coordinator is not None
        custody = self.coordinator.custody
        head = custody.snapshot()
        try:
            custody.require_reconciliation(
                expected_epoch=head.epoch,
                expected_state_root=head.state_root,
                attempt_id=custody_attempt.attempt_id,
            )
        except CustodyViolation as exc:
            raise CommerceViolation(str(exc)) from exc
        self._project_custody_evidence()

    def _reconcile_custody_attempt(
        self,
        custody_attempt: GovernedDomainAttempt,
        *,
        outcome: str,
        observation_hash: str,
    ) -> None:
        """Best-effort terminal reconciliation from the live observation.

        A custody or projection failure here must never mask the purchase
        outcome the caller has to act on -- the same principle as
        _record_purchase_event. The attempt stays in a non-terminal state
        (reconciliation-required, or request-transmitted if even that
        failed) and the incident channel reports it unresolved; a
        transition that did commit stays durably pending in the
        convergence outbox until projected.
        """
        assert self.coordinator is not None
        custody = self.coordinator.custody
        try:
            head = custody.snapshot()
            custody.reconcile_observed(
                expected_epoch=head.epoch,
                expected_state_root=head.state_root,
                attempt_id=custody_attempt.attempt_id,
                outcome=outcome,
                observation_hash=observation_hash,
                observer_id=LIVE_CUSTODY_EXECUTOR_ID,
            )
            self._project_custody_evidence()
        except (CustodyViolation, CommerceViolation):
            pass

    def execute(
        self,
        kernel: GovernanceKernel,
        order: DomainPurchaseOrder,
        permit: str,
        adapter: RegistrarAdapter,
        budget: BudgetState,
        reservation_id: str,
        *,
        now_ns: int,
        target_id: str | None = None,
        expected_target_hash: str | None = None,
        target_version: int = 1,
    ) -> CommerceOutcome:
        if now_ns >= order.expires_at_ns:
            raise CommerceViolation("order_expired")
        if order.order_hash in self.attempted_order_hashes:
            raise CommerceViolation("duplicate_purchase_attempt")

        intent = purchase_intent(order)
        custody_attempt: GovernedDomainAttempt | None = None
        if self.coordinator is not None:
            # The coordinator owns its budget account; a different account
            # would mark the attempt on one store and reconcile on another.
            if budget is not self.coordinator.budget:
                raise CommerceViolation("custody_budget_mismatch")
            if not target_id or not expected_target_hash:
                raise CommerceViolation("custody_target_required")
            try:
                custody_attempt = self.coordinator.authorize(
                    target_id=target_id,
                    expected_target_hash=expected_target_hash,
                    order=order,
                    permit=permit,
                    reservation_id=reservation_id,
                    version=target_version,
                )
            except CustodyViolation as exc:
                raise CommerceViolation(str(exc)) from exc
        else:
            budget.require_active(reservation_id, order, now_ns=now_ns)
            if not kernel.consume(permit, intent):
                raise CommerceViolation("permit_rejected")

            # Mark before the external call.  An uncertain network outcome must be
            # reconciled, not blindly retried with a new capability.
            budget.mark_attempted(reservation_id)

        self.attempted_order_hashes.add(order.order_hash)
        outcome = CommerceOutcome(order_hash=order.order_hash, authorized=True, capability_revoked=True)

        # Re-read permit/directive/policy/expiry state immediately before the
        # provider call, under the same transaction discipline as consume.
        # A revocation or expiry landing between consume and transmission
        # refuses here, before any consequence exists.
        revalidation = kernel.revalidate_consumed_permit(permit, intent)
        if revalidation != "valid":
            self._record_purchase_event(
                kernel,
                "purchase_revalidation_failed",
                self._purchase_payload(
                    kernel, order, intent, permit, reservation_id,
                    reason=revalidation, custody_attempt=custody_attempt,
                ),
                now_ns,
            )
            raise CommerceViolation(revalidation)

        if custody_attempt is not None:
            self._claim_and_transmit(
                kernel, order, intent, permit, reservation_id, custody_attempt, now_ns,
            )
        try:
            result = adapter.purchase(order, max_charge_cents=order.purchase_price_cents)
        except Exception as exc:
            # The provider call may already have changed reality. Record the
            # unknown outcome as durable canonical evidence, then re-raise the
            # original failure unchanged: no silent success, no blind retry.
            if custody_attempt is not None:
                # The transmission happened: leave the attempt open for
                # independent reconciliation instead of stranded in
                # attempt_authorized, where no reconciler could touch it.
                # Best-effort -- the unknown record below is the safety
                # boundary if custody itself failed.
                try:
                    self._require_custody_reconciliation(custody_attempt)
                except CommerceViolation:
                    pass
            self._record_purchase_event(
                kernel,
                "purchase_consequence_unknown",
                self._purchase_payload(
                    kernel, order, intent, permit, reservation_id,
                    reason="external_consequence_not_yet_verified",
                    custody_attempt=custody_attempt,
                    error=type(exc).__name__,
                ),
                now_ns,
            )
            raise

        if custody_attempt is not None:
            # The transmission happened and the provider answered: the
            # attempt must leave request_transmitted for
            # reconciliation-required before any outcome is settled, so a
            # later independent observation can resolve it however
            # validation below goes. Best-effort -- a custody failure must
            # not rewrite the provider outcome (see _record_purchase_event).
            try:
                self._require_custody_reconciliation(custody_attempt)
            except CommerceViolation:
                pass

        if result.payment_id is not None or result.charged_cents is not None or result.receipt_hash is not None:
            if None in (result.payment_id, result.charged_cents, result.receipt_hash):
                raise CommerceViolation("incomplete_payment_evidence")
            if result.charged_cents < 0 or result.charged_cents > order.purchase_price_cents:
                if custody_attempt is not None:
                    # Known-wrong on the provider's own return: the charge
                    # it reports contradicts the authorization. This matches
                    # IndependentDomainReconciler's
                    # observed_charge_exceeded_authorization failure; a
                    # negative charge is malformed the same way.
                    reason = ("charge_exceeded_authorized_amount"
                              if result.charged_cents > order.purchase_price_cents
                              else "charge_invalid")
                    self._reconcile_custody_attempt(
                        custody_attempt,
                        outcome="failure",
                        observation_hash=_live_observation_hash(order, result, reason=reason),
                    )
                raise CommerceViolation("charge_exceeded_authorized_amount")
            outcome.payment = PaymentEvidence(result.payment_id, result.charged_cents, result.receipt_hash)
            outcome.reconciliation = budget.reconcile(reservation_id, outcome.payment)

        if result.registration_id is not None or result.domain is not None or result.registrar is not None:
            if None in (result.registration_id, result.domain, result.registrar):
                raise CommerceViolation("incomplete_delivery_evidence")
            outcome.delivery = DeliveryEvidence(result.registration_id, result.domain, result.registrar)

        if (custody_attempt is not None and outcome.payment is not None
                and outcome.delivery is not None):
            # Complete payment evidence with settled budget, complete
            # delivery evidence: the live executor's own synchronous
            # observation verifies the purchase. First-party, not
            # independent -- see LIVE_CUSTODY_EXECUTOR_ID. A purchase with
            # payment but no delivery evidence stays
            # reconciliation-required: delivery is unverified, and the
            # independent reconciler may still observe it later.
            self._reconcile_custody_attempt(
                custody_attempt,
                outcome="success",
                observation_hash=_live_observation_hash(
                    order, result, reason="external_consequence_verified"),
            )

        return outcome


def accept_delivery(
    order: DomainPurchaseOrder,
    outcome: CommerceOutcome,
    verification: VerificationEvidence,
) -> None:
    """Accept only independently verified delivery and configuration evidence."""

    if outcome.payment is None:
        raise CommerceViolation("payment_not_proven")
    if outcome.delivery is None:
        raise CommerceViolation("delivery_not_proven")
    if verification.domain != order.domain or outcome.delivery.domain != order.domain:
        raise CommerceViolation("domain_delivery_mismatch")
    if verification.registrar != order.registrar or outcome.delivery.registrar != order.registrar:
        raise CommerceViolation("registrar_delivery_mismatch")
    if verification.owner_ref != order.owner_ref:
        raise CommerceViolation("ownership_not_verified")
    if verification.registration_years < 1:
        raise CommerceViolation("registration_period_not_verified")
    if order.privacy_required and not verification.privacy_enabled:
        raise CommerceViolation("privacy_not_verified")
    if verification.auto_renew_enabled is None:
        raise CommerceViolation("auto_renew_not_verified")
    if verification.auto_renew_enabled != order.auto_renew_enabled:
        raise CommerceViolation("auto_renew_mismatch")
    if verification.dns_state not in {"registered", "configured"}:
        raise CommerceViolation("dns_state_not_accepted")
    outcome.verification = verification
    outcome.accepted = True


def record_value(outcome: CommerceOutcome, observation: str) -> None:
    """Record continuing value separately from purchase acceptance."""

    if not outcome.accepted:
        raise CommerceViolation("value_requires_acceptance")
    if not observation:
        raise CommerceViolation("value observation is required")
    outcome.valuable = True
    outcome.value_observation = observation


def build_proof_bundle(
    kernel: GovernanceKernel,
    request: DomainPurchaseRequest,
    quote: DomainQuote,
    assessment: QuoteAssessment,
    outcome: CommerceOutcome | None,
) -> dict[str, Any]:
    """Project portable commerce evidence from domain state and kernel audit."""

    payload = {
        "schema": "pulpo.commerce.proof.v1",
        "request": asdict(request),
        "quote": asdict(quote),
        "assessment": {key: value for key, value in asdict(assessment).items() if key != "order"},
        "order": asdict(assessment.order) if assessment.order else None,
        "outcome": asdict(outcome) if outcome else None,
        "audit_valid": kernel.verify_audit(),
        "audit_tip": kernel.audit[-1]["hash"] if kernel.audit else None,
    }
    return {**payload, "bundle_hash": _hash(payload)}
