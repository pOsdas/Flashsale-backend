from flask import Blueprint, jsonify, request

from ozon_browser_fetcher.app.browser.worker import get_browser_worker


bp = Blueprint("api", __name__)


@bp.route("/api/v1/product", methods=["POST"])
def product():
    data = request.get_json(silent=True) or {}

    url = data.get("url")
    timeout_seconds = int(data.get("timeout_seconds", 90))

    if not url:
        return jsonify({"error": "url is required"}), 400

    worker = get_browser_worker()

    try:
        result = worker.parse_product(
            url=url,
            timeout_seconds=timeout_seconds,
        )

        if result.get("ok"):
            return jsonify(result["data"]), 200

        return jsonify(
            {
                "error": result.get("error", "unknown parser error"),
                "trace": result.get("trace", ""),
            }
        ), 500

    except TimeoutError as exc:
        return jsonify({"error": str(exc)}), 504

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/v1/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200
