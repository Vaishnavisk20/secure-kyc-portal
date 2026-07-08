import re

def validate_pan_number(pan_text: str) -> bool:
    """
    Validates PAN Structure (5 Letters - 4 Digits - 1 Letter).
    Example: ABCDE1234F
    """
    if not pan_text:
        return False
    
    # 1. Standardize
    pan = pan_text.strip().upper()
    
    # 2. Length Check
    if len(pan) != 10:
        return False

    # 3. Regex Check
    # ^ = Start, $ = End
    # [A-Z]{5} = 5 Letters
    # [0-9]{4} = 4 Digits
    # [A-Z]    = 1 Letter
    pattern = r'^[A-Z]{5}[0-9]{4}[A-Z]$'
    
    if re.match(pattern, pan):
        return True
        
    return False