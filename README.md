# Aadhaar & PAN KYC  (Flask)

An end-to-end KYC flow supporting account login, Aadhaar/PAN document OCR, webcam liveness, face matching, and database-backed KYC decisions.

## What it does
- Supports Google login, local email/password registration, and admin fallback login.
- Collects Name, DOB, Aadhaar last 4, and optional PAN.
- Aadhaar/PAN upload -> local Tesseract OCR -> document-number matching.
- Optional DigiLocker OAuth handoff when official credentials and endpoints are configured.
- Live webcam capture -> OpenCV liveness checks -> DeepFace face match against the ID photo.
- Stores completed KYC results in Supabase/Postgres when configured, with SQLite as the local fallback.

## Current thresholds & rules
- Aadhaar last4: if provided and mismatched → reject; if provided but not detected → reject.
- PAN number: if provided and mismatched → reject; if provided but not detected → reject.
- Face: similarity score >= 70 → approve; >= 50 → manual review; below 50 → reject.
- Webcam liveness: requires multiple camera frames, face detection, image sharpness, and small real motion.
- Uploaded selfie/photo: can still be checked, but it cannot receive automatic approval without live liveness.

## Tech stack
- Flask (API + inline UI)
- Tesseract OCR via `pytesseract`
- OpenCV for image processing and liveness checks
- DeepFace (ArcFace model + RetinaFace detector) for face matching
- NumPy/TensorFlow/Keras backend via DeepFace
- Supabase/Postgres or local SQLite for users and KYC records

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
   - Page 3: Capture live selfie for liveness + face verification.
   - Results: View KYC decision.

## Environment notes
- Model weights (DeepFace backends) download on first use; allow network on first run.
- To quiet TensorFlow logs, set `TF_CPP_MIN_LOG_LEVEL=2`.

## File map
- `app.py` – Multi-page routes, inline UI, decision logic.
- `services/face_service.py` – DeepFace verification with ArcFace, RetinaFace, orientation handling, and ID face crops.
- `services/liveness_service.py` – OpenCV webcam liveness checks across multiple frames.
- `services/ocr_service.py` – OCR + document heuristics (Aadhaar/PAN status, DOB, numbers).
- `services/db_service.py` – Supabase/Postgres or SQLite tables for users and KYC records.
- `scripts/kyc_smoke_test.py` – Local OCR/face verification smoke test helper.
- `scripts/list_kyc_records.py` – Prints recent KYC records from the configured database.
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

### Supabase Database

The app uses local SQLite by default at `data/kyc_records.db`. To use Supabase instead, set a Supabase Postgres connection string in either `DATABASE_URL` or `SUPABASE_DB_URL`.

Use the Supabase dashboard's Postgres connection string, usually in this shape:

```bash
DATABASE_URL="postgresql://postgres:[YOUR-PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres?sslmode=require"
```

Then reinstall dependencies and run the app:

```bash
pip install -r requirements.txt
python app.py
```

On startup, the app creates the `users` and `kyc_records` tables in Supabase if they do not exist.

To upload Aadhaar, PAN, and selfie files to Supabase Storage as well, create a private bucket named `kyc-uploads` in Supabase Storage and set:

```bash
SUPABASE_URL="https://apmrjwvyegqpvzsohojm.supabase.co"
SUPABASE_SERVICE_ROLE_KEY="[YOUR-SERVICE-ROLE-KEY]"
SUPABASE_STORAGE_BUCKET="kyc-uploads"
```

KYC records will include `aadhaar_document_path`, `aadhaar_storage_path`, `pan_document_path`, `pan_storage_path`, `selfie_path`, `selfie_storage_path`, and `upload_metadata`.

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
- `DATABASE_URL` - Supabase/Postgres connection URL; when set, this is used instead of SQLite.
- `SUPABASE_DB_URL` - alternative Supabase/Postgres connection URL name.
- `SUPABASE_URL` - Supabase project URL, used for Storage uploads.
- `SUPABASE_SERVICE_ROLE_KEY` - Supabase service role key, used server-side for private Storage uploads.
- `SUPABASE_STORAGE_BUCKET` - Supabase Storage bucket name, defaults to `kyc-uploads`.
- `KYC_DB_PATH` - SQLite database location, only used when no Postgres URL is configured.
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

SQLite files and uploaded documents may be lost on hosts with ephemeral disks. For real production, use Supabase/Postgres plus S3-style storage and encrypt sensitive files.

### Quick commands (local)

```bash
# Install deps
pip install -r requirements.txt

# Run the app
python app.py
```

### Security & production notes

- Do not commit real user uploads, Aadhaar/PAN images, SQLite production data, OAuth secrets, or Google/DigiLocker client secrets.
- For production, move from local SQLite/uploads to managed database and object storage with encryption.
- Add audit logging, admin review screens, and stricter liveness/anti-spoofing before using this for real onboarding.
