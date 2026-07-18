import argparse
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, TypedDict

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright


class MarketplaceConfig(TypedDict):
    url: str
    default_output: str
    profile_dir: str
    excluded_cookie_names: Set[str]


MARKETPLACE_CONFIG: Dict[str, MarketplaceConfig] = {
    "wb": {
        "url": "https://www.wildberries.ru",
        "default_output": "secrets/wb_cookie.txt",
        "profile_dir": "tools/playwright/chrome_profiles/wb",
        # Browser/IP-bound anti-bot token. The server-side Chrome must obtain
        # its own fresh value inside its persistent profile.
        "excluded_cookie_names": {
            "x_wbaas_token",
        },
    },
    "ozon": {
        "url": "https://www.ozon.ru",
        "default_output": "secrets/ozon_cookie.txt",
        "profile_dir": "tools/playwright/chrome_profiles/ozon",
        # These challenge cookies are tied to the local browser/IP session.
        # Exporting them to the server can conflict with the server-side
        # persistent Chrome profile and trigger a new anti-bot rejection.
        "excluded_cookie_names": {
            "abt_data",
            "__Secure-ETC",
        },
    },
}


def get_default_chrome_paths() -> List[Path]:
    paths = [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    ]

    local_app_data = os.getenv("LOCALAPPDATA")

    if local_app_data:
        paths.append(
            Path(local_app_data)
            / "Google"
            / "Chrome"
            / "Application"
            / "chrome.exe"
        )

    return paths


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
            "Launches Google Chrome with remote debugging, opens the "
            "marketplace and saves only cookies safe to transfer to the "
            "server as an HTTP Cookie header."
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
            "Optional output path for the cookie file. "
            "If not provided, the marketplace default path will be used."
        ),
    )

    parser.add_argument(
        "--cdp-port",
        type=int,
        default=9222,
        help="Google Chrome remote debugging port. Default: 9222.",
    )

    parser.add_argument(
        "--chrome-path",
        default=None,
        help="Optional path to chrome.exe.",
    )

    parser.add_argument(
        "--keep-open",
        action="store_true",
        help="Keep Google Chrome open after cookies are saved.",
    )

    return parser


def resolve_output_path(
    marketplace: str,
    custom_output: Optional[str],
) -> Path:
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


def resolve_chrome_path(custom_chrome_path: Optional[str]) -> Path:
    if custom_chrome_path:
        chrome_path = Path(custom_chrome_path).expanduser().resolve()

        if not chrome_path.exists():
            raise RuntimeError(
                f"Google Chrome executable not found: {chrome_path}"
            )

        return chrome_path

    for chrome_path in get_default_chrome_paths():
        if chrome_path.exists():
            return chrome_path

    raise RuntimeError(
        "Google Chrome executable was not found automatically. "
        "Pass it manually with --chrome-path."
    )


def get_cdp_metadata(cdp_port: int) -> Optional[dict]:
    url = f"http://127.0.0.1:{cdp_port}/json/version"

    try:
        with urllib.request.urlopen(url, timeout=1) as response:
            if response.status != 200:
                return None

            raw_data = response.read().decode("utf-8")
            data = json.loads(raw_data)

            if not isinstance(data, dict):
                return None

            return data

    except Exception:
        return None


def is_cdp_available(cdp_port: int) -> bool:
    return get_cdp_metadata(cdp_port=cdp_port) is not None


def validate_existing_cdp_browser(cdp_port: int) -> None:
    metadata = get_cdp_metadata(cdp_port=cdp_port)

    if metadata is None:
        return

    browser_name = str(metadata.get("Browser", ""))
    user_agent = str(metadata.get("User-Agent", ""))
    combined = f"{browser_name} {user_agent}".lower()

    if "edg/" in combined or "microsoft edge" in combined:
        raise RuntimeError(
            f"Port {cdp_port} is already used by Microsoft Edge. "
            "Close Edge or use another --cdp-port so the script can start "
            "Google Chrome."
        )


def wait_for_chrome_cdp(
    cdp_port: int,
    timeout_seconds: int = 20,
) -> None:
    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        metadata = get_cdp_metadata(cdp_port=cdp_port)

        if metadata is not None:
            validate_existing_cdp_browser(cdp_port=cdp_port)
            return

        time.sleep(0.3)

    raise RuntimeError(
        f"Google Chrome did not start remote debugging on port {cdp_port}."
    )


def launch_chrome_with_cdp(
    chrome_path: Path,
    profile_path: Path,
    cdp_port: int,
    start_url: str,
) -> subprocess.Popen:
    profile_path.mkdir(parents=True, exist_ok=True)

    command = [
        str(chrome_path),
        "--remote-debugging-address=127.0.0.1",
        f"--remote-debugging-port={cdp_port}",
        f"--user-data-dir={profile_path}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-mode",
        start_url,
    ]

    process = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    wait_for_chrome_cdp(cdp_port=cdp_port)

    return process


def get_main_context(browser: Browser) -> BrowserContext:
    if not browser.contexts:
        raise RuntimeError(
            "Google Chrome CDP connection has no persistent browser context."
        )

    return browser.contexts[0]


def get_or_create_page(browser: Browser, site_url: str) -> Page:
    context = get_main_context(browser=browser)

    for page in context.pages:
        current_url = page.url.lower()

        if "wildberries" in current_url or "ozon" in current_url:
            return page

    page = context.new_page()
    page.goto(
        site_url,
        wait_until="domcontentloaded",
        timeout=60_000,
    )

    return page


def cookie_priority(cookie: dict) -> Tuple[int, int, float]:
    """
    Cookie files store only name=value and lose domain/path metadata.

    When Chrome returns several applicable cookies with the same name, prefer:
    1. a root-path cookie, because the server parser calls different endpoints;
    2. a parent-domain cookie, because it is usable on marketplace subdomains;
    3. the cookie with the later expiration time.
    """
    path = str(cookie.get("path") or "")
    domain = str(cookie.get("domain") or "")

    root_path_score = 1 if path == "/" else 0
    parent_domain_score = 1 if domain.startswith(".") else 0

    raw_expires = cookie.get("expires", 0)

    try:
        expires = float(raw_expires)
    except (TypeError, ValueError):
        expires = 0.0

    return root_path_score, parent_domain_score, expires


def filter_exportable_cookies(
    cookies: List[dict],
    excluded_cookie_names: Set[str],
) -> Tuple[List[dict], List[str], List[str]]:
    """
    Removes cookies that should never be transferred from local Chrome to the
    server and deduplicates names that cannot be represented unambiguously in
    a plain HTTP Cookie header.
    """
    excluded_names_casefold = {
        name.casefold()
        for name in excluded_cookie_names
    }

    selected_by_name: Dict[str, dict] = {}
    excluded_names: Set[str] = set()
    duplicate_names: Set[str] = set()

    for cookie in cookies:
        name = str(cookie.get("name") or "").strip()
        value = cookie.get("value")

        if not name or value is None or value == "":
            continue

        if name.casefold() in excluded_names_casefold:
            excluded_names.add(name)
            continue

        existing = selected_by_name.get(name)

        if existing is None:
            selected_by_name[name] = cookie
            continue

        duplicate_names.add(name)

        if cookie_priority(cookie) > cookie_priority(existing):
            selected_by_name[name] = cookie

    selected_cookies = [
        selected_by_name[name]
        for name in sorted(selected_by_name)
    ]

    return (
        selected_cookies,
        sorted(excluded_names),
        sorted(duplicate_names),
    )


def format_cookie_header(cookies: List[dict]) -> str:
    """
    Converts cookies to one HTTP Cookie header line:

        name1=value1; name2=value2
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

        if not cookie_part or "=" not in cookie_part:
            continue

        cookie_name = cookie_part.split("=", 1)[0].strip()

        if cookie_name:
            cookie_names.append(cookie_name)

    return sorted(set(cookie_names))


def validate_cookie_header(cookie_header: str) -> None:
    if not cookie_header:
        raise RuntimeError(
            "No transferable cookies remain after filtering. "
            "The local browser may contain only browser/IP-bound anti-bot "
            "cookies. Open the marketplace normally, browse a product and "
            "try again."
        )

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


def save_cookie_header(
    output_path: Path,
    cookie_header: str,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(cookie_header, encoding="utf-8")


def print_manual_steps(
    marketplace: str,
    site_url: str,
    profile_path: Path,
) -> None:
    print()
    print(f"Marketplace: {marketplace}")
    print(f"Site: {site_url}")
    print(f"Google Chrome profile: {profile_path}")
    print()
    print("Manual steps:")
    print("1. Wait until Google Chrome opens the marketplace.")
    print("2. Complete the anti-bot check if it appears.")
    print("3. Search for any product and open its page.")
    print("4. Wait until the page is loaded normally.")
    print("5. Return to this terminal.")
    print("6. Press Enter to save cookies.")
    print()
    print(
        "Browser/IP-bound anti-bot cookies will not be written "
        "to the server cookie file."
    )
    print("The script will not print cookie values.")
    print()


def print_cookie_summary(
    cookie_header: str,
    output_path: Path,
    marketplace: str,
    profile_path: Path,
    excluded_names: List[str],
    duplicate_names: List[str],
) -> None:
    cookie_names = extract_cookie_names(cookie_header)

    print()
    print("Cookies saved successfully.")
    print(f"Marketplace: {marketplace}")
    print(f"Exported cookies count: {len(cookie_names)}")
    print(f"Exported cookie names: {', '.join(cookie_names)}")

    if excluded_names:
        print(
            "Excluded browser/IP-bound cookies: "
            f"{', '.join(excluded_names)}"
        )

    if duplicate_names:
        print(
            "Deduplicated cookie names: "
            f"{', '.join(duplicate_names)}"
        )

    print(f"Saved to: {output_path}")
    print(f"Google Chrome profile: {profile_path}")


def terminate_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return

    process.terminate()

    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def run_cookie_update(
    marketplace: str,
    output_path: Path,
    cdp_port: int,
    custom_chrome_path: Optional[str],
    keep_open: bool,
) -> None:
    marketplace_config = MARKETPLACE_CONFIG[marketplace]

    site_url = marketplace_config["url"]
    profile_path = resolve_profile_path(marketplace=marketplace)
    chrome_path = resolve_chrome_path(
        custom_chrome_path=custom_chrome_path,
    )
    excluded_cookie_names = marketplace_config[
        "excluded_cookie_names"
    ]

    chrome_process: Optional[subprocess.Popen] = None

    if is_cdp_available(cdp_port=cdp_port):
        validate_existing_cdp_browser(cdp_port=cdp_port)
    else:
        chrome_process = launch_chrome_with_cdp(
            chrome_path=chrome_path,
            profile_path=profile_path,
            cdp_port=cdp_port,
            start_url=site_url,
        )

    try:
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
            all_cookies = context.cookies(site_url)

            (
                exportable_cookies,
                excluded_names,
                duplicate_names,
            ) = filter_exportable_cookies(
                cookies=all_cookies,
                excluded_cookie_names=excluded_cookie_names,
            )

            cookie_header = format_cookie_header(exportable_cookies)

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
                excluded_names=excluded_names,
                duplicate_names=duplicate_names,
            )

            # Do not call browser.close() here. This browser was launched
            # externally and is only connected through CDP. Exiting the
            # Playwright context disconnects Playwright without intentionally
            # closing the external Chrome process.

    finally:
        if keep_open:
            print()
            print(
                "Google Chrome was kept open because --keep-open was passed."
            )
        elif chrome_process is not None:
            terminate_process(chrome_process)


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
        custom_chrome_path=args.chrome_path,
        keep_open=args.keep_open,
    )


if __name__ == "__main__":
    main()