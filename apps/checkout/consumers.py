import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser

class BranchOrderConsumer(AsyncWebsocketConsumer):
    """ CONNECTION """
    async def connect(self):
        self.branch_id  = self.scope["url_route"]["kwargs"]["branch_id"]
        self.group_name = f"branch_{self.branch_id}"
 
        # Authenticate
        user = self.scope.get("user")
        if not user or isinstance(user, AnonymousUser) or not user.is_authenticated:
            await self.close(code=4001)
            return
 
        # Authorise - employee must belong to this branch; owners/admins pass freely
        authorised = await self._is_authorised(user)
        if not authorised:
            await self.close(code=4003)
            return
 
        # Join branch group
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
 
        await self.send(text_data=json.dumps({
            "type": "connection_established",
            "message": f"Listening for orders on branch {self.branch_id}",
        }))

    """ DISCONNECTION """
    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
 
    #  Employees can send a ping to keep the socket alive.
    async def receive(self, text_data=None, bytes_data=None):
        try:
            payload = json.loads(text_data or "{}")
        except json.JSONDecodeError:
            return
 
        if payload.get("type") == "ping":
            await self.send(text_data=json.dumps({"type": "pong"}))
 

    """ HELPERS """
    async def user_arrived(self, event):
        """
        Pushed by the Celery task via channel_layer.group_send().
        Forwards the arrival popup to the connected employee.
        """
        await self.send(text_data=json.dumps({
            "type": "user_arrived",
            "order_id": event["order_id"],
            "order_number": event["order_number"],
            "customer_name": event.get("customer_name", ""),
            "car": event.get("car"),
            "items": event.get("items", []),
            "arrived_at": event.get("arrived_at"),
            "message": f"{event.get('customer_name', 'Customer')} has arrived!",
        }))

 
    @database_sync_to_async
    def _is_authorised(self, user) -> bool:
        """
        Synchronous DB check wrapped for async context.
 
        Rules:
          admin - always allowed
          owner - allowed if branch belongs to their restaurant
          employee - allowed only if assigned to this exact branch
        """
        if user.role == "admin":
            return True
 
        if user.role == "owner":
            from apps.restaurants.models import Branch
            return Branch.objects.filter(
                id=self.branch_id,
                restaurant__owner=user,
            ).exists()
 
        if user.role == "employee":
            emp = getattr(user, "employee_profile", None)
            if not emp:
                return False
            return str(emp.branch_id) == str(self.branch_id)
 
        return False