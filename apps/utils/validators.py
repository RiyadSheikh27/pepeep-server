import re
from django.core.exceptions import ValidationError

SA_PHONE_RE = re.compile(r"^\+9665\d{8}$")


def validate_sa_phone(value: str):
    if not SA_PHONE_RE.match(value.replace(" ", "")):
        raise ValidationError("Enter a valid Saudi mobile number: +9665XXXXXXXX")
