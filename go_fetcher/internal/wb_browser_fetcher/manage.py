import atexit
import json
import os
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, jsonify, request

from wb_browser_fetcher.app.browser import WBBrowser


def resolve_cookie_path() -> str:
    env_path = os.getenv("WB_COOKIE_PATH")
    if env_path:
        return str(Path(env_path).expanduser().resolve())

    docker_path = Path("/app/secrets/wb_cookie.txt")
    if docker_path.exists():
        return str(docker_path)

    return str(Path(__file__).resolve().parents[2] / "secrets" / "wb_cookie.txt")


def is_allowed_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.hostname in {
        "wildberries.ru",
        "www.wildberries.ru",
        "search.wb.ru",
    }


app = Flask(__name__)
browser = WBBrowser(resolve_cookie_path())
browser.start()
atexit.register(browser.stop)


def classify_fetch_error(error: BaseException | str) -> str:
    error_text = str(error or "").lower()
    if (
        "status is 403" in error_text
        or "status is 498" in error_text
        or "antibot" in error_text
        or "angie" in error_text
    ):
        return "blocked_by_antibot"
    if (
        "validation" in error_text
        or "invalid" in error_text
        or "not wildberries json" in error_text
        or "does not contain" in error_text
        or "product catalog" in error_text
    ):
        return "parser_response_invalid"
    if "timeout" in error_text or "deadline exceeded" in error_text:
        return "browser_fallback_timeout"
    return "browser_fallback_error"


@app.post("/api/v1/fetch")
def fetch():
    data = request.get_json(silent=True) or {}
    url = str(data.get("url") or "").strip()
    try:
        request_timeout_ms = int(data.get("request_timeout_ms") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "request_timeout_ms must be an integer"}), 400
    if not is_allowed_url(url):
        return jsonify({"error": "url must be an allowed Wildberries HTTPS URL"}), 400

    try:
        print(
            "WB browser fetch requested: "
            f"url={url}, request_timeout_ms={request_timeout_ms}",
            flush=True,
        )
        result = browser.fetch(url, request_timeout_ms)
        body_text = str(result.get("body") or "")
        try:
            body = json.loads(body_text)
        except json.JSONDecodeError:
            body = body_text

        return jsonify(
            {
                "status_code": int(result.get("status_code") or 0),
                "body": body,
                "requested_url": str(result.get("requested_url") or url),
                "final_url": str(result.get("final_url") or ""),
                "content_type": str(result.get("content_type") or ""),
                "response_size": int(result.get("response_size") or 0),
                "document_title": str(result.get("document_title") or ""),
                "response_kind": str(result.get("response_kind") or ""),
                "requested_nm_id": str(result.get("requested_nm_id") or ""),
                "parsed_nm_id": str(result.get("parsed_nm_id") or ""),
                "json_decode_success": bool(result.get("json_decode_success")),
                "resultset": str(result.get("resultset") or ""),
                "products_count": int(result.get("products_count") or 0),
            }
        )
    except Exception as exc:
        error_type = classify_fetch_error(exc)
        print(
            f"WB browser fetch failed: error_type={error_type}, error={exc}",
            flush=True,
        )
        return jsonify({"error": str(exc), "error_type": error_type}), 500


@app.get("/api/v1/health")
def health():
    health_data = browser.get_health_snapshot()
    status_code = 200 if health_data["status"] == "ok" else 503
    return jsonify(health_data), status_code


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8096, threaded=False, debug=False)
