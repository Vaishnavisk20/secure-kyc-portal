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
- Face: similarity score >= 70 → approve; >= 50 → manual review; below 50 → reject.
- OCR status: must be `CONFIRMED` to auto-pass; otherwise manual.
- Risk score: > 0.7 → reject; > 0.5 → manual; else OK.

## Tech stack
- Flask (API + inline UI)
- OCR.Space API for cloud-based OCR (requires API key)
- OpenCV for image preprocessing
- DeepFace (ArcFace model + RetinaFace detector) for face matching
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
   - Login: `admin` / `admin123` by default.
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
- `services/face_service.py` – DeepFace verification with ArcFace, RetinaFace, orientation handling, and ID face crops.
- `services/ocr_service.py` – OCR + document heuristics (Aadhaar/PAN status, DOB, numbers).
- `services/image_preprocess.py` – Simple preprocessing/cropping.
- `services/aadhaar_validator.py` – Aadhaar number validation/masking.
- `services/pan_validator.py` – PAN number validation.
- `services/risk_model.py` – Risk scoring (ML model or heuristic fallback).
- `ml/train_model.py` – Risk model training script.
- `requirements.txt` – Dependencies.

## Notes on performance
- DeepFace on CPU can be slow; first call downloads weights. For faster runs, use a GPU-enabled environment or switch to a lighter DeepFace model/detector (e.g., Facenet512 + opencv) and retune thresholds.
- ArcFace and RetinaFace model weights are cached after the first run.

## Deployment

This app is a Flask backend with TensorFlow, DeepFace, OpenCV, and Tesseract. Deploy it to a backend host, not a static-site host.

### Docker

```bash
docker build -t secure-kyc-portal .
docker run --rm -p 5000:5000 \
  -e KYC_SECRET_KEY="change-this-secret" \
  -e KYC_DEBUG=0 \
  secure-kyc-portal
```

Open `http://localhost:5000`.

### Render

1. Push this folder to GitHub.
2. In Render, create a new Blueprint or Web Service from the repo.
3. Render will use `render.yaml` and the `Dockerfile`.
4. Use at least the Standard plan; TensorFlow + DeepFace can exceed small free-tier memory limits.

### Environment Variables

Copy `.env.example` and set production values:

- `KYC_SECRET_KEY` - required, use a long random secret.
- `KYC_DEBUG=0` - hides debug OCR/model details in production.
- `KYC_LOGIN_USERNAME` - portal login username, defaults to `admin`.
- `KYC_LOGIN_PASSWORD` - portal login password, defaults to `admin123`; change this in production.
- `KYC_PUBLIC_URL` - public base URL used for OAuth callbacks, for example `https://secure-kyc-portal.onrender.com`.
- `KYC_GOOGLE_CLIENT_ID` / `KYC_GOOGLE_CLIENT_SECRET` - enables Google login.
- `KYC_GITHUB_CLIENT_ID` / `KYC_GITHUB_CLIENT_SECRET` - enables GitHub login.
- `KYC_DIGILOCKER_CLIENT_ID` / `KYC_DIGILOCKER_CLIENT_SECRET` - enables DigiLocker document KYC.
- `KYC_DIGILOCKER_AUTH_URL` / `KYC_DIGILOCKER_TOKEN_URL` - DigiLocker OAuth URLs assigned to your app.
- `KYC_DIGILOCKER_PROFILE_URL` - optional DigiLocker profile/eKYC endpoint used to fetch verified identity fields.
- `KYC_DIGILOCKER_SCOPE` - DigiLocker OAuth scopes, defaults to `openid profile`.
- `KYC_DB_PATH` - SQLite database location.
- `KYC_UPLOAD_FOLDER` - uploaded document location.
- `KYC_FACE_MODEL` - defaults to `ArcFace`.
- `KYC_FACE_DETECTOR` - defaults to `retinaface`.
- `KYC_FACE_APPROVE_SCORE` - minimum displayed similarity score for approval, defaults to `70`.
- `KYC_FACE_MANUAL_SCORE` - minimum displayed similarity score for manual review, defaults to `50`.

### OAuth Login

The app supports Google and GitHub login in addition to the local admin login. Create OAuth apps with these callback URLs:

- Local Google: `http://127.0.0.1:5000/oauth/google/callback`
- Local GitHub: `http://127.0.0.1:5000/oauth/github/callback`
- Render Google: `https://secure-kyc-portal.onrender.com/oauth/google/callback`
- Render GitHub: `https://secure-kyc-portal.onrender.com/oauth/github/callback`
- Local DigiLocker: `http://127.0.0.1:5000/digilocker/callback`
- Render DigiLocker: `https://secure-kyc-portal.onrender.com/digilocker/callback`

After you create the OAuth app, set the matching Client ID and Client Secret environment variables. The login buttons appear only for providers that have both values configured.

### DigiLocker KYC

The document step includes a DigiLocker option. With approved DigiLocker/API Setu credentials, the app redirects the user to DigiLocker, exchanges the callback code for an access token, fetches verified identity data from the configured profile/eKYC endpoint, and then continues to the existing live face capture step.

If the configured DigiLocker profile response includes a base64 face photo in fields such as `photo`, `picture`, `photo_base64`, `aadhaar_photo`, or `jpg_image`, the app uses it as the reference image for face matching. If no photo is returned, the app asks for a one-time Aadhaar image upload so live capture still has an ID face to compare against.

### Persistence Warning

SQLite files and uploaded documents may be lost on hosts with ephemeral disks. For real production, use managed Postgres/S3-style storage and encrypt sensitive files.

## ML Model & Training

- The repository now includes a small example training script at `ml/train_model.py` and a placeholder model artifact at `ml/risk_model.pkl`.

- Purpose: `services/risk_model.py` will attempt to load `ml/risk_model.pkl` at startup. If the file is missing the service falls back to a rule-based heuristic implementation (this is intentional and safe for development).

- The provided `ml/train_model.py` generates synthetic training data, trains a small RandomForest classifier, and saves the artifact to `ml/risk_model.pkl`. This placeholder model is intended for local testing and demonstration only.

### How to retrain a production model

1. Replace the synthetic data generator in `ml/train_model.py` with your labeled KYC dataset. The expected feature order used by `services/risk_model.py` is:

   - `face_pct` (0-100)
   - `name_pct` (0-100)
   - `verhoeff_flag` (0 or 1)
   - `blur_score` (numeric)

2. Train and save a scikit-learn compatible estimator with `joblib.dump()` to `ml/risk_model.pkl`.

3. Restart the Flask app; `services/risk_model.py` will automatically load the model if present.

### Quick commands (local)

```bash
# Install deps
pip install -r requirements.txt

# Train and save placeholder model (creates ml/risk_model.pkl)
python ml/train_model.py

# Run the app
python app.py
```

### Security & production notes

- Do NOT commit real production model artifacts containing sensitive training data. Use an artifacts store (S3, Artifactory, MLflow) and fetch the model during deploy.
- The example model here is synthetic and for local testing only. Replace with a properly validated, versioned model before using in production.
- Logging, model versioning, and monitoring should be added when moving to production (CI, model registry, A/B testing and rollback).
