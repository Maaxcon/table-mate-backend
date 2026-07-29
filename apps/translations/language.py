import re
from typing import Optional

LANGUAGE_CODE_REGEX = re.compile(r"^[a-z]{2,3}(-[a-zA-Z0-9]+)?$")


def parse_accept_language_header(header: str) -> list[tuple[str, float]]:
    """Parse Accept-Language header into a sorted list of (lang, q) tuples."""
    if not header:
        return []
    tags: list[tuple[str, float]] = []
    for part in header.split(","):
        part = part.strip()
        if not part:
            continue
        if ";" in part:
            lang, q_str = part.split(";", 1)
            q_str = q_str.strip()
            if q_str.startswith("q="):
                try:
                    q = float(q_str[2:])
                except ValueError:
                    q = 1.0
            else:
                q = 1.0
        else:
            lang = part
            q = 1.0
        lang = lang.strip()
        if lang and LANGUAGE_CODE_REGEX.match(lang):
            tags.append((lang, q))
    tags.sort(key=lambda x: x[1], reverse=True)
    return tags


def select_best_match(
    preferred: list[tuple[str, float]],
    supported: list[str],
) -> Optional[str]:
    """Select the best supported language from the preferred list.

    Tries exact match first, then falls back to matching just the primary
    language subtag (e.g. 'en-US' matches 'en').
    """
    supported_set = set(supported)
    for lang, _q in preferred:
        if lang in supported_set:
            return lang
    for lang, _q in preferred:
        primary = lang.split("-")[0]
        if primary in supported_set:
            return primary
    return None


SUPPORTED_LANGUAGE_CODES = frozenset(
    {
        "en", "uk", "de", "fr", "pl", "es", "it", "pt", "nl", "ro",
        "bg", "cs", "da", "el", "et", "fi", "hu", "lt", "lv", "sk",
        "sl", "sv", "tr",
    }
)


def resolve_restaurant_language(
    restaurant: object,
    accept_language_header: str,
    default: str = "en",
) -> str:
    """Resolve the best language for a restaurant given an Accept-Language header.

    Returns the best matching supported language, or the restaurant's configured
    locale, or *default* as a last resort.
    """
    from django.core.exceptions import ObjectDoesNotExist
    try:
        settings = restaurant.settings  # type: ignore[union-attr]
    except (ObjectDoesNotExist, AttributeError):
        return default
    supported = settings.supported_languages or [settings.locale]
    preferred = parse_accept_language_header(accept_language_header)
    best = select_best_match(preferred, supported)
    if best:
        return best
    return settings.locale
