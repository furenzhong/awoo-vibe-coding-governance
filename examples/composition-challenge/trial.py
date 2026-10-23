"""Composition-behavior trial fixtures.

The buggy implementations are intentionally plausible and are never product code.
The trial first runs local component checks, then black-box checks derived from
the user-facing contract.  A useful governance method must fail the buggy
implementation and pass the corrected one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable


class BuggyCheckoutApi:
    """Looks tidy, but treats a yuan value as if it were already cents."""

    def __init__(self, gateway: "PaymentGateway") -> None:
        self.gateway = gateway

    def create_order(self, amount_yuan: float) -> int:
        amount_cents = int(round(amount_yuan))
        return self.gateway.charge_cents(amount_cents)


class CorrectCheckoutApi(BuggyCheckoutApi):
    def create_order(self, amount_yuan: float) -> int:
        amount_cents = int(round(amount_yuan * 100))
        return self.gateway.charge_cents(amount_cents)


class PaymentGateway:
    def __init__(self) -> None:
        self.charges: list[int] = []

    def charge_cents(self, amount_cents: int) -> int:
        self.charges.append(amount_cents)
        return amount_cents


class DocumentStore:
    def __init__(self, fail_commit: bool = False) -> None:
        self.fail_commit = fail_commit
        self.documents: dict[str, str] = {}

    def commit(self, document_id: str, body: str) -> None:
        if self.fail_commit:
            raise RuntimeError("store unavailable")
        self.documents[document_id] = body


class BuggyDocumentApi:
    """Returns saved before the worker has made persistence durable."""

    def __init__(self, store: DocumentStore) -> None:
        self.store = store
        self.queue: list[tuple[str, str]] = []

    def save(self, document_id: str, body: str) -> dict[str, str]:
        self.queue.append((document_id, body))
        return {"status": "saved"}

    def run_worker(self) -> None:
        while self.queue:
            document_id, body = self.queue.pop(0)
            self.store.commit(document_id, body)

    def read(self, document_id: str) -> str | None:
        return self.store.documents.get(document_id)


class CorrectDocumentApi(BuggyDocumentApi):
    def save(self, document_id: str, body: str) -> dict[str, str]:
        try:
            self.store.commit(document_id, body)
        except RuntimeError:
            return {"status": "error"}
        return {"status": "saved"}

    def run_worker(self) -> None:
        return None


class BuggyGateway:
    def __init__(self, fail_after_charge: bool) -> None:
        self.fail_after_charge = fail_after_charge
        self.charges: list[tuple[str, int]] = []
        self.calls = 0

    def charge(self, key: str, amount_cents: int) -> str:
        self.calls += 1
        self.charges.append((key, amount_cents))
        if self.fail_after_charge and self.calls == 1:
            raise TimeoutError("response lost after charge")
        return f"charge-{len(self.charges)}"


class IdempotentGateway(BuggyGateway):
    def charge(self, key: str, amount_cents: int) -> str:
        for existing_key, existing_amount in self.charges:
            if existing_key == key:
                assert existing_amount == amount_cents
                return "charge-1"
        return super().charge(key, amount_cents)


class BuggyOrderApi:
    """A retry is locally reasonable, but unsafe after an unknown outcome."""

    def __init__(self, gateway: BuggyGateway) -> None:
        self.gateway = gateway

    def place(self, key: str, amount_cents: int) -> str:
        try:
            return self.gateway.charge(key, amount_cents)
        except TimeoutError:
            return self.gateway.charge(key, amount_cents)


class CorrectOrderApi(BuggyOrderApi):
    pass


@dataclass
class CaseResult:
    name: str
    local_checks_pass: bool
    buggy_contract_failed: bool
    corrected_contract_passed: bool
    finding: str


def local_checkout_checks() -> None:
    gateway = PaymentGateway()
    assert BuggyCheckoutApi(gateway).create_order(1234) == 1234


def checkout_contract(api_factory: Callable[[PaymentGateway], BuggyCheckoutApi]) -> None:
    gateway = PaymentGateway()
    api_factory(gateway).create_order(12.34)
    assert gateway.charges == [1234], gateway.charges


def local_document_checks() -> None:
    store = DocumentStore()
    api = BuggyDocumentApi(store)
    assert api.save("doc-1", "draft") == {"status": "saved"}
    api.run_worker()
    assert api.read("doc-1") == "draft"


def document_contract(api_factory: Callable[[DocumentStore], BuggyDocumentApi]) -> None:
    store = DocumentStore(fail_commit=True)
    api = api_factory(store)
    response = api.save("doc-1", "draft")
    if response == {"status": "saved"}:
        api.run_worker()
        assert api.read("doc-1") == "draft", "saved response without durable data"
    else:
        assert response == {"status": "error"}


def local_order_checks() -> None:
    class FailsBeforeCharge(BuggyGateway):
        def charge(self, key: str, amount_cents: int) -> str:
            if self.calls == 0:
                self.calls += 1
                raise TimeoutError("connection lost before charge")
            return super().charge(key, amount_cents)

    gateway = FailsBeforeCharge(False)
    assert BuggyOrderApi(gateway).place("order-1", 500) == "charge-1"
    assert gateway.charges == [("order-1", 500)]


def order_contract(api_factory: Callable[[BuggyGateway], BuggyOrderApi], gateway_factory: Callable[[], BuggyGateway]) -> None:
    gateway = gateway_factory()
    result = api_factory(gateway).place("order-1", 500)
    assert result == "charge-1"
    assert gateway.charges == [("order-1", 500)], gateway.charges


def run_case(
    name: str,
    local_check: Callable[[], None],
    buggy_check: Callable[[], None],
    corrected_check: Callable[[], None],
    finding: str,
) -> CaseResult:
    local_check()
    buggy_failed = False
    try:
        buggy_check()
    except (AssertionError, RuntimeError, TimeoutError):
        buggy_failed = True
    corrected_passed = True
    try:
        corrected_check()
    except (AssertionError, RuntimeError, TimeoutError):
        corrected_passed = False
    return CaseResult(name, True, buggy_failed, corrected_passed, finding)


def main() -> None:
    results = [
        run_case(
            "currency-boundary",
            local_checkout_checks,
            lambda: checkout_contract(BuggyCheckoutApi),
            lambda: checkout_contract(CorrectCheckoutApi),
            "frontend sends yuan while payment boundary requires cents",
        ),
        run_case(
            "durability-ack",
            local_document_checks,
            lambda: document_contract(BuggyDocumentApi),
            lambda: document_contract(CorrectDocumentApi),
            "success is returned before the queued write is durable",
        ),
        run_case(
            "retry-idempotency",
            local_order_checks,
            lambda: order_contract(BuggyOrderApi, lambda: BuggyGateway(True)),
            lambda: order_contract(CorrectOrderApi, lambda: IdempotentGateway(True)),
            "retry repeats a charge after a response-loss timeout",
        ),
    ]
    payload = {
        "method": "contract-first composition challenge",
        "results": [result.__dict__ for result in results],
        "summary": {
            "local_checks": all(result.local_checks_pass for result in results),
            "buggy_defects_detected": sum(result.buggy_contract_failed for result in results),
            "corrected_false_failures": sum(not result.corrected_contract_passed for result in results),
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
