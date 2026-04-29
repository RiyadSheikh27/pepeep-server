from django.urls import re_path
from .consumers import BranchOrderConsumer, CustomerOrderConsumer
 
websocket_urlpatterns = [
    re_path(
        r"^ws/orders/branch/(?P<branch_id>[0-9a-f-]+)/$",
        BranchOrderConsumer.as_asgi(),
    ),
    re_path(
        r"^ws/orders/(?P<order_id>[0-9a-f-]+)/status/$",   # ← NEW
        CustomerOrderConsumer.as_asgi(),
    ),
]