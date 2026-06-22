from apps.restaurants.models import Table


def update_table_position(
    table: Table,
    *,
    position_x: int | None,
    position_y: int | None,
) -> Table:
    if position_x is not None:
        table.position_x = position_x
    if position_y is not None:
        table.position_y = position_y
    table.save(update_fields=["position_x", "position_y", "updated_at"])
    return table
