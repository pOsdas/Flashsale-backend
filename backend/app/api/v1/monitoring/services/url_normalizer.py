from urllib.parse import urlsplit, urlunsplit


def normalize_product_url(url: str) -> str:
    parsed = urlsplit(url.strip())

    scheme = "https"
    netloc = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.rstrip("/")

    return urlunsplit((scheme, netloc, path, "", ""))
