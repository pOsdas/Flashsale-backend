import re
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from app.api.v1.monitoring.models import Marketplace


URL_PATTERN = re.compile(
    r"https?://[^\s<>()]+",
    flags=re.IGNORECASE,
)
TRAILING_URL_CHARACTERS = ".,!?;:)]}>\"'"


class MarketplaceUrlError(ValueError):
    """The text does not contain a supported marketplace product URL."""


@dataclass(frozen=True, slots=True)
class ResolvedMarketplaceUrl:
    marketplace: str
    url: str


def resolve_marketplace_url(
    *,
    text: str,
) -> ResolvedMarketplaceUrl:
    url = _extract_url(text=text)
    parsed_url = urlsplit(url)

    if parsed_url.scheme.lower() not in {"http", "https"}:
        raise MarketplaceUrlError(
            "Ссылка должна начинаться с http:// или https://."
        )

    if parsed_url.username or parsed_url.password:
        raise MarketplaceUrlError(
            "Ссылка содержит недопустимые данные авторизации."
        )

    hostname = (parsed_url.hostname or "").lower().rstrip(".")

    if _host_matches(hostname, "wildberries.ru"):
        marketplace = Marketplace.WILDBERRIES
    elif _host_matches(hostname, "ozon.ru"):
        marketplace = Marketplace.OZON
    else:
        raise MarketplaceUrlError(
            "Поддерживаются только ссылки Wildberries и Ozon."
        )

    normalized_url = urlunsplit(
        (
            parsed_url.scheme.lower(),
            parsed_url.netloc.lower(),
            parsed_url.path or "/",
            parsed_url.query,
            "",
        )
    )

    return ResolvedMarketplaceUrl(
        marketplace=marketplace,
        url=normalized_url,
    )


def _extract_url(*, text: str) -> str:
    normalized_text = str(text).strip()

    if not normalized_text:
        raise MarketplaceUrlError(
            "Отправьте ссылку на товар Wildberries или Ozon."
        )

    match = URL_PATTERN.search(normalized_text)

    if match is None:
        raise MarketplaceUrlError(
            "Отправьте полную ссылку на товар Wildberries или Ozon."
        )

    return match.group(0).rstrip(TRAILING_URL_CHARACTERS)


def _host_matches(hostname: str, domain: str) -> bool:
    return hostname == domain or hostname.endswith(f".{domain}")
