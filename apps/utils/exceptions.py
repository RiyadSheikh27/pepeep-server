from rest_framework.views import exception_handler
from django.utils import timezone


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None

    detail = response.data
    if isinstance(detail, dict) and "detail" in detail:
        message = str(detail["detail"])
        errors  = {"non_field_errors": [message]}
    elif isinstance(detail, dict):
        message = next(
            (str(v[0]) if isinstance(v, list) else str(v) for v in detail.values()),
            "Validation error."
        )
        errors = detail
    else:
        message = str(detail)
        errors  = {"non_field_errors": [message]}

    response.data = {
        "success":  False,
        "message":  message,
        "data":     None,
        "errors":   errors,
        "meta":     {"timestamp": timezone.now()},
    }
    return response
