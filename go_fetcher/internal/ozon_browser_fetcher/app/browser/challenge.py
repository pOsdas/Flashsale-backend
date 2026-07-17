import os
import time
from typing import Dict, Optional

from playwright.sync_api import Page


CHALLENGE_TITLE_MARKERS = {
    "antibot challenge page",
    "antibot page",
}

REJECTED_TITLE_MARKERS = {
    "похоже, нет соединения",
}

CHALLENGE_BODY_MARKERS = {
    "проверяем ваш браузер",
    "antibot challenge",
}

REJECTED_BODY_MARKERS = {
    "похоже, нет соединения",
}


def get_challenge_timeout_ms() -> int:
    raw_value = os.getenv(
        "OZON_BROWSER_CHALLENGE_TIMEOUT_MS",
        "25000",
    )

    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return 25_000

    return value if value > 0 else 25_000


def get_page_state(page: Page) -> Dict[str, object]:
    try:
        return page.evaluate(
            r"""
            () => ({
                title: document.title || "",
                ready_state: document.readyState || "",
                body_length: document.body
                    ? (document.body.innerText || "").length
                    : 0,
                body_prefix: document.body
                    ? (document.body.innerText || "").slice(0, 500)
                    : ""
            })
            """
        )
    except Exception:
        return {
            "title": "",
            "ready_state": "",
            "body_length": 0,
            "body_prefix": "",
        }


def wait_for_ozon_page_ready(
    page: Page,
    *,
    timeout_ms: Optional[int] = None,
) -> Dict[str, object]:
    safe_timeout_ms = (
        timeout_ms
        if timeout_ms is not None and timeout_ms > 0
        else get_challenge_timeout_ms()
    )
    deadline = time.monotonic() + safe_timeout_ms / 1000
    challenge_seen = False
    last_state: Dict[str, object] = {}

    while time.monotonic() < deadline:
        current_url = page.url
        state = get_page_state(page)
        title = str(state.get("title") or "").strip()
        lowered_title = title.lower()
        body_prefix = str(
            state.get("body_prefix") or ""
        ).lower()
        body_length = int(state.get("body_length") or 0)
        ready_state = str(state.get("ready_state") or "")

        last_state = {
            "url": current_url,
            "title": title,
            "ready_state": ready_state,
            "body_length": body_length,
            "challenge_seen": challenge_seen,
        }

        if (
            any(
                marker in lowered_title
                for marker in REJECTED_TITLE_MARKERS
            )
            or any(
                marker in body_prefix
                for marker in REJECTED_BODY_MARKERS
            )
        ):
            raise RuntimeError(
                "Ozon rejected browser fingerprint: "
                f"url={current_url}, title={title!r}"
            )

        url_looks_like_pending_challenge = bool(
            "__rr=" in current_url
            and "abt_att=1" not in current_url
            and (
                not title
                or lowered_title.startswith("loading ")
                or body_length < 200
            )
        )
        is_challenge = bool(
            any(
                marker in lowered_title
                for marker in CHALLENGE_TITLE_MARKERS
            )
            or any(
                marker in body_prefix
                for marker in CHALLENGE_BODY_MARKERS
            )
            or url_looks_like_pending_challenge
        )

        if is_challenge:
            challenge_seen = True
            time.sleep(0.15)
            continue

        is_loading_title = (
            not title
            or lowered_title.startswith("loading ")
        )
        document_ready = ready_state in {
            "interactive",
            "complete",
        }
        accepted_challenge = "abt_att=1" in current_url
        meaningful_document = body_length >= 200

        if (
            not is_loading_title
            and document_ready
            and meaningful_document
        ):
            if challenge_seen:
                print(
                    "Ozon antibot challenge passed: "
                    f"url={current_url}, title={title!r}",
                    flush=True,
                )
            return last_state

        if accepted_challenge and not is_loading_title:
            return last_state

        time.sleep(0.15)

    raise TimeoutError(
        "Ozon page did not become ready after browser challenge: "
        f"timeout_ms={safe_timeout_ms}, "
        f"last_state={last_state}"
    )
