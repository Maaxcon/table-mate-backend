from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.editor.selectors import get_available_tables
from apps.menu.models import MenuItem
from apps.orders.models import CartSession, CartSessionStatus
from apps.orders.selectors import get_cart_session_by_public_id
from apps.orders.services.cart import add_item_to_cart
from apps.orders.services.modifiers import normalize_modifiers
from apps.reservations.models import Reservation, ReservationStatus
from apps.reservations.selectors import get_reservation_by_id, get_reservation_participant_ids
from apps.reservations.services import cancel_reservation, create_reservation, reschedule_reservation
from apps.restaurants.models import Restaurant, RestaurantSettings
from common.exceptions import (
    CartSessionClosedError,
    InvalidModifierError,
    MenuItemNotFoundError,
    MenuItemUnavailableError,
    ModifierRequiredError,
    ReservationCancelError,
    ReservationConflictError,
    RestaurantClosedError,
)

from .registry import (
    PERSONA_ADMIN,
    PERSONA_GUEST,
    ExecutionResult,
    ToolContext,
    ToolResult,
    registry,
)
from .schemas import (
    AddToCartArgsSerializer,
    CancelReservationArgsSerializer,
    CheckAvailabilityArgsSerializer,
    CreateReservationArgsSerializer,
    GetFloorStatusArgsSerializer,
    GetMenuArgsSerializer,
    GetRestaurantInfoArgsSerializer,
    RescheduleReservationArgsSerializer,
)

RESERVATION_DURATION = timedelta(hours=2)


def _settings(restaurant_id: int) -> RestaurantSettings | None:
    return RestaurantSettings.objects.filter(restaurant_id=restaurant_id).first()


def _tz(restaurant_id: int) -> ZoneInfo:
    settings = _settings(restaurant_id)
    if settings is not None and settings.timezone:
        try:
            return ZoneInfo(settings.timezone)
        except (ValueError, KeyError, ZoneInfoNotFoundError):
            pass
    return ZoneInfo("UTC")


def _slot_start(restaurant_id: int, when_date: Any, when_time: Any) -> datetime:
    tz = _tz(restaurant_id)
    if isinstance(when_date, str):
        when_date = datetime.strptime(when_date, "%Y-%m-%d").date()
    if isinstance(when_time, str):
        when_time = datetime.strptime(when_time, "%H:%M").time()
    naive = datetime.combine(when_date, when_time)
    return naive.replace(tzinfo=tz)


def _now(ctx: ToolContext) -> datetime:
    return ctx.now or timezone.now()


def _slot_label(ctx: ToolContext, when_date: Any, when_time: Any) -> str:
    try:
        start = _slot_start(ctx.restaurant_id, when_date, when_time)
        return f"{start.date().isoformat()} at {start.strftime('%H:%M')}"
    except (TypeError, ValueError):
        return "the requested time"


def _format_price(price: Decimal) -> str:
    try:
        return str(price.quantize(Decimal("0.01")))
    except Exception:
        return str(price)


def _translate_name(item: Any, language: str, field: str = "name") -> str:
    if language:
        for translation in item.translations.all():
            if translation.language_code == language:
                translated = getattr(translation, field, None)
                if translated:
                    return str(translated)
    return str(getattr(item, field) or "")


# ---------------------------------------------------------------------------
# Read-only tools (US-1)
# ---------------------------------------------------------------------------


def _execute_get_menu(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    qs = MenuItem.objects.filter(restaurant_id=ctx.restaurant_id, menu__is_active=True)
    if args.get("available_only"):
        qs = qs.filter(is_available=True)
    category_id = (args.get("category_id") or "").strip()
    if category_id:
        qs = qs.filter(category__public_id=category_id)
    query = (args.get("query") or "").strip()
    if query:
        qs = qs.filter(
            Q(name__icontains=query)
            | Q(description__icontains=query)
            | Q(translations__name__icontains=query)
        ).distinct()

    items = list(
        qs.prefetch_related("translations", "allergens", "ingredients")
        .order_by("sort_order", "id")[:12]
    )
    if not items:
        return ToolResult(text="No menu items found matching your request.")

    lines: list[str] = []
    for item in items:
        name = _translate_name(item, ctx.language)
        price = _format_price(item.price)
        status = "available" if item.is_available else "not available today"
        allergens = ", ".join(str(a.name) for a in item.allergens.all()) or "none"
        ingredients = ", ".join(str(i.name) for i in item.ingredients.all()) or "n/a"
        lines.append(
            f"{name} — {price} {ctx_currency(ctx)} ({status}). "
            f"Ingredients: {ingredients}. Allergens: {allergens}."
        )
    return ToolResult(text="\n".join(lines))


def ctx_currency(ctx: ToolContext) -> str:
    settings = _settings(ctx.restaurant_id)
    return settings.currency if settings is not None and settings.currency else "UAH"


def _working_hours_text(settings: RestaurantSettings) -> str:
    hours = settings.working_hours or {}
    if not hours:
        return "We are open daily; please contact us for exact hours."
    lines: list[str] = []
    for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun"):
        entry = hours.get(day)
        if entry:
            lines.append(f"{day.capitalize()}: {entry.get('open')}-{entry.get('close')}")
        else:
            lines.append(f"{day.capitalize()}: closed")
    return "; ".join(lines)


def _execute_get_restaurant_info(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    restaurant = Restaurant.objects.filter(pk=ctx.restaurant_id).first()
    settings = _settings(ctx.restaurant_id)
    topic = args.get("topic")

    if topic == "payment":
        return ToolResult(
            text="Payment is handled by our staff at the table or at the checkout. "
            "The assistant cannot process payments or store card details."
        )
    if topic == "hours":
        hours = _working_hours_text(settings) if settings else "Hours are not configured."
        return ToolResult(text=hours)
    if topic == "address":
        address = restaurant.address if restaurant else "Address is not available."
        return ToolResult(text=address)
    if topic == "contact":
        phone = restaurant.phone if restaurant and restaurant.phone else "not listed"
        address = restaurant.address if restaurant else "n/a"
        return ToolResult(text=f"Phone: {phone}. Address: {address}.")
    if topic == "policy":
        return ToolResult(
            text="Reservations are confirmed when the requested time is available and within "
            "opening hours. You can move or cancel your reservation through the assistant; "
            "please do so ahead of your visit."
        )

    name = restaurant.name if restaurant else "our restaurant"
    address = restaurant.address if restaurant and restaurant.address else "n/a"
    phone = restaurant.phone if restaurant and restaurant.phone else "n/a"
    hours = _working_hours_text(settings) if settings else "n/a"
    currency = ctx_currency(ctx)
    return ToolResult(
        text=f"{name}. Address: {address}. Phone: {phone}. Currency: {currency}. "
        f"Opening hours: {hours}. For payment questions, our staff will help at the table."
    )


def _execute_check_availability(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    party_size = int(args["party_size"])
    start = _slot_start(ctx.restaurant_id, args["date"], args["time"])
    end = start + RESERVATION_DURATION

    tables = list(get_available_tables(ctx.restaurant_id, start, end, guest_count=party_size))
    if tables:
        numbers = ", ".join(str(t.public_number) for t in tables[:5])
        return ToolResult(
            text=f"We have availability for {party_size} guests on "
            f"{start.date().isoformat()} at {start.strftime('%H:%M')} "
            f"(tables: {numbers}). Say 'book it' to reserve."
        )

    alternatives: list[str] = []
    for minutes in (60, 30, -30, -60, 90, 120):
        probe = start + timedelta(minutes=minutes)
        probe_tables = list(
            get_available_tables(ctx.restaurant_id, probe, probe + RESERVATION_DURATION, guest_count=party_size)
        )
        if probe_tables:
            slot_tables = "/".join(str(t.public_number) for t in probe_tables[:2])
            alternatives.append(f"{probe.strftime('%H:%M')} (table {slot_tables})")
            if len(alternatives) >= 2:
                break

    if alternatives:
        return ToolResult(
            text=f"No availability for {party_size} guests at {start.strftime('%H:%M')}. "
            f"Nearest open slots: {', '.join(alternatives)}."
        )
    return ToolResult(
        text=f"We have no availability for {party_size} guests on {start.date().isoformat()} "
        f"at {start.strftime('%H:%M')} or nearby. Please ask staff for options."
    )


# ---------------------------------------------------------------------------
# Write tools — proposal builders + confirm-time executors (US-2/3/4)
# ---------------------------------------------------------------------------


def _reservation_belongs_to_owner(ctx: ToolContext, reservation: Reservation) -> bool:
    if ctx.user is not None:
        if reservation.customer_id == ctx.user.pk:
            return True
        return ctx.user.pk in get_reservation_participant_ids(reservation)
    return False


def _resolve_own_reservation(ctx: ToolContext, reservation_id: Any) -> Reservation | None:
    try:
        reservation = get_reservation_by_id(str(reservation_id), ctx.restaurant_id)
    except (ValueError, TypeError):
        return None
    if reservation is None:
        return None
    if not _reservation_belongs_to_owner(ctx, reservation):
        return None
    return reservation


def _propose_create_reservation(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    party_size = int(args["party_size"])
    when = _slot_label(ctx, args.get("date"), args.get("time"))
    return ToolResult(
        summary=f"Create a reservation for {party_size} guests on {when}",
        consequence=f"This books a table for {party_size} guests on {when}. You can reschedule or cancel it later.",
        needs_confirmation=True,
    )


def _execute_create_reservation(ctx: ToolContext, args: dict[str, Any]) -> ExecutionResult:
    party_size = int(args["party_size"])
    start = _slot_start(ctx.restaurant_id, args["date"], args["time"])
    end = start + RESERVATION_DURATION
    try:
        tables = list(get_available_tables(ctx.restaurant_id, start, end, guest_count=party_size))
        if not tables:
            return ExecutionResult("failed", error_code="slot_taken")
        customer_id = ctx.user.pk if ctx.user is not None else None
        reservation = create_reservation(
            restaurant_id=ctx.restaurant_id,
            customer_id=customer_id,  # type: ignore[arg-type]
            table_id=str(tables[0].public_id),
            guest_count=party_size,
            start_at=start,
            end_at=end,
            notes=args.get("notes") or None,
            actor=ctx.user,
        )
        return ExecutionResult("success", reference_id=str(reservation.public_id))
    except RestaurantClosedError:
        return ExecutionResult("failed", error_code="outside_business_hours")
    except ReservationConflictError:
        return ExecutionResult("failed", error_code="slot_taken")
    except Exception:
        return ExecutionResult("failed", error_code="unknown")


def _propose_reschedule_reservation(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    reservation = _resolve_own_reservation(ctx, args.get("reservation_id"))
    if reservation is not None:
        target = _target_datetime_text(ctx, args, reservation)
        summary = f"Move your reservation to {target}"
        consequence = (
            f"This reschedules your reservation #{reservation.public_id} for {reservation.guest_count} guests "
            f"currently booked on {reservation.start_at.strftime('%Y-%m-%d %H:%M')} to {target}."
        )
    else:
        summary = "Move your reservation"
        consequence = "This reschedules the reservation you specified."
    return ToolResult(summary=summary, consequence=consequence, needs_confirmation=True)


def _target_datetime_text(ctx: ToolContext, args: dict[str, Any], reservation: Reservation) -> str:
    if args.get("date") and args.get("time"):
        return _slot_label(ctx, args["date"], args["time"])
    if args.get("date"):
        label = args["date"].isoformat() if not isinstance(args["date"], str) else args["date"]
        return f"{label} at the current time"
    if args.get("time"):
        label = args["time"].strftime("%H:%M") if not isinstance(args["time"], str) else args["time"]
        return f"the current date at {label}"
    if args.get("party_size"):
        return f"for {args['party_size']} guests (same time)"
    return "the requested time"


def _execute_reschedule_reservation(ctx: ToolContext, args: dict[str, Any]) -> ExecutionResult:
    reservation = _resolve_own_reservation(ctx, args.get("reservation_id"))
    if reservation is None:
        return ExecutionResult("failed", error_code="reservation_not_found")
    if ctx.user is None or reservation.customer_id != ctx.user.pk:
        return ExecutionResult("failed", error_code="not_owner")
    if reservation.status in {ReservationStatus.COMPLETED, ReservationStatus.CANCELLED}:
        return ExecutionResult("failed", error_code="already_cancelled")

    validated_data: dict[str, Any] = {}
    if args.get("date") or args.get("time"):
        when_date = args.get("date") or reservation.start_at.date()
        when_time = args.get("time") or reservation.start_at.time().replace(tzinfo=None)
        start = _slot_start(ctx.restaurant_id, when_date, when_time)
        validated_data["start_at"] = start
        validated_data["end_at"] = start + RESERVATION_DURATION
    if args.get("party_size"):
        validated_data["guest_count"] = int(args["party_size"])
    try:
        reschedule_reservation(reservation, validated_data)
        return ExecutionResult("success", reference_id=str(reservation.public_id))
    except (ReservationConflictError, RestaurantClosedError):
        return ExecutionResult("failed", error_code="slot_taken")
    except Exception:
        return ExecutionResult("failed", error_code="unknown")


def _propose_cancel_reservation(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    reservation = _resolve_own_reservation(ctx, args.get("reservation_id"))
    summary = "Cancel your reservation"
    if reservation is not None:
        consequence = (
            f"This cancels your reservation #{reservation.public_id} for {reservation.guest_count} guests "
            f"on {reservation.start_at.strftime('%Y-%m-%d %H:%M')}. The table is freed for other guests."
        )
    else:
        consequence = "This cancels the reservation you specified."
    return ToolResult(summary=summary, consequence=consequence, needs_confirmation=True)


def _execute_cancel_reservation(ctx: ToolContext, args: dict[str, Any]) -> ExecutionResult:
    reservation = _resolve_own_reservation(ctx, args.get("reservation_id"))
    if reservation is None:
        return ExecutionResult("failed", error_code="reservation_not_found")
    if ctx.user is None or not _reservation_belongs_to_owner(ctx, reservation):
        return ExecutionResult("failed", error_code="not_owner")
    if reservation.status == ReservationStatus.CANCELLED:
        return ExecutionResult("failed", error_code="already_cancelled")
    try:
        cancel_reservation(reservation, actor=ctx.user)
        return ExecutionResult("success", reference_id=str(reservation.public_id))
    except ReservationCancelError:
        return ExecutionResult("failed", error_code="already_cancelled")
    except Exception:
        return ExecutionResult("failed", error_code="unknown")


def _active_cart_session(ctx: ToolContext) -> CartSession | None:
    if ctx.cart_session_id:
        session = get_cart_session_by_public_id(str(ctx.cart_session_id))
        if (
            session is not None
            and session.restaurant_id == ctx.restaurant_id
            and session.status == CartSessionStatus.ACTIVE
        ):
            return session
        return None
    if ctx.user is not None:
        return (
            CartSession.objects.filter(restaurant_id=ctx.restaurant_id, status=CartSessionStatus.ACTIVE)
            .filter(
                Q(reservation__customer=ctx.user)
                | Q(participants=ctx.user)
                | Q(reservation__participants=ctx.user)
            )
            .order_by("-created_at")
            .first()
        )
    return None


def _propose_add_to_cart(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    quantity = int(args.get("quantity") or 1)
    item_id = args.get("menu_item_id")
    item = MenuItem.objects.filter(restaurant_id=ctx.restaurant_id, public_id=item_id).first() if item_id else None
    if item is None:
        summary = f"Add {quantity}× item to your cart"
        consequence = "This adds the requested item to your cart."
        return ToolResult(summary=summary, consequence=consequence, needs_confirmation=True)

    name = _translate_name(item, ctx.language)
    try:
        snapshot, price_delta = normalize_modifiers(item, args.get("modifiers"))
    except ModifierRequiredError as exc:
        # US-3/AS-4: ask for the missing choices before proposing.
        groups = []
        for missing in exc.missing:
            options = ", ".join(o["name"] for o in missing["options"])
            groups.append(f"{missing['name']} ({options})")
        clarification = (
            f"To add {name} I need to know your choice for: {'; '.join(groups)}. "
            "Please tell me which option you'd like."
        )
        return ToolResult(clarification=clarification)
    except InvalidModifierError:
        clarification = (
            f"Sorry, one of the chosen options isn't valid for {name}. "
            "Could you tell me which size/extras you'd like?"
        )
        return ToolResult(clarification=clarification)

    unit_price = item.price + price_delta
    total = _format_price(unit_price * quantity)
    summary = f"Add {quantity}× {name} to your cart"
    consequence = f"This adds {quantity}× {name} ({total} {ctx_currency(ctx)}) to your cart. "
    if snapshot:
        selections = ", ".join(entry["name"] for entry in snapshot)
        consequence += f"Options: {selections}. "
    consequence += "You can change or remove it before checkout."
    return ToolResult(summary=summary, consequence=consequence, needs_confirmation=True)


def _execute_add_to_cart(ctx: ToolContext, args: dict[str, Any]) -> ExecutionResult:
    session = _active_cart_session(ctx)
    if session is None:
        return ExecutionResult("failed", error_code="cart_closed")
    try:
        add_item_to_cart(
            session=session,
            menu_item_id=str(args["menu_item_id"]),
            quantity=int(args.get("quantity") or 1),
            user=ctx.user,
            guest_identity=ctx.guest_key or None,
            guest_slot=None,
            comment=args.get("guest_comment") or None,
            client_id=f"assistant:{ctx.conversation_id}"[:64],
            modifiers=args.get("modifiers") or None,
        )
        return ExecutionResult("success", reference_id=str(session.public_id))
    except CartSessionClosedError:
        return ExecutionResult("failed", error_code="cart_closed")
    except (MenuItemNotFoundError, MenuItemUnavailableError):
        return ExecutionResult("failed", error_code="item_unavailable")
    except (ModifierRequiredError, InvalidModifierError):
        return ExecutionResult("failed", error_code="modifier_required")
    except PermissionDenied:
        return ExecutionResult("failed", error_code="cart_closed")
    except Exception:
        return ExecutionResult("failed", error_code="unknown")


# ---------------------------------------------------------------------------
# Admin demo tool (US-6): role-bounded, read-only
# ---------------------------------------------------------------------------


def _execute_get_floor_status(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    open_sessions = CartSession.objects.filter(
        restaurant_id=ctx.restaurant_id,
        status=CartSessionStatus.ACTIVE,
    ).count()
    pending = Reservation.objects.filter(
        restaurant_id=ctx.restaurant_id,
        status=ReservationStatus.PENDING,
    ).count()
    return ToolResult(
        text=f"Floor status: {open_sessions} active cart session(s), {pending} pending reservation(s)."
    )


# ---------------------------------------------------------------------------
# Registration (FR-014): adding a tool = one entry here.
# ---------------------------------------------------------------------------

registry.register_tool(
    "get_menu",
    "Search the restaurant's live menu (name, price, availability, allergens, ingredients).",
    GetMenuArgsSerializer,
    needs_confirmation=False,
    personas={PERSONA_GUEST, PERSONA_ADMIN},
)(_execute_get_menu)

registry.register_tool(
    "get_restaurant_info",
    "Return restaurant info: hours, address, policy, contact, or payment referral.",
    GetRestaurantInfoArgsSerializer,
    needs_confirmation=False,
    personas={PERSONA_GUEST, PERSONA_ADMIN},
)(_execute_get_restaurant_info)

registry.register_tool(
    "check_availability",
    "Check table availability for a date, time and party size; suggest alternatives.",
    CheckAvailabilityArgsSerializer,
    needs_confirmation=False,
    personas={PERSONA_GUEST, PERSONA_ADMIN},
)(_execute_check_availability)

registry.register_tool(
    "create_reservation",
    "Create a reservation for a party on a date/time (requires confirmation).",
    CreateReservationArgsSerializer,
    needs_confirmation=True,
    personas={PERSONA_GUEST, PERSONA_ADMIN},
    execute=_execute_create_reservation,
)(_propose_create_reservation)

registry.register_tool(
    "reschedule_reservation",
    "Move the guest's own reservation (requires confirmation).",
    RescheduleReservationArgsSerializer,
    needs_confirmation=True,
    personas={PERSONA_GUEST, PERSONA_ADMIN},
    execute=_execute_reschedule_reservation,
)(_propose_reschedule_reservation)

registry.register_tool(
    "cancel_reservation",
    "Cancel the guest's own reservation (destructive — requires confirmation).",
    CancelReservationArgsSerializer,
    needs_confirmation=True,
    personas={PERSONA_GUEST, PERSONA_ADMIN},
    execute=_execute_cancel_reservation,
)(_propose_cancel_reservation)

registry.register_tool(
    "add_to_cart",
    "Add a menu item to the guest's active cart (requires confirmation).",
    AddToCartArgsSerializer,
    needs_confirmation=True,
    personas={PERSONA_GUEST, PERSONA_ADMIN},
    execute=_execute_add_to_cart,
)(_propose_add_to_cart)

registry.register_tool(
    "get_floor_status",
    "Admin-only: current floor status (open carts, pending reservations).",
    GetFloorStatusArgsSerializer,
    needs_confirmation=False,
    personas={PERSONA_ADMIN},
)(_execute_get_floor_status)

__all__ = [
    "_active_cart_session",
    "_execute_get_floor_status",
    "_resolve_own_reservation",
]
