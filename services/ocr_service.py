import re
import cv2
import pytesseract

# 🔥 Set this correctly
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


# ------------------------------------------
# IMAGE PREPROCESSING (important for accuracy)
# ------------------------------------------
def preprocess_for_ocr(image):

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    gray = cv2.bilateralFilter(gray, 11, 17, 17)

    thresh = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        2
    )

    return thresh


# ------------------------------------------
# TEXT EXTRACTION (LOCAL TESSERACT)
# ------------------------------------------
def extract_text_locally(image):

    print("--- 🖥️ Running Tesseract OCR... ---")

    processed = preprocess_for_ocr(image)

    text = pytesseract.image_to_string(
        processed,
        config='--oem 3 --psm 6'
    )

    clean_text = text.replace('\n', ' ').strip()

    print("✅ Local OCR Output:", clean_text)

    return clean_text


# ------------------------------------------
# AADHAAR EXTRACTION
# ------------------------------------------
def extract_aadhaar_text(image):

    full_text = extract_text_locally(image)

    if not full_text:
        return {"aadhaar_number": None, "full_text": ""}

    clean_text = full_text.replace(" ", "").replace("-", "")

    matches = re.findall(r'\d{12}', clean_text)

    if matches:
        # Aadhaar number is usually at bottom → take last match
        return {
            "aadhaar_number": matches[-1],
            "full_text": full_text
        }

    return {"aadhaar_number": None, "full_text": full_text}


# ------------------------------------------
# PAN EXTRACTION
# ------------------------------------------
def extract_pan_text(image):

    full_text = extract_text_locally(image)

    if not full_text:
        return {"pan_number": None}

    words = full_text.split()

    for word in words:

        word = re.sub(r'[^A-Z0-9]', '', word.upper())

        if re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]$', word):
            return {"pan_number": word}

    return {"pan_number": None}
