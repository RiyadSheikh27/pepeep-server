from rest_framework.views import exception_handler
from rest_framework import status
from django.utils import timezone


def custom_exception_handler(exc, context):
    """
    Wraps DRF's default exception handler output into the project's
    standard APIResponse envelope.
    """
    response = exception_handler(exc, context)

    if response is not None:
        response.data = {
            "success": False,
            "message": _extract_message(response.data),
            "data": None,
            "errors": _normalise_errors(response.data),
            "meta": {"timestamp": timezone.now()},
        }

    return response


# --- Helpers -------------------------------------------

def _extract_message(data) -> str:
    if isinstance(data, dict):
        if "detail" in data:
            return str(data["detail"])
        # First field error becomes the headline message
        for key, value in data.items():
            if isinstance(value, list) and value:
                return str(value[0])
            if isinstance(value, str):
                return value
    if isinstance(data, list) and data:
        return str(data[0])
    return "An error occurred."


def _normalise_errors(data):
    """Always return errors as a dict of field → [messages]."""
    if isinstance(data, dict):
        if "detail" in data:
            return {"non_field_errors": [str(data["detail"])]}
        return {
            k: v if isinstance(v, list) else [str(v)]
            for k, v in data.items()
        }
    if isinstance(data, list):
        return {"non_field_errors": [str(e) for e in data]}
    return {"non_field_errors": [str(data)]}
