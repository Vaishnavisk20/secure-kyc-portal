import argparse
import json
import os
import sys

import cv2

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from services.face_service import verify_face_match
from services.ocr_service import extract_aadhaar_text, extract_pan_text


def read_image(path):
    image = cv2.imread(path)
    if image is None:
        raise ValueError(f"Could not read image: {path}")
    return image


def main():
    parser = argparse.ArgumentParser(description="Run local KYC OCR/face checks.")
    parser.add_argument("--aadhaar", required=True, help="Path to Aadhaar image")
    parser.add_argument("--selfie", help="Path to selfie/photo image")
    parser.add_argument("--pan", help="Optional path to PAN image")
    args = parser.parse_args()

    aadhaar_image = read_image(args.aadhaar)
    aadhaar_result = extract_aadhaar_text(aadhaar_image)

    output = {
        "aadhaar": {
            "number": aadhaar_result.get("masked_number"),
            "detected": bool(aadhaar_result.get("aadhaar_number")),
        }
    }

    if args.pan:
        pan_result = extract_pan_text(read_image(args.pan))
        output["pan"] = {
            "number": pan_result.get("pan_number"),
            "detected": bool(pan_result.get("pan_number")),
        }

    if args.selfie:
        face_result = verify_face_match(aadhaar_image, read_image(args.selfie))
        output["face"] = face_result

    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
