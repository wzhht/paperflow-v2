import re
from urllib.parse import unquote, urlsplit

DOI_RE = re.compile(
    r"^10\.\d{4,9}/\S+$",
    re.IGNORECASE,
)


def normalize_doi(value: str) -> str:
    """
    Normalize a DOI into canonical lowercase form.

    Accepted examples:

        10.1016/j.buildenv.2025.113229

        DOI:10.1016/j.buildenv.2025.113229

        https://doi.org/10.1016/j.buildenv.2025.113229

        http://dx.doi.org/10.1007/s12273-026-1484-2
    """

    if not isinstance(value, str):
        raise TypeError("DOI must be a string.")

    text = value.strip()

    if not text:
        raise ValueError("DOI cannot be empty.")

    # Common wrappers copied from HTML / Markdown-like text.
    text = text.strip("<>").strip()

    # DOI resolver URL.
    if text.lower().startswith(("http://", "https://")):
        parsed = urlsplit(text)

        hostname = (parsed.hostname or "").lower()

        if hostname not in {
            "doi.org",
            "www.doi.org",
            "dx.doi.org",
        }:
            raise ValueError(f"Unsupported DOI URL host: {hostname or 'unknown'}")

        text = parsed.path.lstrip("/")

    # Common textual prefix.
    if text.lower().startswith("doi:"):
        text = text[4:].strip()

    # Decode URL-escaped characters.
    text = unquote(text).strip()

    # DOI identifiers are case-insensitive.
    text = text.lower()

    if not DOI_RE.fullmatch(text):
        raise ValueError(f"Invalid DOI: {value!r}")

    return text


def is_valid_doi(value: str) -> bool:
    try:
        normalize_doi(value)
    except (ValueError, TypeError):
        return False

    return True
