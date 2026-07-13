from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from apps.authentication.models import RoleCode
from apps.authentication.services import issue_tokens_with_restaurant
from apps.editor.consumers import HallConsumer, StaffReservationsConsumer
from apps.orders.models import Session, SessionStatus
from apps.reservations.models import Reservation, ReservationStatus
from apps.reservations.services import (
    create_reservation,
    reschedule_reservation,
    update_reservation_status,
)
from apps.restaurants.models import Restaurant, Table
from common.channels import hall_group_name, staff_group_name
from common.hall_events import (
    emit_hall_new_reservation,
    emit_hall_reservation_cancelled,
    emit_hall_reservations_updated,
    emit_hall_table_status_changed,
)
from common.notification_events import emit_cart_created
from core.routing import application
from tests.conftest import RestaurantFactory, UserFactory


@pytest.mark.django_db
def test_emit_hall_table_status_changed_sends_to_group(restaurant: Any, table: Any) -> None:
    user = UserFactory.build(role=RoleCode.ADMIN)
    user.save()

    with patch("common.hall_events.get_channel_layer") as mock_get_layer:
        mock_layer = AsyncMock()
        mock_get_layer.return_value = mock_layer

        emit_hall_table_status_changed(
            restaurant.id,
            table_id=str(table.public_id),
            previous_status="free",
            current_status="occupied",
            session_id="test-session-id",
            actor=user,
        )

        mock_layer.group_send.assert_called_once()
        call_args = mock_layer.group_send.call_args
        assert call_args[0][0] == hall_group_name(restaurant.id)
        event = call_args[0][1]["event"]
        assert event["event_name"] == "HALL_TABLE_STATUS_CHANGED"
        assert event["schema_version"] == "1"
        assert event["table_id"] == str(table.public_id)
        assert event["previous_status"] == "free"
        assert event["current_status"] == "occupied"
        assert event["session_id"] == "test-session-id"
        assert event["actor_id"] == user.pk
        assert event["actor_role"] == RoleCode.ADMIN


@pytest.mark.django_db
def test_emit_hall_new_reservation_sends_to_group(restaurant: Any, table: Any) -> None:
    user = UserFactory.build(role=RoleCode.WAITER)
    user.save()

    with patch("common.hall_events.get_channel_layer") as mock_get_layer:
        mock_layer = AsyncMock()
        mock_get_layer.return_value = mock_layer

        emit_hall_new_reservation(
            restaurant.id,
            reservation_id="test-reservation-id",
            table_id=str(table.public_id),
            start_at="2026-06-15T18:00:00Z",
            end_at="2026-06-15T20:00:00Z",
            actor=user,
        )

        assert mock_layer.group_send.call_count == 2

        hall_call = mock_layer.group_send.call_args_list[0]
        assert hall_call[0][0] == hall_group_name(restaurant.id)
        event = hall_call[0][1]["event"]
        assert event["event_name"] == "HALL_NEW_RESERVATION"
        assert event["schema_version"] == "1"
        assert event["reservation_id"] == "test-reservation-id"
        assert event["table_id"] == str(table.public_id)
        assert event["actor_id"] == user.pk
        assert event["actor_role"] == RoleCode.WAITER

        staff_call = mock_layer.group_send.call_args_list[1]
        assert staff_call[0][0] == staff_group_name(restaurant.id)
        assert staff_call[0][1]["event"]["event_name"] == "HALL_NEW_RESERVATION"


@pytest.mark.django_db(databases=["default"], transaction=True)
def test_create_reservation_emits_hall_event(restaurant: Any, table: Any) -> None:
    user = UserFactory.build(role=RoleCode.CUSTOMER)
    user.save()
    start_at = timezone.now() + timedelta(hours=2)
    end_at = start_at + timedelta(hours=2)

    with patch("apps.reservations.services.emit_hall_new_reservation") as mock_emit:
        reservation = create_reservation(
            restaurant_id=restaurant.id,
            customer_id=user.pk,
            table_id=str(table.public_id),
            guest_count=2,
            start_at=start_at,
            end_at=end_at,
            actor=user,
        )

        mock_emit.assert_called_once()
        call_args = mock_emit.call_args
        assert call_args[0][0] == restaurant.id
        call_kwargs = call_args[1]
        assert call_kwargs["reservation_id"] == str(reservation.public_id)
        assert call_kwargs["table_id"] == str(table.public_id)
        assert call_kwargs["actor"] == user


@pytest.mark.django_db
def test_create_reservation_without_actor_skips_event(restaurant: Any, table: Any) -> None:
    user = UserFactory.build(role=RoleCode.CUSTOMER)
    user.save()
    start_at = timezone.now() + timedelta(hours=2)
    end_at = start_at + timedelta(hours=2)

    with patch("apps.reservations.services.emit_hall_new_reservation") as mock_emit:
        create_reservation(
            restaurant_id=restaurant.id,
            customer_id=user.pk,
            table_id=str(table.public_id),
            guest_count=2,
            start_at=start_at,
            end_at=end_at,
        )

        mock_emit.assert_not_called()


@pytest.mark.django_db
def test_update_reservation_status_denies_customer(restaurant: Any, table: Any) -> None:
    customer = UserFactory.build(role=RoleCode.CUSTOMER)
    customer.save()

    admin = UserFactory.build(role=RoleCode.ADMIN)
    admin.save()

    reservation = Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        customer=customer,
        guest_count=2,
        start_at=timezone.now() + timedelta(hours=1),
        end_at=timezone.now() + timedelta(hours=3),
        status=ReservationStatus.PENDING,
    )

    with pytest.raises(Exception) as exc_info:
        update_reservation_status(reservation, new_status=ReservationStatus.ACTIVE, actor=customer)
    assert "admin and waiter" in str(exc_info.value).lower()


@pytest.mark.django_db
def test_update_reservation_status_denies_cook(restaurant: Any, table: Any) -> None:
    cook = UserFactory.build(role=RoleCode.COOK)
    cook.save()

    reservation = Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        guest_count=2,
        start_at=timezone.now() + timedelta(hours=1),
        end_at=timezone.now() + timedelta(hours=3),
        status=ReservationStatus.PENDING,
    )

    with pytest.raises(Exception) as exc_info:
        update_reservation_status(reservation, new_status=ReservationStatus.ACTIVE, actor=cook)
    assert "admin and waiter" in str(exc_info.value).lower()


@pytest.mark.django_db
def test_update_reservation_status_allows_admin(restaurant: Any, table: Any) -> None:
    admin = UserFactory.build(role=RoleCode.ADMIN)
    admin.save()

    reservation = Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        guest_count=2,
        start_at=timezone.now() + timedelta(hours=1),
        end_at=timezone.now() + timedelta(hours=3),
        status=ReservationStatus.PENDING,
    )

    updated = update_reservation_status(reservation, new_status=ReservationStatus.ACTIVE, actor=admin)
    assert updated.status == ReservationStatus.ACTIVE


@pytest.mark.django_db
def test_update_reservation_status_allows_waiter(restaurant: Any, table: Any) -> None:
    waiter = UserFactory.build(role=RoleCode.WAITER)
    waiter.save()

    reservation = Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        guest_count=2,
        start_at=timezone.now() + timedelta(hours=1),
        end_at=timezone.now() + timedelta(hours=3),
        status=ReservationStatus.PENDING,
    )

    updated = update_reservation_status(reservation, new_status=ReservationStatus.ACTIVE, actor=waiter)
    assert updated.status == ReservationStatus.ACTIVE


@pytest.mark.django_db
def test_update_reservation_status_rejects_invalid_transition(restaurant: Any, table: Any) -> None:
    admin = UserFactory.build(role=RoleCode.ADMIN)
    admin.save()

    reservation = Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        guest_count=2,
        start_at=timezone.now() + timedelta(hours=1),
        end_at=timezone.now() + timedelta(hours=3),
        status=ReservationStatus.COMPLETED,
    )

    with pytest.raises(Exception) as exc_info:
        update_reservation_status(reservation, new_status=ReservationStatus.ACTIVE, actor=admin)
    assert "cannot transition" in str(exc_info.value).lower()


@pytest.mark.django_db(databases=["default"], transaction=True)
def test_session_create_emits_table_status_changed(restaurant: Any, table: Any) -> None:
    admin = UserFactory.build(role=RoleCode.ADMIN)
    admin.save()

    with patch("apps.orders.views.emit_hall_table_status_changed") as mock_emit:
        client = APIClient()
        access, _ = issue_tokens_with_restaurant(admin, restaurant.id)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        response = client.post(
            "/api/orders/sessions/",
            {
                "table": table.public_id,
                "guest_count": 2,
                "currency": "UAH",
                "opened_at": timezone.now().isoformat(),
            },
            format="json",
        )

        assert response.status_code == 201
        mock_emit.assert_called_once()
        call_kwargs = mock_emit.call_args[1]
        assert call_kwargs["previous_status"] == "free"
        assert call_kwargs["current_status"] == "occupied"
        assert call_kwargs["actor"] == admin


@pytest.mark.django_db(databases=["default"], transaction=True)
def test_session_close_emits_table_status_changed(restaurant: Any, table: Any) -> None:
    admin = UserFactory.build(role=RoleCode.ADMIN)
    admin.save()

    customer = UserFactory.build(role=RoleCode.CUSTOMER)
    customer.save()

    reservation = Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        customer=customer,
        guest_count=2,
        start_at=timezone.now(),
        end_at=timezone.now() + timedelta(hours=2),
        status=ReservationStatus.ACTIVE,
    )

    session = Session.objects.create(
        restaurant=restaurant,
        table=table,
        reservation=reservation,
        opened_by=admin,
        guest_count=2,
        status=SessionStatus.OPEN,
        currency="UAH",
        opened_at=timezone.now(),
    )

    with patch("apps.orders.services.cart.emit_hall_table_status_changed") as mock_emit:
        client = APIClient()
        access, _ = issue_tokens_with_restaurant(admin, restaurant.id)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        response = client.patch(
            f"/api/orders/sessions/{session.public_id}/",
            {"status": SessionStatus.CLOSED},
            format="json",
        )

        assert response.status_code == 200
        mock_emit.assert_called_once()
        call_kwargs = mock_emit.call_args[1]
        assert call_kwargs["previous_status"] == "occupied"
        assert call_kwargs["current_status"] == "free"
        assert call_kwargs["actor"] == admin


@pytest.mark.django_db
def test_hall_consumer_rejects_unauthenticated() -> None:
    async def _test() -> None:
        communicator = WebsocketCommunicator(HallConsumer.as_asgi(), "/ws/hall/")
        await communicator.connect()
        close_code = await communicator.receive_output(timeout=5)
        assert close_code["type"] == "websocket.close"
        assert close_code["code"] == 4001

    asyncio.run(_test())


@pytest.mark.django_db
def test_staff_reservations_consumer_rejects_unauthenticated() -> None:
    async def _test() -> None:
        communicator = WebsocketCommunicator(StaffReservationsConsumer.as_asgi(), "/ws/staff/reservations/")
        await communicator.connect()
        close_code = await communicator.receive_output(timeout=5)
        assert close_code["type"] == "websocket.close"
        assert close_code["code"] == 4001

    asyncio.run(_test())


@pytest.mark.django_db(databases=["default"], transaction=True)
def test_staff_reservations_consumer_rejects_customer(restaurant: Any) -> None:
    async def _test() -> None:
        user = await sync_to_async(UserFactory.build)(role=RoleCode.CUSTOMER)
        await sync_to_async(user.save)()
        access, _ = await sync_to_async(issue_tokens_with_restaurant)(user, restaurant.id)
        communicator = WebsocketCommunicator(
            application,
            "/ws/staff/reservations/",
            subprotocols=["access_token", access],
        )
        await communicator.connect()
        close_code = await communicator.receive_output(timeout=5)
        assert close_code["type"] == "websocket.close"
        assert close_code["code"] == 4003
        await communicator.disconnect()

    asyncio.run(_test())


pytestmark_rt = pytest.mark.django_db(databases=["default"], transaction=True)


@pytest.fixture(autouse=True)
def _inmemory_channel_layer(settings: Any) -> None:
    settings.CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }


async def _connect_hall(user: Any, restaurant_id: int) -> WebsocketCommunicator:
    access, _ = await sync_to_async(issue_tokens_with_restaurant)(user, restaurant_id)
    communicator = WebsocketCommunicator(
        application,
        "/ws/hall/",
        subprotocols=["access_token", access],
    )
    connected, _ = await communicator.connect()
    assert connected
    return communicator


async def _post_session(user: Any, restaurant_id: int, table_id: str) -> int:
    def _do() -> int:
        client = APIClient()
        access, _ = issue_tokens_with_restaurant(user, restaurant_id)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        response = client.post(
            "/api/orders/sessions/",
            {
                "table": table_id,
                "guest_count": 2,
                "currency": "UAH",
                "opened_at": timezone.now().isoformat(),
            },
            format="json",
        )
        return response.status_code

    return await sync_to_async(_do)()


async def _patch_session(user: Any, restaurant_id: int, session_id: str, status: str) -> int:
    def _do() -> int:
        client = APIClient()
        access, _ = issue_tokens_with_restaurant(user, restaurant_id)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        response = client.patch(
            f"/api/orders/sessions/{session_id}/",
            {"status": status},
            format="json",
        )
        return response.status_code

    return await sync_to_async(_do)()


@pytestmark_rt
async def test_session_create_broadcasts_to_hall_subscriber(restaurant: Any, table: Any) -> None:
    admin = await sync_to_async(UserFactory.build)(role=RoleCode.ADMIN)
    await sync_to_async(admin.save)()

    communicator = await _connect_hall(admin, restaurant.id)

    status_code = await _post_session(admin, restaurant.id, str(table.public_id))
    assert status_code == 201

    event = await communicator.receive_json_from(timeout=5)
    assert event["event_name"] == "HALL_TABLE_STATUS_CHANGED"
    assert event["table_id"] == str(table.public_id)
    assert event["previous_status"] == "free"
    assert event["current_status"] == "occupied"

    await communicator.disconnect()


@pytestmark_rt
async def test_session_close_broadcasts_to_hall_subscriber(restaurant: Any, table: Any) -> None:
    admin = await sync_to_async(UserFactory.build)(role=RoleCode.ADMIN)
    await sync_to_async(admin.save)()

    def _create_session() -> Session:
        reservation = Reservation.objects.create(
            restaurant=restaurant,
            table=table,
            customer=None,
            guest_count=2,
            start_at=timezone.now(),
            end_at=timezone.now() + timedelta(hours=2),
            status=ReservationStatus.ACTIVE,
        )
        return Session.objects.create(
            restaurant=restaurant,
            table=table,
            reservation=reservation,
            opened_by=admin,
            guest_count=2,
            status=SessionStatus.OPEN,
            currency="UAH",
            opened_at=timezone.now(),
        )

    session = await sync_to_async(_create_session)()

    communicator = await _connect_hall(admin, restaurant.id)

    status_code = await _patch_session(admin, restaurant.id, str(session.public_id), SessionStatus.CLOSED)
    assert status_code == 200

    event = await communicator.receive_json_from(timeout=5)
    assert event["event_name"] == "HALL_TABLE_STATUS_CHANGED"
    assert event["table_id"] == str(table.public_id)
    assert event["previous_status"] == "occupied"
    assert event["current_status"] == "free"

    await communicator.disconnect()


@pytestmark_rt
async def test_hall_event_does_not_leak_across_restaurants(restaurant: Any, table: Any) -> None:
    other_restaurant = cast(
        Restaurant,
        await sync_to_async(RestaurantFactory)(name="Other Restaurant"),
    )
    other_admin = await sync_to_async(UserFactory.build)(role=RoleCode.ADMIN)
    await sync_to_async(other_admin.save)()

    admin = await sync_to_async(UserFactory.build)(role=RoleCode.ADMIN)
    await sync_to_async(admin.save)()

    other_comm = await _connect_hall(other_admin, other_restaurant.id)
    comm = await _connect_hall(admin, restaurant.id)

    status_code = await _post_session(admin, restaurant.id, str(table.public_id))
    assert status_code == 201

    event = await comm.receive_json_from(timeout=5)
    assert event["event_name"] == "HALL_TABLE_STATUS_CHANGED"

    with pytest.raises(asyncio.TimeoutError):
        await other_comm.receive_json_from(timeout=0.5)

    await comm.disconnect()
    try:
        await other_comm.disconnect()
    except asyncio.CancelledError:
        pass


@pytest.mark.django_db
def test_emit_hall_reservation_cancelled_sends_to_group(restaurant: Any, table: Any) -> None:
    user = UserFactory.build(role=RoleCode.ADMIN)
    user.save()

    with patch("common.hall_events.get_channel_layer") as mock_get_layer:
        mock_layer = AsyncMock()
        mock_get_layer.return_value = mock_layer

        emit_hall_reservation_cancelled(
            restaurant.id,
            reservation_id="test-reservation-id",
            table_id=str(table.public_id),
            actor=user,
        )

        assert mock_layer.group_send.call_count == 2

        hall_call = mock_layer.group_send.call_args_list[0]
        assert hall_call[0][0] == hall_group_name(restaurant.id)
        event = hall_call[0][1]["event"]
        assert event["event_name"] == "HALL_RESERVATION_CANCELLED"
        assert event["schema_version"] == "1"
        assert event["reservation_id"] == "test-reservation-id"
        assert event["table_id"] == str(table.public_id)
        assert event["actor_id"] == user.pk
        assert event["actor_role"] == RoleCode.ADMIN

        staff_call = mock_layer.group_send.call_args_list[1]
        assert staff_call[0][0] == staff_group_name(restaurant.id)
        assert staff_call[0][1]["event"]["event_name"] == "HALL_RESERVATION_CANCELLED"


@pytest.mark.django_db(databases=["default"], transaction=True)
def test_update_reservation_status_cancel_emits_event(restaurant: Any, table: Any) -> None:
    admin = UserFactory.build(role=RoleCode.ADMIN)
    admin.save()

    reservation = Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        guest_count=2,
        start_at=timezone.now() + timedelta(hours=1),
        end_at=timezone.now() + timedelta(hours=3),
        status=ReservationStatus.PENDING,
    )

    with patch("apps.reservations.services.emit_hall_reservation_cancelled") as mock_emit:
        update_reservation_status(reservation, new_status=ReservationStatus.CANCELLED, actor=admin)

        mock_emit.assert_called_once()
        call_kwargs = mock_emit.call_args[1]
        assert call_kwargs["reservation_id"] == str(reservation.public_id)
        assert call_kwargs["table_id"] == str(table.public_id)
        assert call_kwargs["actor"] == admin


@pytest.mark.django_db
def test_emit_hall_reservations_updated_broadcasts_and_is_not_deduped(restaurant: Any, table: Any) -> None:
    # HALL_RESERVATIONS_UPDATED carries no event_id, so consecutive emits must all
    # broadcast. Regression for the empty-event_id dedup collision that dropped every
    # such event after the first within the dedup TTL.
    cache.clear()

    with patch("common.hall_events.get_channel_layer") as mock_get_layer:
        mock_layer = AsyncMock()
        mock_get_layer.return_value = mock_layer

        emit_hall_reservations_updated(restaurant.id, table_ids=[str(table.public_id)])
        emit_hall_reservations_updated(restaurant.id, table_ids=[str(table.public_id)])

        assert mock_layer.group_send.call_count == 4
        event = mock_layer.group_send.call_args[0][1]["event"]
        assert event["event_name"] == "HALL_RESERVATIONS_UPDATED"
        assert event["table_ids"] == [str(table.public_id)]
        assert "event_id" not in event


@pytest.mark.django_db
def test_hall_event_with_event_id_still_dedups(restaurant: Any, table: Any) -> None:
    # Events that DO carry an event_id must still dedup true duplicates.
    # The hall group deduplicates, but the staff group does not (it receives all).
    cache.clear()
    user = UserFactory.build(role=RoleCode.ADMIN)
    user.save()

    with patch("common.hall_events.get_channel_layer") as mock_get_layer:
        mock_layer = AsyncMock()
        mock_get_layer.return_value = mock_layer

        for _ in range(2):
            emit_hall_reservation_cancelled(
                restaurant.id,
                reservation_id="dup-reservation-id",
                table_id=str(table.public_id),
                actor=user,
            )

        # 1st emit: hall (1) + staff (1) = 2 calls
        # 2nd emit: hall deduped (0) + staff (1) = 1 call
        assert mock_layer.group_send.call_count == 3


@pytest.mark.django_db(databases=["default"], transaction=True)
def test_reschedule_reservation_emits_hall_reservations_updated(
    restaurant: Any, table: Any, zone: Any
) -> None:
    # A single-PATCH reschedule must notify the floor for both the old and new table.
    new_table = Table.objects.create(
        restaurant=restaurant,
        public_number="T2",
        capacity=4,
        zone=zone,
        active=True,
    )
    start_at = timezone.now() + timedelta(hours=2)
    reservation = Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        guest_count=2,
        start_at=start_at,
        end_at=start_at + timedelta(hours=2),
        status=ReservationStatus.PENDING,
    )

    with patch("apps.reservations.services.emit_hall_reservations_updated") as mock_emit:
        reschedule_reservation(reservation=reservation, validated_data={"table": new_table})

        mock_emit.assert_called_once()
        assert mock_emit.call_args[0][0] == restaurant.id
        assert set(mock_emit.call_args[1]["table_ids"]) == {
            str(table.public_id),
            str(new_table.public_id),
        }


@pytest.mark.django_db
def test_emit_hall_reservations_updated_broadcasts_to_hall_and_staff_groups(
    restaurant: Any, table: Any
) -> None:
    cache.clear()

    with patch("common.hall_events.get_channel_layer") as mock_get_layer:
        mock_layer = AsyncMock()
        mock_get_layer.return_value = mock_layer

        emit_hall_reservations_updated(restaurant.id, table_ids=[str(table.public_id)])

        assert mock_layer.group_send.call_count == 2

        hall_call = mock_layer.group_send.call_args_list[0]
        assert hall_call[0][0] == hall_group_name(restaurant.id)
        assert hall_call[0][1]["type"] == "hall.event"
        assert hall_call[0][1]["event"]["event_name"] == "HALL_RESERVATIONS_UPDATED"

        staff_call = mock_layer.group_send.call_args_list[1]
        assert staff_call[0][0] == staff_group_name(restaurant.id)
        assert staff_call[0][1]["type"] == "hall.event"
        assert staff_call[0][1]["event"]["event_name"] == "HALL_RESERVATIONS_UPDATED"


async def _connect_staff_reservations(user: Any, restaurant_id: int) -> WebsocketCommunicator:
    access, _ = await sync_to_async(issue_tokens_with_restaurant)(user, restaurant_id)
    communicator = WebsocketCommunicator(
        application,
        "/ws/staff/reservations/",
        subprotocols=["access_token", access],
    )
    connected, _ = await communicator.connect()
    assert connected
    return communicator


@pytestmark_rt
async def test_staff_reservations_consumer_receives_hall_reservations_updated(
    restaurant: Any, table: Any
) -> None:
    admin = await sync_to_async(UserFactory.build)(role=RoleCode.ADMIN)
    await sync_to_async(admin.save)()

    communicator = await _connect_staff_reservations(admin, restaurant.id)

    await sync_to_async(emit_hall_reservations_updated)(
        restaurant.id,
        table_ids=[str(table.public_id)],
    )

    event = await communicator.receive_json_from(timeout=5)
    assert event["event_name"] == "HALL_RESERVATIONS_UPDATED"
    assert event["table_ids"] == [str(table.public_id)]

    await communicator.disconnect()


@pytestmark_rt
async def test_staff_reservations_consumer_survives_notification_broadcast(
    restaurant: Any, table: Any
) -> None:
    admin = await sync_to_async(UserFactory.build)(role=RoleCode.ADMIN)
    await sync_to_async(admin.save)()

    communicator = await _connect_staff_reservations(admin, restaurant.id)

    await sync_to_async(emit_cart_created)(
        restaurant.id,
        session_id="session-1",
        table_number=table.public_number,
        guest_name="Alice",
    )
    await sync_to_async(emit_hall_reservations_updated)(
        restaurant.id,
        table_ids=[str(table.public_id)],
    )

    event = await communicator.receive_json_from(timeout=5)
    assert event["event_name"] == "HALL_RESERVATIONS_UPDATED"
    assert event["table_ids"] == [str(table.public_id)]

    await communicator.disconnect()
