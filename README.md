# Aadhaar & PAN KYC  (Flask)

An end-to-end KYC flow supporting both Aadhaar and PAN cards: user details form, document upload + OCR, live selfie + face match, and risk assessment with rule-based decision (approve / manual / reject).

## What it does
- Collects Name, DOB, Aadhaar last 4, and contact (phone/email for OTP).
- OTP verification (mock-only; OTP is displayed on the page).
- Aadhaar upload → preprocess → OCR (EasyOCR) → heuristics (keywords, number, DOB).
- Live selfie capture in browser → face match against Aadhaar photo using DeepFace (RetinaFace + ArcFace, cosine similarity).
- Decision rules: hard rejects on mismatched DOB/last4, low face similarity, missing Aadhaar cues; manual review for weak matches; approve on strong signals.

## Current thresholds & rules
- Aadhaar last4: if provided and mismatched → reject; if provided but not detected → reject.
- PAN number: if provided and mismatched → reject; if provided but not detected → reject.
- DOB: if provided and mismatched → reject; if provided but missing in OCR → reject.
- Name: fuzzy score < 50 → reject; < 70 → manual; else OK.
- Face: distance < 0.40 → reject; < 0.60 → manual; else OK (Facenet model).
- OCR status: must be `CONFIRMED` to auto-pass; otherwise manual.
- Risk score: > 0.7 → reject; > 0.5 → manual; else OK.

## Tech stack
- Flask (API + inline UI)
- OCR.Space API for cloud-based OCR (requires API key)
- OpenCV for image preprocessing
- DeepFace (Facenet model + opencv detector) for optimized face matching
- RapidFuzz for name similarity
- Scikit-learn for risk modeling
- NumPy/TensorFlow/Keras backend via DeepFace

## Setup & run
1) Install Python 3.11+.
2) Install deps:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```
3) Run:
   ```bash
   python app.py
   ```
4) Open http://127.0.0.1:5000 and follow the multi-page KYC flow:
   - Page 1: Enter user details (Name, DOB, Aadhaar last4, PAN number).
   - Page 2: Upload Aadhaar and PAN documents.
   - Page 3: Capture live selfie for face verification.
   - Results: View KYC decision and risk assessment.

## Environment notes
- OTP is forced to mock: code is returned in `/otp/start` response and shown in UI.
- Model weights (DeepFace backends) download on first use; allow network on first run.
- To quiet TensorFlow logs, set `TF_CPP_MIN_LOG_LEVEL=2`.

## File map
- `app.py` – Multi-page routes, inline UI, decision logic.
- `services/face_service.py` – Optimized DeepFace face verification (Facenet + opencv).
- `services/ocr_service.py` – OCR + document heuristics (Aadhaar/PAN status, DOB, numbers).
- `services/image_preprocess.py` – Simple preprocessing/cropping.
- `services/aadhaar_validator.py` – Aadhaar number validation/masking.
- `services/pan_validator.py` – PAN number validation.
- `services/risk_model.py` – Risk scoring (ML model or heuristic fallback).
- `ml/train_model.py` – Risk model training script.
- `requirements.txt` – Dependencies.

## Notes on performance
- DeepFace on CPU can be slow; first call downloads weights. For faster runs, use a GPU-enabled environment or switch to a lighter DeepFace model/detector (e.g., Facenet512 + opencv) and retune thresholds.
