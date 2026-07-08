import re
import cv2
import shutil
import pytesseract

# Use the installed Tesseract binary on the current machine instead of a
# platform-specific hardcoded path.
tesseract_cmd = shutil.which("tesseract")
if tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = tesseract_cmd


def image_orientations(image):
    return {
        "original": image,
        "rotate_90_clockwise": cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE),
        "rotate_90_counterclockwise": cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE),
        "rotate_180": cv2.rotate(image, cv2.ROTATE_180),
    }


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


def ocr_variants(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    scaled = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    denoised = cv2.bilateralFilter(scaled, 11, 17, 17)
    _, otsu = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    adaptive = cv2.adaptiveThreshold(
        denoised,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        2
    )

    return [
        image,
        gray,
        scaled,
        otsu,
        adaptive,
        cv2.bitwise_not(otsu),
    ]


def extract_aadhaar_candidate(text):
    normalized = text.upper()
    compact = re.sub(r'[\s-]+', '', normalized)

    full_matches = re.findall(r'\d{12}', compact)
    if full_matches:
        return full_matches[-1]

    masked_matches = re.findall(r'(?:X{4}|\*{4})\D*(?:X{4}|\*{4})\D*(\d{4})', normalized)
    if masked_matches:
        return masked_matches[-1]

    digit_groups = re.findall(r'(?<!\d)\d{4}(?!\d)', normalized)
    date_parts = set()
    for date_match in re.findall(r'\b\d{1,2}[/-]\d{1,2}[/-](\d{4})\b', normalized):
        date_parts.add(date_match)

    aadhaar_context = any(word in normalized for word in ("AADHAAR", "AADHAR", "UIDAI", "VID", "GOVERNMENT OF INDIA"))
    candidates = [group for group in digit_groups if group not in date_parts]

    if aadhaar_context and candidates:
        return candidates[-1]

    return None


# ------------------------------------------
# TEXT EXTRACTION (LOCAL TESSERACT)
# ------------------------------------------
def extract_text_locally(image, stop_when=None):

    print("--- 🖥️ Running Tesseract OCR... ---")

    texts = []
    for orientation, oriented_image in image_orientations(image).items():
        for variant in ocr_variants(oriented_image):
            for psm in (6, 11, 12, 3):
                text = pytesseract.image_to_string(
                    variant,
                    config=f'--oem 3 --psm {psm}'
                )
                if text.strip():
                    texts.append(f"[{orientation}] {text}")
                    combined_text = " ".join(texts).replace('\n', ' ').strip()
                    if stop_when and stop_when(combined_text):
                        print("✅ Local OCR Output:", combined_text)
                        return combined_text

    clean_text = " ".join(texts).replace('\n', ' ').strip()

    print("✅ Local OCR Output:", clean_text)

    return clean_text


# ------------------------------------------
# AADHAAR EXTRACTION
# ------------------------------------------
def extract_aadhaar_text(image):

    full_text = extract_text_locally(image, stop_when=extract_aadhaar_candidate)

    if not full_text:
        return {"aadhaar_number": None, "full_text": ""}

    aadhaar_number = extract_aadhaar_candidate(full_text)
    if aadhaar_number:
        return {
            "aadhaar_number": aadhaar_number,
            "masked_number": mask_identifier(aadhaar_number),
            "full_text": full_text
        }

    return {"aadhaar_number": None, "masked_number": None, "full_text": full_text}


def mask_identifier(value):
    if not value:
        return None

    suffix = value[-4:]
    if len(value) <= 4:
        return f"XXXX XXXX {suffix}"

    return f"XXXX XXXX {suffix}"


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
