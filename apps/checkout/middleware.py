from urllib.parse import parse_qs
from channels.middleware import BaseMiddleware
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser


@database_sync_to_async
def _get_user_from_token(token_str: str):
    """
    Validate the JWT access token and return the User, or AnonymousUser on failure.
    Uses SimpleJWT's UntypedToken so it respects your existing token settings.
    """
    try:
        from rest_framework_simplejwt.tokens import UntypedToken
        from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
        from rest_framework_simplejwt.settings import api_settings
        from django.contrib.auth import get_user_model

        User = get_user_model()

        # Validate — raises on invalid / expired
        UntypedToken(token_str)

        # Decode without re-validating (already validated above)
        import jwt
        decoded = jwt.decode(
            token_str,
            options={"verify_signature": False},
        )
        user_id = decoded.get(api_settings.USER_ID_CLAIM)   # defaults to "user_id"
        return User.objects.select_related("employee_profile__branch").get(
            **{api_settings.USER_ID_FIELD: user_id}
        )
    except Exception:
        return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    """
    Drop-in Channels middleware that authenticates WebSocket connections via JWT.

    Usage in asgi.py:
        from apps.checkout.middleware import JWTAuthMiddleware
        application = JWTAuthMiddleware(URLRouter(websocket_urlpatterns))
    """

    async def __call__(self, scope, receive, send):
        if scope["type"] == "websocket":
            query_string = scope.get("query_string", b"").decode()
            params       = parse_qs(query_string)
            token_list   = params.get("token", [])
            token_str    = token_list[0] if token_list else ""

            scope["user"] = await _get_user_from_token(token_str) if token_str else AnonymousUser()

        return await super().__call__(scope, receive, send)