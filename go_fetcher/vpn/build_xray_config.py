import json
import os
import sys
from pathlib import Path
from typing import Any

INPUT_PATH = Path(os.getenv("XRAY_SUBSCRIPTION_PATH", "/input/subscription.json"))
OUTPUT_PATH = Path(os.getenv("XRAY_RUNTIME_CONFIG_PATH", "/output/config.json"))
PREFERRED_PROXY_TAG = os.getenv("XRAY_PROXY_OUTBOUND_TAG", "proxy").strip() or "proxy"
SOCKS_LISTEN = os.getenv("XRAY_SOCKS_LISTEN", "0.0.0.0").strip() or "0.0.0.0"
SOCKS_PORT = int(os.getenv("XRAY_SOCKS_PORT", "1080"))
LOG_LEVEL = os.getenv("XRAY_LOG_LEVEL", "warning").strip() or "warning"

NON_PROXY_PROTOCOLS = {
    "blackhole",
    "block",
    "direct",
    "dns",
    "freedom",
    "loopback",
}


def fail(message: str) -> "NoReturn":
    print(f"[xray-config-builder] ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        fail(f"subscription file not found: {path}")

    try:
        raw = path.read_text(encoding="utf-8-sig")
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        fail(f"cannot read valid JSON from {path}: {error}")

    if not isinstance(value, dict):
        fail("subscription JSON root must be an object")

    return value


def select_proxy_outbound(outbounds: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    for outbound in outbounds:
        if str(outbound.get("tag", "")).strip() == PREFERRED_PROXY_TAG:
            return outbounds, PREFERRED_PROXY_TAG

    for outbound in outbounds:
        protocol = str(outbound.get("protocol", "")).strip().lower()
        if protocol and protocol not in NON_PROXY_PROTOCOLS:
            current_tag = str(outbound.get("tag", "")).strip()
            if current_tag:
                return outbounds, current_tag

            outbound["tag"] = PREFERRED_PROXY_TAG
            return outbounds, PREFERRED_PROXY_TAG

    fail(
        "no proxy outbound found; expected tag "
        f"{PREFERRED_PROXY_TAG!r} or a non-direct outbound such as vless/vmess/trojan"
    )


def build_runtime_config(subscription: dict[str, Any]) -> tuple[dict[str, Any], str]:
    raw_outbounds = subscription.get("outbounds")
    if not isinstance(raw_outbounds, list) or not raw_outbounds:
        fail("subscription JSON must contain a non-empty 'outbounds' array")

    outbounds: list[dict[str, Any]] = []
    for index, outbound in enumerate(raw_outbounds):
        if not isinstance(outbound, dict):
            fail(f"outbounds[{index}] must be an object")
        outbounds.append(dict(outbound))

    outbounds, proxy_tag = select_proxy_outbound(outbounds)

    runtime_config: dict[str, Any] = {
        "log": {
            "loglevel": LOG_LEVEL,
        },
        "inbounds": [
            {
                "tag": "parser-socks-in",
                "listen": SOCKS_LISTEN,
                "port": SOCKS_PORT,
                "protocol": "socks",
                "settings": {
                    "auth": "noauth",
                    "udp": False,
                },
                "sniffing": {
                    "enabled": True,
                    "destOverride": ["http", "tls"],
                    "routeOnly": True,
                },
            }
        ],
        "outbounds": outbounds,
        "routing": {
            "domainStrategy": "AsIs",
            "rules": [
                {
                    "type": "field",
                    "inboundTag": ["parser-socks-in"],
                    "outboundTag": proxy_tag,
                }
            ],
        },
    }

    return runtime_config, proxy_tag


def main() -> None:
    if not 1 <= SOCKS_PORT <= 65535:
        fail(f"invalid XRAY_SOCKS_PORT: {SOCKS_PORT}")

    subscription = load_json(INPUT_PATH)
    runtime_config, proxy_tag = build_runtime_config(subscription)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = OUTPUT_PATH.with_suffix(OUTPUT_PATH.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(runtime_config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.chmod(0o644)
    temporary_path.replace(OUTPUT_PATH)

    protocols = [
        str(item.get("protocol", "unknown"))
        for item in runtime_config["outbounds"]
    ]
    print(
        "[xray-config-builder] config generated: "
        f"output={OUTPUT_PATH}, socks={SOCKS_LISTEN}:{SOCKS_PORT}, "
        f"proxy_tag={proxy_tag!r}, outbound_protocols={protocols}"
    )


if __name__ == "__main__":
    main()
