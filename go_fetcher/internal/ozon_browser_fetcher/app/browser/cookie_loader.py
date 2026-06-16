from pathlib import Path
from typing import Dict, List


OZON_COOKIE_DOMAIN = ".ozon.ru"
OZON_COOKIE_PATH = "/"


def load_cookie_header(path: str) -> str:
    cookie_path = Path(path)

    if not cookie_path.exists():
        raise FileNotFoundError(f"Cookie file not found: {cookie_path}")

    return cookie_path.read_text(encoding="utf-8").strip()


def normalize_cookie_header(cookie_header: str) -> str:
    cookie_header = cookie_header.strip()

    if not cookie_header:
        return ""

    if cookie_header.lower().startswith("cookie:"):
        cookie_header = cookie_header.split(":", 1)[1].strip()

    cookie_header = cookie_header.replace("\r", " ")
    cookie_header = cookie_header.replace("\n", " ")

    while "  " in cookie_header:
        cookie_header = cookie_header.replace("  ", " ")

    return cookie_header.strip()


def is_valid_cookie_name(name: str) -> bool:
    if not name:
        return False

    invalid_chars = ["\x00", "\r", "\n", ";", ",", " "]

    for char in invalid_chars:
        if char in name:
            return False

    return True


def is_valid_cookie_value(value: str) -> bool:
    if value is None:
        return False

    invalid_chars = ["\x00", "\r", "\n"]

    for char in invalid_chars:
        if char in value:
            return False

    return True


def should_skip_cookie(name: str, value: str) -> bool:
    if not is_valid_cookie_name(name):
        return True

    if not is_valid_cookie_value(value):
        return True

    if value == "":
        return True

    return False


def parse_cookie_header(cookie_header: str) -> List[Dict]:
    """
    Преобразует строку вида:

        name1=value1; name2=value2; name3=value3

    в формат Playwright:

        [
            {
                "name": "name1",
                "value": "value1",
                "domain": ".ozon.ru",
                "path": "/",
                "secure": True,
                "httpOnly": False,
                "sameSite": "Lax"
            }
        ]

    Важно:
    - cookies с префиксом __Secure- требуют secure=True;
    - Ozon работает по HTTPS, поэтому secure=True ставим всем cookies;
    - значения cookies не печатаем в консоль.
    """
    normalized_cookie_header = normalize_cookie_header(cookie_header)

    if not normalized_cookie_header:
        return []

    cookies: List[Dict] = []

    for raw_part in normalized_cookie_header.split(";"):
        part = raw_part.strip()

        if not part:
            continue

        if "=" not in part:
            continue

        name, value = part.split("=", 1)

        name = name.strip()
        value = value.strip()

        if should_skip_cookie(name=name, value=value):
            continue

        cookie = {
            "name": name,
            "value": value,
            "domain": OZON_COOKIE_DOMAIN,
            "path": OZON_COOKIE_PATH,
            "secure": True,
            "httpOnly": False,
            "sameSite": "Lax",
        }

        cookies.append(cookie)

    return cookies


def extract_cookie_names(cookies: List[Dict]) -> List[str]:
    names = []

    for cookie in cookies:
        name = cookie.get("name", "")

        if name:
            names.append(name)

    return sorted(set(names))