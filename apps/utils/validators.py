import re
from django.core.exceptions import ValidationError


# --- Phone --------------------------------------------------------------------------

SA_PHONE_REGEX = re.compile(r"^\+9665\d{8}$")
GENERIC_PHONE_REGEX = re.compile(r"^\+\d{7,15}$")


def validate_saudi_phone(value: str) -> None:
    """Validates a Saudi mobile number in E.164 format (+9665XXXXXXXX)."""
    if not SA_PHONE_REGEX.match(value):
        raise ValidationError(
            "Enter a valid Saudi mobile number in format +9665XXXXXXXX."
        )


def validate_phone(value: str) -> None:
    """Generic E.164 phone validator."""
    if not GENERIC_PHONE_REGEX.match(value):
        raise ValidationError(
            "Enter a valid phone number in E.164 format (e.g. +9665XXXXXXXX)."
        )


# --- IBAN --------------------------------------------------------------------------

SA_IBAN_REGEX = re.compile(r"^SA\d{22}$")


def validate_saudi_iban(value: str) -> None:
    """Validates a Saudi IBAN: SA followed by 22 digits."""
    cleaned = value.replace(" ", "").upper()
    if not SA_IBAN_REGEX.match(cleaned):
        raise ValidationError(
            "Enter a valid Saudi IBAN (SA followed by 22 digits)."
        )


# --- CR / VAT --------------------------------------------------------------------

CR_REGEX = re.compile(r"^\d{10}$")
VAT_REGEX = re.compile(r"^3\d{14}$")


def validate_cr_number(value: str) -> None:
    """Saudi CR Unified Number — 10 digits."""
    if not CR_REGEX.match(value):
        raise ValidationError("CR Unified Number must be exactly 10 digits.")


def validate_vat_number(value: str) -> None:
    """Saudi VAT Registration Number — 15 digits starting with 3."""
    if not VAT_REGEX.match(value):
        raise ValidationError(
            "VAT Registration Number must be 15 digits starting with 3."
        )


# --- File uploads ------------------------------------------------------

def validate_pdf(value) -> None:
    if not value.name.lower().endswith(".pdf"):
        raise ValidationError("Only PDF files are allowed.")
    if value.size > 10 * 1024 * 1024:  # 10 MB
        raise ValidationError("PDF file size must not exceed 10 MB.")


def validate_image(value) -> None:
    allowed = (".jpg", ".jpeg", ".png", ".webp")
    if not any(value.name.lower().endswith(ext) for ext in allowed):
        raise ValidationError("Only JPG, PNG, or WebP images are allowed.")
    if value.size > 5 * 1024 * 1024:  # 5 MB
        raise ValidationError("Image size must not exceed 5 MB.")
