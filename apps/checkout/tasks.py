from celery import shared_task
from django.utils import timezone


@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def mark_user_arrived(self, order_id: str, latitude=None, longitude=None):
    """
    Triggered when customer taps "I Arrived".

    Steps:
      1. Update order.user_arrived + coords in the DB
      2. Build the arrival payload (order number, items, car details)
      3. Push payload to channel group  branch_{branch_id}  via Redis
         - connected employees receive an instant WebSocket popup
    """
    try:
        from .models import Order

        order = (
            Order.objects.select_related("customer", "car", "branch")
            .prefetch_related("items")
            .get(id=order_id)
        )

        # --- 1. DB update ------------------------------------------------------------------------------------
        if order.user_arrived:
            # Idempotent — already marked, still push in case WS missed it
            _push_arrival(order)
            return {"status": "already_arrived", "order_id": order_id}

        update_fields = ["user_arrived", "user_arrived_at", "updated_at"]
        order.user_arrived = True
        order.user_arrived_at = timezone.now()

        if latitude is not None:
            order.arrived_lat = latitude
            update_fields.append("arrived_lat")
        if longitude is not None:
            order.arrived_lon = longitude
            update_fields.append("arrived_lon")

        order.save(update_fields=update_fields)

        # --- 2. WebSocket push ------------------------------------------------------------------------------------
        _push_arrival(order)

        return {
            "status": "arrived",
            "order_id": order_id,
            "arrived_at": str(order.user_arrived_at),
        }

    except Exception as exc:
        raise self.retry(exc=exc)


# --- PRIVATE HELPER --------------------------------------------------------------------------------------


def _push_arrival(order):
    """
    Send the arrival event to all employees connected to this branch's
    WebSocket group.  Runs synchronously inside a Celery worker.
    """
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    channel_layer = get_channel_layer()
    if not channel_layer:
        # Channels / Redis not configured — skip silently
        return

    group_name = f"branch_{order.branch_id}"

    customer = order.customer
    car = order.car
    items_snap = [
        {
            "name": item.name,
            "quantity": item.quantity,
            "subtotal": str(item.subtotal),
        }
        for item in order.items.all()
    ]

    payload = {
        # Channels routing key — maps to  user_arrived()  method in consumer
        "type": "user_arrived",
        # Order info
        "order_id": str(order.id),
        "order_number": order.order_number,
        "items": items_snap,
        # Customer info
        "customer_name": customer.full_name if customer else "",
        # Car info
        "car": (
            {
                "model": car.car_model if car else "",
                "plate_number": car.plate_number if car else "",
                "color": car.color if car else "",
            }
            if car
            else None
        ),
        # Timing
        "arrived_at": str(order.user_arrived_at),
        "pickup_time": order.pickup_time,
    }

    async_to_sync(channel_layer.group_send)(group_name, payload)
