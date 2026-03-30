"""
Custom parser that converts bracket-notation form-data keys into nested dicts/lists.

Handles:
    branches[0][name]                         → branches[0].name
    branches[0][opening_hours][0][day]        → branches[0].opening_hours[0].day
    branches[0][opening_hours][0][shifts][0][open] → ...

Usage — add to a view:
    parser_classes = [NestedMultiPartParser, JSONParser]

Or set globally in settings.py:
    REST_FRAMEWORK = {
        "DEFAULT_PARSER_CLASSES": [
            "apps.utils.parsers.NestedMultiPartParser",
            "rest_framework.parsers.JSONParser",
        ]
    }
"""
import re
from rest_framework.parsers import MultiPartParser
from django.http import QueryDict


def _set_nested(d, keys, value):
    """Recursively set a value inside nested dicts/lists using a key path."""
    key = keys[0]

    # Numeric key → list
    if key.isdigit():
        idx = int(key)
        if not isinstance(d, list):
            raise ValueError("Expected list")
        while len(d) <= idx:
            d.append({})
        if len(keys) == 1:
            d[idx] = value
        else:
            if not isinstance(d[idx], (dict, list)):
                d[idx] = {} if not keys[1].isdigit() else []
            _set_nested(d[idx], keys[1:], value)
    else:
        if len(keys) == 1:
            d[key] = value
        else:
            next_key = keys[1]
            if next_key.isdigit():
                d.setdefault(key, [])
            else:
                d.setdefault(key, {})
            _set_nested(d[key], keys[1:], value)


def _parse_bracket_key(flat_key):
    """
    'branches[0][opening_hours][0][day]'
    → ['branches', '0', 'opening_hours', '0', 'day']
    """
    parts = re.split(r'\[|\]\[|\]', flat_key)
    return [p for p in parts if p != '']


def flatten_to_nested(data: QueryDict, files=None) -> dict:
    """Convert a flat QueryDict with bracket-notation keys into a nested dict."""
    result = {}

    for flat_key, values in data.lists():
        keys = _parse_bracket_key(flat_key)
        value = values[-1] if len(values) == 1 else values   # single value or list
        try:
            if keys[0].isdigit():
                # top-level numeric — rare, skip
                continue
            _set_nested(result, keys, value)
        except Exception:
            result[flat_key] = value   # fallback: keep flat

    if files:
        for flat_key, file_obj in files.items():
            keys = _parse_bracket_key(flat_key)
            try:
                _set_nested(result, keys, file_obj)
            except Exception:
                result[flat_key] = file_obj

    return result


class NestedMultiPartParser(MultiPartParser):
    """
    Drop-in replacement for MultiPartParser.
    Parses bracket-notation keys into proper nested structures so DRF
    serializers with nested fields (like BranchCreateSerializer) work correctly.
    """

    def parse(self, stream, media_type=None, parser_context=None):
        result = super().parse(stream, media_type, parser_context)
        nested = flatten_to_nested(result.data, result.files)
        return type(result)(nested, result.files)