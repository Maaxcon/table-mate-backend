from __future__ import annotations

import re

from .registry import INTENT_BOOKING, INTENT_CART, INTENT_INFO, INTENT_NONE

_BOOKING_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(book|reserve|booking|reservation)\b", re.IGNORECASE),
    re.compile(r"\btable for\b", re.IGNORECASE),
    re.compile(r"\bseat(s|ed)?\s+(for|us|me)?\s*\d+\b", re.IGNORECASE),
    re.compile(r"\b(забронювати|забронюй|бронювання|резервація|столик)\b", re.IGNORECASE),
    re.compile(r"\b(ресторан)?\s*(на|для)\s*\d+\s*(гостей|осіб)?\b", re.IGNORECASE),
)

_CART_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(add|order|cart|i'?d like to have|i want to order)\b", re.IGNORECASE),
    re.compile(r"\b(додай|замов|додати|замовити|кошик)\b", re.IGNORECASE),
)

_INFO_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(menu|allergen|allergens|gluten|ingredient|ingredients|price|how much|open(ing)? hours|address|policy)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(меню|алерг|глютен|інгред|ціна|адреса|години|політика|відкрито)\b", re.IGNORECASE),
    re.compile(r"\bwhat (dishes|food|items|do you serve)\b", re.IGNORECASE),
)


def categorize(text: str) -> str:
    """Deterministic intent classification (FR-020). Output is one of the four
    registry intents; it is keyword/entity based, never model-driven."""
    if not text or not text.strip():
        return INTENT_NONE

    # Booking phrases dominate over generic info words like "price"/"hours".
    for pattern in _BOOKING_PATTERNS:
        if pattern.search(text):
            return INTENT_BOOKING

    for pattern in _CART_PATTERNS:
        if pattern.search(text):
            return INTENT_CART

    for pattern in _INFO_PATTERNS:
        if pattern.search(text):
            return INTENT_INFO

    return INTENT_NONE


__all__ = ["categorize"]
