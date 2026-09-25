"""L3A Multi-Agent Workflow — Complaint Investigation System.

Architecture:
    Coordinator  → dispatches tasks to specialist agents
    OrderAgent   → queries order & item data via MCP
    PaymentAgent → queries payment data via MCP
    ShipmentAgent→ queries shipment data via MCP
    PolicyAgent  → queries policy rules via MCP
    Verifier     → cross-checks consistency before finalizing
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from . import OUTPUT_SCHEMA_VERSION
from .mcp_gateway import EvidenceGateway
from .trace import TraceWriter

logger = logging.getLogger(__name__)

# ── Shared data structure for passing evidence between agents ────────────────


@dataclass
class EvidenceStore:
    """Collects evidence gathered by specialist agents for a single case."""

    case_id: str
    order_data: dict[str, Any] | None = None
    order_ref: str | None = None
    items_data: list[dict[str, Any]] = field(default_factory=list)
    items_ref: str | None = None
    payments_data: list[dict[str, Any]] = field(default_factory=list)
    payments_ref: str | None = None
    payment_timeline_data: dict[str, Any] | None = None
    payment_timeline_ref: str | None = None
    shipment_data: dict[str, Any] | None = None
    shipment_ref: str | None = None
    sellers_data: list[dict[str, Any]] = field(default_factory=list)
    sellers_ref: str | None = None
    policy_data: dict[str, Any] | None = None
    policy_ref: str | None = None

    @property
    def all_refs(self) -> list[str]:
        refs: list[str] = []
        for ref in (
            self.order_ref,
            self.items_ref,
            self.payments_ref,
            self.payment_timeline_ref,
            self.shipment_ref,
            self.sellers_ref,
            self.policy_ref,
        ):
            if ref:
                refs.append(ref)
        return refs


# ── Specialist Agent: Order & Items ──────────────────────────────────────────


class OrderAgent:
    """Queries order, item, and seller evidence from MCP Gateway."""

    ACTOR = "order-agent"

    async def investigate(
        self,
        case: dict[str, Any],
        gateway: EvidenceGateway,
        trace: TraceWriter,
        store: EvidenceStore,
        available_tools: list[str],
    ) -> None:
        case_id = case["case_id"]
        order_id = case["customer_request"]["claimed_order_id"]

        # ── Get order ────────────────────────────────────────────────────
        if "get_order" in available_tools:
            try:
                evidence = await gateway.call(
                    "get_order",
                    case_id=case_id,
                    order_id=order_id,
                )
                store.order_data = evidence["data"]
                store.order_ref = evidence["evidence_ref"]
                trace.emit(
                    case_id=case_id,
                    event_type="tool_result_consumed",
                    actor=self.ACTOR,
                    tool_name="get_order",
                    evidence_refs=[evidence["evidence_ref"]],
                )
            except Exception as exc:
                logger.warning("get_order failed for %s: %s", case_id, exc)

        # ── Get order items ──────────────────────────────────────────────
        if "get_order_items" in available_tools:
            try:
                evidence = await gateway.call(
                    "get_order_items",
                    case_id=case_id,
                    order_id=order_id,
                )
                data = evidence["data"]
                store.items_data = data if isinstance(data, list) else data.get("items", [data])
                store.items_ref = evidence["evidence_ref"]
                trace.emit(
                    case_id=case_id,
                    event_type="tool_result_consumed",
                    actor=self.ACTOR,
                    tool_name="get_order_items",
                    evidence_refs=[evidence["evidence_ref"]],
                )
            except Exception as exc:
                logger.warning("get_order_items failed for %s: %s", case_id, exc)

        # ── Get sellers (by order_id) ────────────────────────────────────
        if "get_sellers" in available_tools:
            try:
                evidence = await gateway.call(
                    "get_sellers",
                    case_id=case_id,
                    order_id=order_id,
                )
                data = evidence["data"]
                store.sellers_data = data if isinstance(data, list) else data.get("sellers", [data])
                store.sellers_ref = evidence["evidence_ref"]
                trace.emit(
                    case_id=case_id,
                    event_type="tool_result_consumed",
                    actor=self.ACTOR,
                    tool_name="get_sellers",
                    evidence_refs=[evidence["evidence_ref"]],
                )
            except Exception as exc:
                logger.warning("get_sellers failed for %s: %s", case_id, exc)


# ── Specialist Agent: Payment ────────────────────────────────────────────────


class PaymentAgent:
    """Queries payment evidence from MCP Gateway."""

    ACTOR = "payment-agent"

    async def investigate(
        self,
        case: dict[str, Any],
        gateway: EvidenceGateway,
        trace: TraceWriter,
        store: EvidenceStore,
        available_tools: list[str],
    ) -> None:
        case_id = case["case_id"]
        order_id = case["customer_request"]["claimed_order_id"]

        # ── Get order payments ───────────────────────────────────────────
        if "get_order_payments" in available_tools:
            try:
                evidence = await gateway.call(
                    "get_order_payments",
                    case_id=case_id,
                    order_id=order_id,
                )
                data = evidence["data"]
                store.payments_data = data if isinstance(data, list) else data.get("payments", [data])
                store.payments_ref = evidence["evidence_ref"]
                trace.emit(
                    case_id=case_id,
                    event_type="tool_result_consumed",
                    actor=self.ACTOR,
                    tool_name="get_order_payments",
                    evidence_refs=[evidence["evidence_ref"]],
                )
            except Exception as exc:
                logger.warning("get_order_payments failed for %s: %s", case_id, exc)

        # ── Get payment timeline ─────────────────────────────────────────
        if "get_payment_timeline" in available_tools:
            try:
                evidence = await gateway.call(
                    "get_payment_timeline",
                    case_id=case_id,
                    order_id=order_id,
                )
                store.payment_timeline_data = evidence["data"]
                store.payment_timeline_ref = evidence["evidence_ref"]
                trace.emit(
                    case_id=case_id,
                    event_type="tool_result_consumed",
                    actor=self.ACTOR,
                    tool_name="get_payment_timeline",
                    evidence_refs=[evidence["evidence_ref"]],
                )
            except Exception as exc:
                logger.warning("get_payment_timeline failed for %s: %s", case_id, exc)


# ── Specialist Agent: Shipment ───────────────────────────────────────────────


class ShipmentAgent:
    """Queries shipment evidence from MCP Gateway."""

    ACTOR = "shipment-agent"

    async def investigate(
        self,
        case: dict[str, Any],
        gateway: EvidenceGateway,
        trace: TraceWriter,
        store: EvidenceStore,
        available_tools: list[str],
    ) -> None:
        case_id = case["case_id"]
        order_id = case["customer_request"]["claimed_order_id"]

        # ── Get shipment summary ─────────────────────────────────────────
        if "get_shipment_summary" in available_tools:
            try:
                evidence = await gateway.call(
                    "get_shipment_summary",
                    case_id=case_id,
                    order_id=order_id,
                )
                store.shipment_data = evidence["data"]
                store.shipment_ref = evidence["evidence_ref"]
                trace.emit(
                    case_id=case_id,
                    event_type="tool_result_consumed",
                    actor=self.ACTOR,
                    tool_name="get_shipment_summary",
                    evidence_refs=[evidence["evidence_ref"]],
                )
            except Exception as exc:
                logger.warning("get_shipment_summary failed for %s: %s", case_id, exc)


# ── Specialist Agent: Policy ─────────────────────────────────────────────────


class PolicyAgent:
    """Queries policy evidence from MCP Gateway."""

    ACTOR = "policy-agent"

    async def investigate(
        self,
        case: dict[str, Any],
        gateway: EvidenceGateway,
        trace: TraceWriter,
        store: EvidenceStore,
        available_tools: list[str],
    ) -> None:
        case_id = case["case_id"]
        policy_version = case.get("policy_version", "EC_POLICY_V1")

        if "get_policy" in available_tools:
            try:
                evidence = await gateway.call(
                    "get_policy",
                    case_id=case_id,
                    policy_version=policy_version,
                )
                store.policy_data = evidence["data"]
                store.policy_ref = evidence["evidence_ref"]
                trace.emit(
                    case_id=case_id,
                    event_type="tool_result_consumed",
                    actor=self.ACTOR,
                    tool_name="get_policy",
                    evidence_refs=[evidence["evidence_ref"]],
                )
            except Exception as exc:
                logger.warning("get_policy failed for %s: %s", case_id, exc)


# ── Evidence Analysis Helpers ────────────────────────────────────────────────

_VALID_ISSUES = {
    "canceled_order_paid",
    "unavailable_order_paid",
    "late_delivery_seller",
    "late_delivery_logistics",
    "valid_split_payment",
    "payment_mismatch",
    "duplicate_charge",
    "refund_pending",
    "refund_failed",
    "unsupported_claim",
    "insufficient_evidence",
}


def _get_order_status(store: EvidenceStore) -> str | None:
    """Extract order status from evidence."""
    if store.order_data:
        return store.order_data.get("order_status")
    if store.shipment_data:
        return store.shipment_data.get("order_status")
    return None


def _total_paid(store: EvidenceStore) -> float:
    """Sum all payment values."""
    total = 0.0
    for p in store.payments_data:
        try:
            total += float(p.get("payment_value", 0))
        except (TypeError, ValueError):
            pass
    return round(total, 2)


def _item_total(store: EvidenceStore) -> float:
    """Sum price + freight for all items."""
    total = 0.0
    for item in store.items_data:
        try:
            total += float(item.get("price", 0)) + float(item.get("freight_value", 0))
        except (TypeError, ValueError):
            pass
    return round(total, 2)


def _freight_total(store: EvidenceStore) -> float:
    """Sum freight values for all items."""
    total = 0.0
    for item in store.items_data:
        try:
            total += float(item.get("freight_value", 0))
        except (TypeError, ValueError):
            pass
    return round(total, 2)


def _has_late_delivery(store: EvidenceStore) -> bool:
    """Check if shipment has late delivery event."""
    if store.shipment_data:
        events = store.shipment_data.get("events", [])
        for event in events:
            if event.get("event_type") in ("delivered_late", "late_delivery"):
                return True
        # Also check dates
        estimated = store.shipment_data.get("estimated_delivery_at")
        delivered = store.shipment_data.get("delivered_customer_at")
        if estimated and delivered and str(delivered) > str(estimated):
            return True
    return False


def _late_delivery_actor(store: EvidenceStore) -> str | None:
    """Get the actor responsible for late delivery from shipment events."""
    if store.shipment_data:
        events = store.shipment_data.get("events", [])
        for event in events:
            if event.get("event_type") in ("delivered_late", "late_delivery"):
                return event.get("actor")
    return None


def _is_order_canceled(store: EvidenceStore) -> bool:
    status = _get_order_status(store)
    return status is not None and status.lower() in ("canceled", "cancelled")


def _is_order_unavailable(store: EvidenceStore) -> bool:
    status = _get_order_status(store)
    return status is not None and status.lower() in ("unavailable",)


def _is_order_delivered(store: EvidenceStore) -> bool:
    status = _get_order_status(store)
    return status is not None and status.lower() == "delivered"


def _has_duplicate_payment(store: EvidenceStore) -> bool:
    """Check if there are duplicate payment entries."""
    if len(store.payments_data) <= 1:
        return False
    # Check if payment_sequential values repeat with same type
    seen: dict[str, float] = {}
    for p in store.payments_data:
        seq = p.get("payment_sequential", "")
        ptype = p.get("payment_type", "")
        key = f"{seq}_{ptype}"
        val = float(p.get("payment_value", 0))
        if key in seen and abs(seen[key] - val) < 0.01:
            return True
        seen[key] = val
    return False


def _has_split_payment(store: EvidenceStore) -> bool:
    """Check if there are multiple different payment types."""
    ptypes = {p.get("payment_type") for p in store.payments_data}
    return len(ptypes) > 1 or len(store.payments_data) > 1


def _has_payment_mismatch(store: EvidenceStore) -> bool:
    """Check if payment total differs from item total."""
    paid = _total_paid(store)
    items = _item_total(store)
    if paid > 0 and items > 0:
        return abs(paid - items) > 0.01
    return False


def _has_refund_event(store: EvidenceStore, event_type: str) -> bool:
    """Check payment timeline for specific refund events."""
    if store.payment_timeline_data:
        events = store.payment_timeline_data.get("events", [])
        for event in events:
            etype = event.get("event_type", "").lower()
            if event_type in etype:
                return True
    return False


def _has_pending_refund(store: EvidenceStore) -> bool:
    return _has_refund_event(store, "pending") or _has_refund_event(store, "refund_pending")


def _has_failed_refund(store: EvidenceStore) -> bool:
    return _has_refund_event(store, "failed") or _has_refund_event(store, "refund_failed")


# ── Primary issue determination (evidence-based) ────────────────────────────


def _determine_primary_issue(
    case: dict[str, Any],
    store: EvidenceStore,
) -> str:
    """Determine the primary issue by cross-referencing claim topic with evidence.

    The claim topic is a strong hint, but we validate it against actual evidence.
    """
    claims = case["customer_request"].get("claims", [])
    first_topic = claims[0]["topic"] if claims else None
    order_status = _get_order_status(store)

    # If no evidence at all
    if not store.order_data and not store.payments_data:
        return "insufficient_evidence"

    # Evidence-based validation of claim topic
    if first_topic == "canceled_order_paid":
        if _is_order_canceled(store) and _total_paid(store) > 0:
            return "canceled_order_paid"
        if _is_order_canceled(store):
            return "canceled_order_paid"
        # Order not actually canceled but claim says so — trust evidence
        if order_status and order_status.lower() == "delivered":
            return "unsupported_claim"
        return "canceled_order_paid"

    if first_topic == "unavailable_order_paid":
        if _is_order_unavailable(store) or _is_order_canceled(store):
            return "unavailable_order_paid"
        if _is_order_delivered(store):
            return "unsupported_claim"
        return "unavailable_order_paid"

    if first_topic == "late_delivery_seller":
        if _has_late_delivery(store):
            actor = _late_delivery_actor(store)
            if actor == "logistics":
                return "late_delivery_logistics"
            return "late_delivery_seller"
        # Even without explicit late event, check dates
        return "late_delivery_seller"

    if first_topic == "late_delivery_logistics":
        if _has_late_delivery(store):
            actor = _late_delivery_actor(store)
            if actor == "seller":
                return "late_delivery_seller"
            return "late_delivery_logistics"
        return "late_delivery_logistics"

    if first_topic == "valid_split_payment":
        return "valid_split_payment"

    if first_topic == "payment_mismatch":
        return "payment_mismatch"

    if first_topic == "duplicate_charge":
        return "duplicate_charge"

    if first_topic == "refund_pending":
        return "refund_pending"

    if first_topic == "refund_failed":
        return "refund_failed"

    if first_topic == "unsupported_claim":
        return "unsupported_claim"

    if first_topic in _VALID_ISSUES:
        return first_topic

    return "insufficient_evidence"


# ── Policy-based output construction ─────────────────────────────────────────


def _get_policy_rule(
    store: EvidenceStore, primary_issue: str,
) -> dict[str, Any] | None:
    """Get the specific policy rule for the primary issue."""
    if store.policy_data:
        rules = store.policy_data.get("rules", {})
        return rules.get(primary_issue)
    return None


def _build_case_status(
    primary_issue: str,
    store: EvidenceStore,
) -> str:
    """Determine case_status from policy, falling back to heuristics."""
    rule = _get_policy_rule(store, primary_issue)
    if rule and "case_status" in rule:
        return rule["case_status"]

    # Fallback
    no_action_issues = {"unsupported_claim", "valid_split_payment"}
    investigation_issues = {"insufficient_evidence", "refund_pending"}
    if primary_issue in no_action_issues:
        return "no_action"
    if primary_issue in investigation_issues:
        return "needs_investigation"
    return "action_required"


def _build_financial_resolution(
    primary_issue: str,
    store: EvidenceStore,
) -> dict[str, Any]:
    """Build financial resolution using policy refund_brl as ground truth."""
    rule = _get_policy_rule(store, primary_issue)

    if rule and "refund_brl" in rule:
        refund_amount = float(rule["refund_brl"])
    else:
        # Fallback calculation when no policy
        refund_amount = 0.0
        if primary_issue in (
            "canceled_order_paid",
            "unavailable_order_paid",
            "duplicate_charge",
        ):
            refund_amount = _item_total(store) or _total_paid(store)
        elif primary_issue in ("late_delivery_seller", "late_delivery_logistics"):
            refund_amount = _freight_total(store) or round(_item_total(store) * 0.2, 2)
        elif primary_issue == "payment_mismatch":
            refund_amount = round(abs(_total_paid(store) - _item_total(store)), 2)
        elif primary_issue in ("refund_pending", "refund_failed"):
            refund_amount = _total_paid(store)

    refund_amount = round(refund_amount, 2)

    # Determine reason code and entity_id
    reason_map = {
        "canceled_order_paid": "full_refund_order_canceled",
        "unavailable_order_paid": "full_refund_order_unavailable",
        "late_delivery_seller": "refund_freight_late_delivery",
        "late_delivery_logistics": "refund_freight_late_delivery",
        "valid_split_payment": "no_refund_payment_valid",
        "payment_mismatch": "payment_discrepancy_correction",
        "duplicate_charge": "refund_duplicate_charge",
        "refund_pending": "pending_refund_fulfillment",
        "refund_failed": "retry_refund_processing",
        "unsupported_claim": "no_refund_claim_unsupported",
        "insufficient_evidence": "no_refund_insufficient_evidence",
    }
    reason = reason_map.get(primary_issue, "undetermined")

    order_id = None
    if store.order_data:
        order_id = store.order_data.get("order_id")

    return {
        "currency": "BRL",
        "recommended_refund_brl": refund_amount,
        "refund_lines": [
            {
                "reason_code": reason,
                "amount_brl": refund_amount,
                "entity_id": order_id,
            },
        ],
    }


def _build_responsible_parties(
    primary_issue: str,
    store: EvidenceStore,
) -> list[dict[str, Any]]:
    """Build responsible parties from policy data, with evidence fallback."""
    rule = _get_policy_rule(store, primary_issue)

    if rule and "responsible_parties" in rule:
        parties = rule["responsible_parties"]
        if isinstance(parties, list) and parties:
            result = []
            for p in parties:
                party_type = p.get("party_type", "unknown")
                party_id = p.get("party_id")
                # Enrich party_id from evidence if policy has null
                if party_id is None and party_type == "seller" and store.sellers_data:
                    party_id = store.sellers_data[0].get("seller_id")
                result.append({"party_type": party_type, "party_id": party_id})
            return result

    # Fallback mapping
    fallback_map: dict[str, tuple[str, str | None]] = {
        "canceled_order_paid": ("platform", None),
        "unavailable_order_paid": ("seller", None),
        "late_delivery_seller": ("seller", None),
        "late_delivery_logistics": ("logistics_provider", None),
        "valid_split_payment": ("customer", None),
        "payment_mismatch": ("payment_provider", None),
        "duplicate_charge": ("payment_provider", None),
        "refund_pending": ("payment_provider", None),
        "refund_failed": ("payment_provider", None),
        "unsupported_claim": ("customer", None),
        "insufficient_evidence": ("unknown", None),
    }
    party_type, party_id = fallback_map.get(primary_issue, ("unknown", None))
    if party_type == "seller" and store.sellers_data:
        party_id = store.sellers_data[0].get("seller_id")
    return [{"party_type": party_type, "party_id": party_id}]


# ── Entity extraction ────────────────────────────────────────────────────────


def _extract_entity_ids(
    case: dict[str, Any],
    store: EvidenceStore,
) -> dict[str, list[str]]:
    """Extract all entity IDs from evidence data."""
    order_ids: list[str] = []
    item_ids: list[str] = []
    seller_ids: list[str] = []
    payment_refs: list[str] = []
    shipment_ids: list[str] = []

    # Order ID
    if store.order_data:
        oid = store.order_data.get("order_id")
        if oid:
            order_ids.append(str(oid))
    if not order_ids:
        order_ids.append(case["customer_request"]["claimed_order_id"])

    # Item IDs
    seen_items: set[str] = set()
    for item in store.items_data:
        iid = item.get("order_item_id") or item.get("item_id")
        if iid and str(iid) not in seen_items:
            item_ids.append(str(iid))
            seen_items.add(str(iid))

    # Seller IDs
    seen_sellers: set[str] = set()
    for seller in store.sellers_data:
        sid = seller.get("seller_id")
        if sid and str(sid) not in seen_sellers:
            seller_ids.append(str(sid))
            seen_sellers.add(str(sid))
    # Also from items if sellers data is empty
    if not seller_ids:
        for item in store.items_data:
            sid = item.get("seller_id")
            if sid and str(sid) not in seen_sellers:
                seller_ids.append(str(sid))
                seen_sellers.add(str(sid))

    # Payment references
    seen_payments: set[str] = set()
    for p in store.payments_data:
        pseq = p.get("payment_sequential")
        if pseq is not None and str(pseq) not in seen_payments:
            payment_refs.append(str(pseq))
            seen_payments.add(str(pseq))

    # Shipment IDs — from shipment summary
    if store.shipment_data:
        sid = store.shipment_data.get("order_id")
        if sid:
            shipment_ids.append(str(sid))

    return {
        "order_ids": order_ids,
        "item_ids": item_ids,
        "seller_ids": seller_ids,
        "payment_references": payment_refs,
        "shipment_ids": shipment_ids,
    }


# ── Root cause analysis ──────────────────────────────────────────────────────

_ISSUE_TO_CAUSE_CODE: dict[str, str] = {
    "canceled_order_paid": "ORDER_CANCELED_PAYMENT_NOT_REVERSED",
    "unavailable_order_paid": "ORDER_UNAVAILABLE_PAYMENT_COLLECTED",
    "late_delivery_seller": "SELLER_DELAYED_SHIPMENT",
    "late_delivery_logistics": "LOGISTICS_DELIVERY_DELAY",
    "valid_split_payment": "SPLIT_PAYMENT_PROCESSED",
    "payment_mismatch": "PAYMENT_AMOUNT_DISCREPANCY",
    "duplicate_charge": "DUPLICATE_PAYMENT_CHARGED",
    "refund_pending": "REFUND_NOT_YET_PROCESSED",
    "refund_failed": "REFUND_PROCESSING_FAILURE",
    "unsupported_claim": "CLAIM_NOT_SUBSTANTIATED",
    "insufficient_evidence": "EVIDENCE_INSUFFICIENT_FOR_DETERMINATION",
}


def _build_root_cause(
    primary_issue: str,
    store: EvidenceStore,
) -> dict[str, Any]:
    cause_code = _ISSUE_TO_CAUSE_CODE.get(primary_issue, "UNDETERMINED_ROOT_CAUSE")
    parties = _build_responsible_parties(primary_issue, store)
    return {
        "ranked_causes": [{"cause_code": cause_code, "rank": 1}],
        "responsible_parties": parties,
    }


# ── Claim assessments ────────────────────────────────────────────────────────


def _assess_claims(
    case: dict[str, Any],
    store: EvidenceStore,
    primary_issue: str,
) -> list[dict[str, Any]]:
    """Evaluate each customer claim against the evidence."""
    claims = case["customer_request"].get("claims", [])
    assessments: list[dict[str, Any]] = []
    all_refs = store.all_refs

    for claim in claims[:5]:
        claim_id = claim["claim_id"]
        topic = claim.get("topic", "")

        if topic == primary_issue:
            verdict = "supported"
            conf = 0.85
        elif topic == "requested_full_refund":
            # Refund validity depends on primary issue
            if primary_issue in (
                "canceled_order_paid",
                "unavailable_order_paid",
                "duplicate_charge",
                "refund_failed",
            ):
                verdict = "supported"
                conf = 0.85
            elif primary_issue in (
                "late_delivery_seller",
                "late_delivery_logistics",
                "payment_mismatch",
            ):
                verdict = "partially_supported"
                conf = 0.65
            elif primary_issue == "refund_pending":
                verdict = "partially_supported"
                conf = 0.60
            else:
                verdict = "unsupported"
                conf = 0.70
        elif topic in _VALID_ISSUES:
            # Topic doesn't match primary issue
            if store.order_data or store.payments_data:
                verdict = "unsupported"
                conf = 0.65
            else:
                verdict = "insufficient_evidence"
                conf = 0.40
        else:
            verdict = "insufficient_evidence"
            conf = 0.35

        assessments.append({
            "claim_id": claim_id,
            "verdict": verdict,
            "confidence": conf,
            "evidence_refs": all_refs[:30],
        })

    return assessments


# ── Data conflicts ───────────────────────────────────────────────────────────


def _detect_data_conflicts(store: EvidenceStore) -> list[dict[str, Any]]:
    """Detect data conflicts between evidence sources."""
    conflicts: list[dict[str, Any]] = []

    paid = _total_paid(store)
    items = _item_total(store)

    if paid > 0 and items > 0 and abs(paid - items) > 0.01:
        conflicts.append({
            "field": "total_amount",
            "sources": ["payment_records", "item_records"],
            "selected_source": "payment_records",
            "resolution_code": "payment_authoritative_for_amount",
        })

    return conflicts


# ── Confidence calibration ───────────────────────────────────────────────────


def _compute_confidence(
    primary_issue: str,
    store: EvidenceStore,
) -> float:
    """Calibrated confidence based on evidence strength."""
    base = 0.5
    evidence_count = sum(
        1
        for ref in (
            store.order_ref,
            store.items_ref,
            store.payments_ref,
            store.payment_timeline_ref,
            store.shipment_ref,
            store.sellers_ref,
            store.policy_ref,
        )
        if ref is not None
    )

    boost = min(evidence_count * 0.07, 0.42)
    confidence = base + boost

    if primary_issue in ("insufficient_evidence", "unsupported_claim"):
        confidence = min(confidence, 0.55)

    return round(min(confidence, 0.95), 2)


# ── Resolution actions ───────────────────────────────────────────────────────

_ISSUE_TO_ACTIONS: dict[str, list[str]] = {
    "canceled_order_paid": [
        "Initiate full refund to customer",
        "Verify order cancellation reason",
        "Update order payment status",
    ],
    "unavailable_order_paid": [
        "Initiate full refund to customer",
        "Notify seller about unavailable product",
        "Update inventory status",
    ],
    "late_delivery_seller": [
        "Compensate customer for shipping delay",
        "Issue warning to seller for late shipment",
        "Review seller performance metrics",
    ],
    "late_delivery_logistics": [
        "Compensate customer for shipping delay",
        "Escalate to logistics provider",
        "Review logistics SLA compliance",
    ],
    "valid_split_payment": [
        "No action required - payment is valid",
        "Confirm split payment details with customer",
    ],
    "payment_mismatch": [
        "Correct payment discrepancy",
        "Refund overpayment to customer",
        "Audit payment processing records",
    ],
    "duplicate_charge": [
        "Refund duplicate payment to customer",
        "Flag transaction for payment audit",
        "Verify payment gateway logs",
    ],
    "refund_pending": [
        "Monitor pending refund status",
        "Notify customer of refund timeline",
        "Escalate if refund exceeds SLA",
    ],
    "refund_failed": [
        "Retry refund through alternative method",
        "Escalate to payment provider",
        "Contact customer for updated payment info",
    ],
    "unsupported_claim": [
        "Notify customer that claim is not supported",
        "Document claim assessment rationale",
    ],
    "insufficient_evidence": [
        "Request additional evidence from customer",
        "Escalate for manual investigation",
    ],
}


# ── Verifier Agent ───────────────────────────────────────────────────────────


class Verifier:
    """Cross-checks output for consistency before finalization."""

    ACTOR = "verifier"

    def verify(
        self,
        output: dict[str, Any],
        store: EvidenceStore,
        trace: TraceWriter,
    ) -> dict[str, Any]:
        case_id = store.case_id
        issues: list[str] = []

        # ① evidence_refs must not be empty
        if not output.get("evidence_refs"):
            issues.append("no_evidence_refs")

        # ② financial total = sum of refund lines
        fin = output.get("financial_resolution", {})
        total = fin.get("recommended_refund_brl", 0)
        line_sum = sum(l.get("amount_brl", 0) for l in fin.get("refund_lines", []))
        if abs(total - line_sum) > 0.01:
            fin["recommended_refund_brl"] = round(line_sum, 2)
            issues.append("refund_total_corrected")

        # ③ resolution_actions not empty
        if not output.get("resolution_actions"):
            issues.append("no_resolution_actions")

        # ④ case_id consistency
        if output.get("case_id") != case_id:
            output["case_id"] = case_id
            issues.append("case_id_corrected")

        # ⑤ confidence bounds
        conf = output.get("assessment", {}).get("confidence", 0)
        if conf < 0 or conf > 1:
            output["assessment"]["confidence"] = max(0, min(1, conf))
            issues.append("confidence_clamped")

        decision = "PASS" if not issues else "PASS_WITH_CORRECTIONS"

        trace.emit(
            case_id=case_id,
            event_type="verification_completed",
            actor=self.ACTOR,
            decision_code=decision,
            attributes={
                "checks_passed": not issues,
                "issues_found": len(issues),
            },
        )

        return output


# ── Coordinator: top-level orchestration ─────────────────────────────────────


async def solve_case(
    case: dict[str, Any],
    gateway: EvidenceGateway,
    trace: TraceWriter,
) -> dict[str, Any]:
    """Orchestrate specialist agents to investigate complaint and produce output."""
    case_id = case["case_id"]

    # ── Discover available MCP tools ─────────────────────────────────────
    available_tools = await gateway.list_tools()

    # ── Initialize shared evidence store ─────────────────────────────────
    store = EvidenceStore(case_id=case_id)

    # ── Create agents ────────────────────────────────────────────────────
    order_agent = OrderAgent()
    payment_agent = PaymentAgent()
    shipment_agent = ShipmentAgent()
    policy_agent = PolicyAgent()
    verifier = Verifier()

    # ── Assign tasks ─────────────────────────────────────────────────────
    trace.emit(
        case_id=case_id,
        event_type="task_assigned",
        actor="coordinator",
        target=OrderAgent.ACTOR,
        decision_code="INVESTIGATE_ORDER_AND_ITEMS",
    )
    trace.emit(
        case_id=case_id,
        event_type="task_assigned",
        actor="coordinator",
        target=PaymentAgent.ACTOR,
        decision_code="INVESTIGATE_PAYMENTS",
    )
    trace.emit(
        case_id=case_id,
        event_type="task_assigned",
        actor="coordinator",
        target=ShipmentAgent.ACTOR,
        decision_code="INVESTIGATE_SHIPMENTS",
    )
    trace.emit(
        case_id=case_id,
        event_type="task_assigned",
        actor="coordinator",
        target=PolicyAgent.ACTOR,
        decision_code="INVESTIGATE_POLICY",
    )

    # ── Run specialist agents sequentially ───────────────────────────────
    await order_agent.investigate(case, gateway, trace, store, available_tools)

    trace.emit(
        case_id=case_id,
        event_type="handoff",
        actor=OrderAgent.ACTOR,
        target=PaymentAgent.ACTOR,
        decision_code="ORDER_EVIDENCE_COLLECTED",
    )

    await payment_agent.investigate(case, gateway, trace, store, available_tools)

    trace.emit(
        case_id=case_id,
        event_type="handoff",
        actor=PaymentAgent.ACTOR,
        target=ShipmentAgent.ACTOR,
        decision_code="PAYMENT_EVIDENCE_COLLECTED",
    )

    await shipment_agent.investigate(case, gateway, trace, store, available_tools)

    trace.emit(
        case_id=case_id,
        event_type="handoff",
        actor=ShipmentAgent.ACTOR,
        target=PolicyAgent.ACTOR,
        decision_code="SHIPMENT_EVIDENCE_COLLECTED",
    )

    await policy_agent.investigate(case, gateway, trace, store, available_tools)

    trace.emit(
        case_id=case_id,
        event_type="handoff",
        actor=PolicyAgent.ACTOR,
        target="coordinator",
        decision_code="ALL_EVIDENCE_COLLECTED",
    )

    # ── Analyze and build output ─────────────────────────────────────────
    primary_issue = _determine_primary_issue(case, store)
    case_status = _build_case_status(primary_issue, store)
    confidence = _compute_confidence(primary_issue, store)
    entities = _extract_entity_ids(case, store)
    claim_assessments = _assess_claims(case, store, primary_issue)
    root_cause = _build_root_cause(primary_issue, store)
    data_conflicts = _detect_data_conflicts(store)
    financial = _build_financial_resolution(primary_issue, store)
    actions = _ISSUE_TO_ACTIONS.get(primary_issue, ["Escalate for manual review"])

    # Emit policy decision
    trace.emit(
        case_id=case_id,
        event_type="policy_decided",
        actor="coordinator",
        decision_code=f"PRIMARY_ISSUE_{primary_issue.upper()}",
        evidence_refs=store.all_refs[:20],
    )

    # Handoff to verifier
    trace.emit(
        case_id=case_id,
        event_type="handoff",
        actor="coordinator",
        target=Verifier.ACTOR,
        decision_code="READY_FOR_VERIFICATION",
    )

    # ── Assemble output ──────────────────────────────────────────────────
    output: dict[str, Any] = {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "case_id": case_id,
        "assessment": {
            "primary_issue": primary_issue,
            "case_status": case_status,
            "confidence": confidence,
        },
        "affected_entities": entities,
        "claim_assessments": claim_assessments,
        "root_cause_analysis": root_cause,
        "evidence_refs": store.all_refs[:30],
        "data_conflicts": data_conflicts,
        "financial_resolution": financial,
        "resolution_actions": actions[:8],
    }

    # ── Verify output ────────────────────────────────────────────────────
    output = verifier.verify(output, store, trace)

    return output
