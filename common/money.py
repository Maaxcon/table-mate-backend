from decimal import ROUND_HALF_UP, Decimal

# Money is rounded to two decimal places (the minor unit for USD and most
# currencies the app handles). Zero/three-decimal currencies (e.g. JPY, BHD)
# are not modelled yet; revisit this if they are added.
_CENTS = Decimal("0.01")


def quantize_money(value: Decimal) -> Decimal:
    """Round a monetary amount to the currency minor unit (cents, half-up)."""
    return Decimal(value).quantize(_CENTS, rounding=ROUND_HALF_UP)
