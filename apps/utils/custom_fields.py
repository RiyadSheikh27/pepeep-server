"""
Custom serializer fields for the application.
"""
import os
from rest_framework import serializers
from django.conf import settings


class AbsoluteURLFileField(serializers.FileField):
    """
    A custom FileField that returns absolute URLs by prepending BASE_URL from .env
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def to_representation(self, value):
        """
        Convert the file field to its absolute URL representation.
        """
        if not value:
            return None

        # Get the relative URL from the parent FileField
        relative_url = super().to_representation(value)

        # Get BASE_URL from environment or settings
        base_url = os.getenv('BASE_URL', getattr(settings, 'BASE_URL', ''))

        # Remove trailing slash from base_url if present
        if base_url.endswith('/'):
            base_url = base_url.rstrip('/')

        # Remove leading slash from relative_url if present
        if relative_url.startswith('/'):
            relative_url = relative_url.lstrip('/')

        # Combine base_url and relative_url
        if base_url and relative_url:
            return f"{base_url}/{relative_url}"

        # Fallback to relative URL if base_url is not set
        return relative_url


class AbsoluteURLImageField(serializers.ImageField):
    """
    A custom ImageField that returns absolute URLs by prepending BASE_URL from .env
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def to_representation(self, value):
        """
        Convert the image field to its absolute URL representation.
        """
        if not value:
            return None

        # Get the relative URL from the parent ImageField
        relative_url = super().to_representation(value)

        # Get BASE_URL from environment or settings
        base_url = os.getenv('BASE_URL', getattr(settings, 'BASE_URL', ''))

        # Remove trailing slash from base_url if present
        if base_url.endswith('/'):
            base_url = base_url.rstrip('/')

        # Remove leading slash from relative_url if present
        if relative_url.startswith('/'):
            relative_url = relative_url.lstrip('/')

        # Combine base_url and relative_url
        if base_url and relative_url:
            return f"{base_url}/{relative_url}"

        # Fallback to relative URL if base_url is not set
        return relative_url