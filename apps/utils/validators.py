import re
from django.core.exceptions import ValidationError

SA_PHONE_RE = re.compile(r"^\+880\d{10}$")


def validate_sa_phone(value: str):
    if not SA_PHONE_RE.match(value.replace(" ", "")):
        raise ValidationError("Enter a valid Saudi mobile number: +880XXXXXXXX")
