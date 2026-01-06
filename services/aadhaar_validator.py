# services/aadhaar_validator.py
import re
from utils.verhoeff import validate as verhoeff_validate

def normalize_number(number: str) -> str:
    """Removes non-digit characters."""
    return re.sub(r"\D", "", number or "")

def validate_aadhaar_number(number: str) -> bool:
    """Checks if length is 12 and Verhoeff checksum passes."""
    digits = normalize_number(number)
    if len(digits) != 12:
        return False
    return verhoeff_validate(digits)

def mask_aadhaar(number: str) -> str:
    """Returns XXXX-XXXX-1234 format."""
    digits = normalize_number(number)
    if len(digits) < 4:
        return "****"
    return "XXXX-XXXX-" + digits[-4:]