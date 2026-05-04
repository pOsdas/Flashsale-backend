import hashlib
import json
from typing import Any


def make_idempotency_hash(payload: dict[str, Any]) -> str:
    """
    returns payload hash
    """
    normalized_payload = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    return hashlib.sha256(
        normalized_payload.encode("utf-8"),
    ).hexdigest()


def compare_idempotency_payloads(
        *,
        original_payload_hash: str,
        current_payload: dict[str, Any],
) -> bool:
    current_payload_hash = make_idempotency_hash(current_payload)
    return original_payload_hash == current_payload_hash
