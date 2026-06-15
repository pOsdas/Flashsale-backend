import argparse
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright


MARKETPLACE_CONFIG: Dict[str, Dict[str, str]] = {
    "wb": {
        "url": "https://www.wildberries.ru",
        "default_output": "secrets/wb_cookie.txt",
        "profile_dir": "tools/playwright/edge_profiles/wb",
    },
    "ozon": {
        "url": "https://www.ozon.ru",
        "default_output": "secrets/ozon_cookie.txt",
        "profile_dir": "tools/playwright/edge_profiles/ozon",
    },
}


DEFAULT_EDGE_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def get_go_fetcher_root() -> Path:
    """
    parents[0] -> playwright
    parents[1] -> tools
    parents[2] -> go_fetcher
    """
    return Path(__file__).resolve().parents[2]


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Marketplace cookie updater for Wildberries and Ozon. "
            "Launches Microsoft Edge with remote debugging, opens marketplace, "
            "then saves cookies as HTTP Cookie header."
        )
    )

    parser.add_argument(
        "--marketplace",
        required=True,
        choices=sorted(MARKETPLACE_CONFIG.keys()),
        help="Marketplace name: wb or ozon.",
    )

    parser.add_argument(
        "--output",
        default=None,
        help=(
            "Optional output path for cookie file. "
            "If not provided, marketplace default path will be used."
        ),
    )

    parser.add_argument(
        "--cdp-port",
        type=int,
        default=9222,
        help="Microsoft Edge remote debugging port. Default: 9222.",
    )

    parser.add_argument(
        "--edge-path",
        default=None,
        help="Optional path to msedge.exe.",
    )

    parser.add_argument(
        "--keep-open",
        action="store_true",
        help="Keep Microsoft Edge opened after cookies are saved.",
    )

    return parser


def resolve_output_path(marketplace: str, custom_output: Optional[str]) -> Path:
    go_fetcher_root = get_go_fetcher_root()

    if custom_output:
        output_path = Path(custom_output).expanduser()

        if not output_path.is_absolute():
            output_path = go_fetcher_root / output_path

        return output_path.resolve()

    default_output = MARKETPLACE_CONFIG[marketplace]["default_output"]

    return (go_fetcher_root / default_output).resolve()


def resolve_profile_path(marketplace: str) -> Path:
    go_fetcher_root = get_go_fetcher_root()
    profile_dir = MARKETPLACE_CONFIG[marketplace]["profile_dir"]

    return (go_fetcher_root / profile_dir).resolve()


def resolve_edge_path(custom_edge_path: Optional[str]) -> Path:
    if custom_edge_path:
        edge_path = Path(custom_edge_path).expanduser().resolve()

        if not edge_path.exists():
            raise RuntimeError(f"Microsoft Edge executable not found: {edge_path}")

        return edge_path

    for path_value in DEFAULT_EDGE_PATHS:
        edge_path = Path(path_value)

        if edge_path.exists():
            return edge_path

    raise RuntimeError(
        "Microsoft Edge executable was not found automatically. "
        "Pass it manually with --edge-path."
    )


def is_cdp_available(cdp_port: int) -> bool:
    url = f"http://127.0.0.1:{cdp_port}/json/version"

    try:
        with urllib.request.urlopen(url, timeout=1) as response:
            return response.status == 200
    except Exception:
        return False


def wait_for_cdp(cdp_port: int, timeout_seconds: int = 15) -> None:
    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        if is_cdp_available(cdp_port=cdp_port):
            return

        time.sleep(0.3)

    raise RuntimeError(
        f"Microsoft Edge did not start remote debugging on port {cdp_port}."
    )


def launch_edge_with_cdp(
    edge_path: Path,
    profile_path: Path,
    cdp_port: int,
    start_url: str,
) -> subprocess.Popen:
    profile_path.mkdir(parents=True, exist_ok=True)

    command = [
        str(edge_path),
        f"--remote-debugging-port={cdp_port}",
        f"--user-data-dir={profile_path}",
        "--no-first-run",
        "--no-default-browser-check",
        start_url,
    ]

    process = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    wait_for_cdp(cdp_port=cdp_port)

    return process


def get_or_create_page(browser: Browser, site_url: str) -> Page:
    if not browser.contexts:
        context = browser.new_context()
        page = context.new_page()
        page.goto(site_url, wait_until="domcontentloaded", timeout=60_000)
        return page

    context = browser.contexts[0]

    for page in context.pages:
        current_url = page.url.lower()

        if "wildberries" in current_url or "ozon" in current_url:
            return page

    page = context.new_page()
    page.goto(site_url, wait_until="domcontentloaded", timeout=60_000)

    return page


def get_main_context(browser: Browser) -> BrowserContext:
    if not browser.contexts:
        return browser.new_context()

    return browser.contexts[0]


def format_cookie_header(cookies: List[dict]) -> str:
    """
    Преобразует cookies из browser context в одну строку формата HTTP Cookie header:

    name1=value1; name2=value2; name3=value3
    """
    cookie_parts: List[str] = []

    for cookie in cookies:
        name = cookie.get("name")
        value = cookie.get("value")

        if not name:
            continue

        if value is None:
            value = ""

        cookie_parts.append(f"{name}={value}")

    return "; ".join(cookie_parts)


def extract_cookie_names(cookie_header: str) -> List[str]:
    cookie_names: List[str] = []

    for cookie_part in cookie_header.split(";"):
        cookie_part = cookie_part.strip()

        if not cookie_part:
            continue

        if "=" not in cookie_part:
            continue

        cookie_name = cookie_part.split("=", 1)[0].strip()

        if cookie_name:
            cookie_names.append(cookie_name)

    return sorted(set(cookie_names))


def validate_cookie_header(cookie_header: str) -> None:
    if not cookie_header:
        raise RuntimeError("Cookie header is empty.")

    if "=" not in cookie_header:
        raise RuntimeError(
            "Cookie header does not look valid. "
            "Expected format: name1=value1; name2=value2"
        )

    cookie_names = extract_cookie_names(cookie_header)

    if not cookie_names:
        raise RuntimeError(
            "Cookie header does not contain valid cookie names. "
            "Expected format: name1=value1; name2=value2"
        )


def save_cookie_header(output_path: Path, cookie_header: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(cookie_header, encoding="utf-8")


def print_manual_steps(marketplace: str, site_url: str, profile_path: Path) -> None:
    print()
    print(f"Marketplace: {marketplace}")
    print(f"Site: {site_url}")
    print(f"Microsoft Edge profile: {profile_path}")
    print()
    print("Manual steps:")
    print("1. Wait until Microsoft Edge opens the marketplace.")
    print("2. If marketplace asks you to log in, log in.")
    print("3. Search for any product.")
    print("4. Wait until the page is loaded normally.")
    print("5. Return to this terminal.")
    print("6. Press Enter to save cookies.")
    print()
    print("The script will not print cookie values.")
    print()


def print_cookie_summary(
    cookie_header: str,
    output_path: Path,
    marketplace: str,
    profile_path: Path,
) -> None:
    cookie_names = extract_cookie_names(cookie_header)

    print()
    print("Cookies saved successfully.")
    print(f"Marketplace: {marketplace}")
    print(f"Cookies count: {len(cookie_names)}")
    print(f"Cookie names: {', '.join(cookie_names)}")
    print(f"Saved to: {output_path}")
    print(f"Microsoft Edge profile: {profile_path}")


def run_cookie_update(
    marketplace: str,
    output_path: Path,
    cdp_port: int,
    custom_edge_path: Optional[str],
    keep_open: bool,
) -> None:
    marketplace_config = MARKETPLACE_CONFIG[marketplace]

    site_url = marketplace_config["url"]
    profile_path = resolve_profile_path(marketplace=marketplace)
    edge_path = resolve_edge_path(custom_edge_path=custom_edge_path)

    edge_process: Optional[subprocess.Popen] = None

    if not is_cdp_available(cdp_port=cdp_port):
        edge_process = launch_edge_with_cdp(
            edge_path=edge_path,
            profile_path=profile_path,
            cdp_port=cdp_port,
            start_url=site_url,
        )

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(
            endpoint_url=f"http://127.0.0.1:{cdp_port}",
        )

        page = get_or_create_page(
            browser=browser,
            site_url=site_url,
        )

        page.bring_to_front()

        print_manual_steps(
            marketplace=marketplace,
            site_url=site_url,
            profile_path=profile_path,
        )

        input("Press Enter when the marketplace page is ready...")

        context = get_main_context(browser=browser)

        cookies = context.cookies(site_url)
        cookie_header = format_cookie_header(cookies)

        validate_cookie_header(cookie_header)

        save_cookie_header(
            output_path=output_path,
            cookie_header=cookie_header,
        )

        print_cookie_summary(
            cookie_header=cookie_header,
            output_path=output_path,
            marketplace=marketplace,
            profile_path=profile_path,
        )

        browser.close()

    if keep_open:
        print()
        print("Microsoft Edge was kept open because --keep-open was passed.")
        return

    if edge_process is not None:
        edge_process.terminate()


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    output_path = resolve_output_path(
        marketplace=args.marketplace,
        custom_output=args.output,
    )

    run_cookie_update(
        marketplace=args.marketplace,
        output_path=output_path,
        cdp_port=args.cdp_port,
        custom_edge_path=args.edge_path,
        keep_open=args.keep_open,
    )


if __name__ == "__main__":
    main()
