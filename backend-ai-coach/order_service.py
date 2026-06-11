"""
Unified order service for both daily delivery and weekly batch orders.

Currently uses mock order creation. When real delivery APIs are added,
only this module needs to change — all callers remain the same.
"""
import uuid
from typing import List, Optional
from pydantic import BaseModel

from meal_catalog_service import get_meal_by_id, MealItem


class OrderItem(BaseModel):
    id: str
    name: str
    provider: str
    price_eur: float


class OrderResponse(BaseModel):
    order_id: str
    status: str = "confirmed"
    order_type: str          # "daily_delivery" | "weekly_order"
    items: List[OrderItem]
    delivery_location: Optional[str] = None
    scheduled_time: Optional[str] = None
    total_price_eur: float


def _meal_to_order_item(meal: MealItem) -> OrderItem:
    return OrderItem(id=meal.id, name=meal.name, provider=meal.provider, price_eur=meal.price_eur)


def create_order(
    meal_ids: List[str],
    order_type: str,
    delivery_location: Optional[str] = None,
    scheduled_time: Optional[str] = None,
) -> OrderResponse:
    items: List[OrderItem] = []
    for mid in meal_ids:
        meal = get_meal_by_id(mid)
        if meal is None:
            raise ValueError(f"Unknown meal id: {mid}")
        items.append(_meal_to_order_item(meal))

    return OrderResponse(
        order_id=str(uuid.uuid4())[:8].upper(),
        order_type=order_type,
        items=items,
        delivery_location=delivery_location,
        scheduled_time=scheduled_time,
        total_price_eur=round(sum(i.price_eur for i in items), 2),
    )


def confirm_daily_delivery(
    meal_id: str,
    meal_slot: str,
    delivery_location: str,
    scheduled_time: Optional[str] = None,
) -> OrderResponse:
    return create_order(
        meal_ids=[meal_id],
        order_type="daily_delivery",
        delivery_location=delivery_location,
        scheduled_time=scheduled_time,
    )


def confirm_weekly_order(meal_ids: List[str]) -> OrderResponse:
    return create_order(meal_ids=meal_ids, order_type="weekly_order")
