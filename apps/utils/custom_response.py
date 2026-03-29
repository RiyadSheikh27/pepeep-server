from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone


class APIResponse:

    @staticmethod
    def success(data=None, message="Request successful", status_code=status.HTTP_200_OK, meta=None):
        return Response({
            "success": True,
            "message": message,
            "data": data,
            "errors": None,
            "meta": {**(meta or {}), "timestamp": timezone.now()},
        }, status=status_code)

    @staticmethod
    def error(errors=None, message="Something went wrong", status_code=status.HTTP_400_BAD_REQUEST, meta=None):
        return Response({
            "success": False,
            "message": message,
            "data": None,
            "errors": errors,
            "meta": {**(meta or {}), "timestamp": timezone.now()},
        }, status=status_code)
