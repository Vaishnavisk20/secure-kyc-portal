import os
import cv2
import base64
import html
import json
import time
import secrets
import urllib.error
import urllib.parse
import urllib.request
import numpy as np
import fitz  # PyMuPDF for PDF handling
from flask import Flask, request, session, redirect, jsonify, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

# --- IMPORT SERVICES ---
# Ensure you have services/ocr_service.py and services/face_service.py
from services.ocr_service import extract_aadhaar_text, extract_pan_text
from services.face_service import verify_face_match
from services.db_service import create_kyc_record, create_user, find_user_by_email, init_db

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("KYC_SECRET_KEY", "secure-kyc-key-999")
app.config['MAX_CONTENT_LENGTH'] = int(os.getenv("KYC_MAX_UPLOAD_MB", "16")) * 1024 * 1024

UPLOAD_FOLDER = os.getenv("KYC_UPLOAD_FOLDER", "static/uploads")
DEBUG_KYC = os.getenv("KYC_DEBUG", "1") == "1"
LOGIN_USERNAME = os.getenv("KYC_LOGIN_USERNAME", "admin")
LOGIN_PASSWORD = os.getenv("KYC_LOGIN_PASSWORD", "admin123")
GOOGLE_CLIENT_ID = os.getenv("KYC_GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("KYC_GOOGLE_CLIENT_SECRET")
GITHUB_CLIENT_ID = os.getenv("KYC_GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("KYC_GITHUB_CLIENT_SECRET")
PUBLIC_URL = os.getenv("KYC_PUBLIC_URL")
DIGILOCKER_CLIENT_ID = os.getenv("KYC_DIGILOCKER_CLIENT_ID")
DIGILOCKER_CLIENT_SECRET = os.getenv("KYC_DIGILOCKER_CLIENT_SECRET")
DIGILOCKER_AUTH_URL = os.getenv("KYC_DIGILOCKER_AUTH_URL")
DIGILOCKER_TOKEN_URL = os.getenv("KYC_DIGILOCKER_TOKEN_URL")
DIGILOCKER_PROFILE_URL = os.getenv("KYC_DIGILOCKER_PROFILE_URL")
DIGILOCKER_SCOPE = os.getenv("KYC_DIGILOCKER_SCOPE", "openid profile")
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "pdf"}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
init_db()


def escape(value):
    return html.escape(str(value or ""))


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def allowed_image_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in {"jpg", "jpeg", "png"}


def upload_path(prefix, filename):
    safe_name = secure_filename(filename or "upload")
    return os.path.join(UPLOAD_FOLDER, f"{prefix}_{int(time.time() * 1000)}_{safe_name}")


def is_logged_in():
    return session.get("logged_in") is True


def require_login():
    if not is_logged_in():
        return redirect("/login")
    return None


OAUTH_PROVIDERS = {
    "google": {
        "label": "Google",
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://openidconnect.googleapis.com/v1/userinfo",
        "scope": "openid email profile",
    },
    "github": {
        "label": "GitHub",
        "client_id": GITHUB_CLIENT_ID,
        "client_secret": GITHUB_CLIENT_SECRET,
        "auth_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "userinfo_url": "https://api.github.com/user",
        "emails_url": "https://api.github.com/user/emails",
        "scope": "read:user user:email",
    },
}


def get_provider(provider):
    config = OAUTH_PROVIDERS.get(provider)
    if not config:
        return None
    return config


def provider_is_configured(provider):
    config = get_provider(provider)
    return bool(config and config.get("client_id") and config.get("client_secret"))


def callback_url(provider):
    path = url_for("oauth_callback", provider=provider)
    if PUBLIC_URL:
        return f"{PUBLIC_URL.rstrip('/')}{path}"
    return url_for("oauth_callback", provider=provider, _external=True)


def digilocker_callback_url():
    path = url_for("digilocker_callback")
    if PUBLIC_URL:
        return f"{PUBLIC_URL.rstrip('/')}{path}"
    return url_for("digilocker_callback", _external=True)


def digilocker_is_configured():
    return bool(DIGILOCKER_CLIENT_ID and DIGILOCKER_CLIENT_SECRET and DIGILOCKER_AUTH_URL and DIGILOCKER_TOKEN_URL)


def post_form_json(url, data, headers=None):
    body = urllib.parse.urlencode(data).encode("utf-8")
    request_obj = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            **(headers or {}),
        },
        method="POST",
    )
    with urllib.request.urlopen(request_obj, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def get_json(url, token):
    request_obj = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "secure-kyc-portal",
        },
    )
    with urllib.request.urlopen(request_obj, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def first_value(data, keys):
    for key in keys:
        value = data.get(key)
        if value:
            return str(value)
    return None


def save_base64_image(raw_value, prefix):
    if not raw_value:
        return None

    value = str(raw_value)
    extension = "jpg"
    if value.startswith("data:image/"):
        header, value = value.split(",", 1)
        extension = header.split("/")[1].split(";")[0] or "jpg"

    try:
        image_bytes = base64.b64decode(value)
    except Exception:
        return None

    save_path = upload_path(prefix, f"digilocker_photo.{extension}")
    with open(save_path, "wb") as file:
        file.write(image_bytes)

    if cv2.imread(save_path) is None:
        return None
    return save_path


def normalize_digilocker_profile(profile):
    aadhaar_number = first_value(profile, ["aadhaar_number", "aadhaar", "uid", "uid_number"])
    aadhaar_last4 = first_value(profile, ["aadhaar_last4", "uid_last4"])
    if aadhaar_number:
        aadhaar_last4 = aadhaar_number[-4:]
    masked_number = first_value(profile, ["masked_aadhaar", "masked_uid"])
    if not masked_number and aadhaar_last4:
        masked_number = f"XXXX XXXX {aadhaar_last4}"

    photo_value = first_value(profile, ["photo", "picture", "photo_base64", "aadhaar_photo", "jpg_image"])
    photo_path = save_base64_image(photo_value, "digilocker") if photo_value else None

    return {
        "name": first_value(profile, ["name", "full_name"]),
        "dob": first_value(profile, ["dob", "date_of_birth", "birthdate"]),
        "aadhaar_number": aadhaar_number or aadhaar_last4,
        "aadhaar_last4": aadhaar_last4,
        "masked_number": masked_number,
        "photo_path": photo_path,
        "raw_profile": profile,
    }


def github_primary_email(token):
    try:
        emails = get_json(OAUTH_PROVIDERS["github"]["emails_url"], token)
    except (urllib.error.URLError, json.JSONDecodeError):
        return None
    for email in emails:
        if email.get("primary") and email.get("verified"):
            return email.get("email")
    for email in emails:
        if email.get("verified"):
            return email.get("email")
    return None


def complete_login(provider, profile):
    session.clear()
    session["logged_in"] = True
    session["login_provider"] = provider
    session["login_user"] = profile.get("email") or profile.get("login") or profile.get("name") or provider
    session["login_name"] = profile.get("name") or profile.get("login") or ""
    return redirect("/")


def complete_local_login(user):
    session.clear()
    session["logged_in"] = True
    session["login_provider"] = "local"
    session["login_user"] = user["email"]
    session["login_name"] = user["name"]
    session["login_user_id"] = user["id"]
    return redirect("/")


def login_error(message):
    return redirect(f"/login?error_message={urllib.parse.quote(message)}")


def mask_identifier(value):
    if not value:
        return "Not Detected"
    return f"XXXX XXXX {str(value)[-4:]}"


def compact_debug_text(text, limit=700):
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return escape(text)
    return escape(text[:limit] + "...")


def stepper(active):
    steps = ["Details", "Documents", "Face", "Result"]
    items = []
    for index, label in enumerate(steps, start=1):
        state = "active" if index == active else "done" if index < active else ""
        items.append(f"<span class='step {state}'>{index}. {label}</span>")
    return f"<div class='stepper'>{''.join(items)}</div>"

# --- HELPER: CONVERT PDF TO IMAGE ---
def convert_pdf_to_image(file_storage, save_path):
    """
    If file is PDF, converts first page to Image.
    If file is Image, saves it directly.
    """
    filename = file_storage.filename.lower()
    
    # CASE 1: PDF FILE
    if filename.endswith('.pdf'):
        doc = fitz.open(stream=file_storage.read(), filetype="pdf")
        page = doc.load_page(0)  # Get first page
        pix = page.get_pixmap()  # Render to image
        
        img_data = np.frombuffer(pix.samples, dtype=np.uint8)
        img_np = img_data.reshape(pix.h, pix.w, pix.n)
        
        if pix.n == 3:
            img_np = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
        elif pix.n == 4: # RGBA
            img_np = cv2.cvtColor(img_np, cv2.COLOR_RGBA2BGR)
            
        final_path = save_path.replace(".pdf", ".jpg")
        cv2.imwrite(final_path, img_np)
        return img_np, final_path

    # CASE 2: NORMAL IMAGE
    else:
        file_storage.save(save_path)
        return cv2.imread(save_path), save_path

# --- CSS STYLES (Modern UI + Loader) ---
MODERN_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&display=swap');
    
    body {
        font-family: 'Inter', sans-serif;
        background: linear-gradient(135deg, #526a8f 0%, #6b587d 100%);
        min-height: 100vh;
        display: flex;
        align-items: center;
        justify-content: center;
        margin: 0;
        color: #333;
    }
    .card {
        background: rgba(255, 255, 255, 0.95);
        padding: 40px;
        border-radius: 20px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        width: 100%;
        max-width: 500px;
        text-align: center;
    }
    h2 { color: #2d3748; margin-bottom: 10px; font-weight: 700; }
    p { color: #718096; font-size: 0.95rem; margin-bottom: 25px; }
    
    input[type="text"], input[type="date"], input[type="file"], input[type="password"] {
        width: 100%; padding: 12px; margin: 8px 0 20px 0;
        border: 2px solid #e2e8f0; border-radius: 10px; box-sizing: border-box; font-size: 1rem;
    }
    
    .btn {
        background: linear-gradient(90deg, #486f99 0%, #6b587d 100%);
        color: white; padding: 14px 20px; border: none; border-radius: 10px;
        width: 100%; font-size: 1rem; font-weight: 600; cursor: pointer; margin-top: 10px;
    }
    .btn:hover { opacity: 0.9; }
    .btn:disabled { background: #cbd5e0; cursor: not-allowed; }
    
    .status-box { padding: 15px; border-radius: 10px; margin-top: 20px; text-align: left; }
    .webcam-container { margin: 20px 0; width: 100%; max-width: 320px; border-radius: 12px; overflow: hidden; display: inline-block; position: relative; background: #000; }
    
    video { width: 100%; height: auto; display: block; }

    .tab-container { display: flex; justify-content: center; margin-bottom: 20px; gap: 10px; }
    .tab-btn { background: #e2e8f0; color: #4a5568; padding: 10px 20px; border-radius: 20px; cursor: pointer; border: none; font-weight: 600; }
    .tab-btn.active { background: #486f99; color: white; }

    .stepper { display:flex; gap:8px; justify-content:center; flex-wrap:wrap; margin-bottom:22px; }
    .step { padding:7px 10px; border-radius:999px; background:#edf2f7; color:#4a5568; font-size:0.78rem; font-weight:700; }
    .step.done { background:#c6f6d5; color:#276749; }
    .step.active { background:#bee3f8; color:#2b6cb0; }
    .debug-box { background:#1a202c; color:#e2e8f0; border-radius:10px; padding:14px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size:0.78rem; overflow-wrap:anywhere; }
    .pill { display:inline-block; padding:5px 9px; border-radius:999px; font-size:0.78rem; font-weight:700; margin:2px; }
    .pill-ok { background:#c6f6d5; color:#276749; }
    .pill-warn { background:#fefcbf; color:#744210; }
    .pill-bad { background:#fed7d7; color:#9b2c2c; }
    .challenge { background:#ebf8ff; border:1px solid #bee3f8; color:#2b6cb0; padding:12px; border-radius:10px; font-weight:700; margin:14px 0; }
    .top-link { display:block; text-align:right; color:#4a5568; text-decoration:none; font-size:0.86rem; font-weight:700; margin-bottom:8px; }
    .error-message { background:#fed7d7; color:#9b2c2c; padding:10px 12px; border-radius:10px; font-weight:700; margin:0 0 18px 0; }
    .oauth-grid { display:grid; gap:10px; margin:18px 0 8px 0; }
    .oauth-btn { display:block; padding:12px 14px; border-radius:10px; border:1px solid #cbd5e0; color:#2d3748; text-decoration:none; font-weight:700; background:#fff; }
    .oauth-btn:hover { background:#f7fafc; }
    .divider { display:flex; align-items:center; gap:12px; color:#a0aec0; font-size:0.82rem; font-weight:700; margin:20px 0 14px 0; }
    .divider:before, .divider:after { content:""; flex:1; height:1px; background:#e2e8f0; }
    .auth-link { color:#486f99; text-decoration:none; font-weight:700; }
    .helper-text { margin:16px 0 0 0; color:#4a5568; }

    /* LOADING SPINNER */
    .loader-overlay {
        position: fixed; top: 0; left: 0; width: 100%; height: 100%;
        background: rgba(255, 255, 255, 0.9);
        display: none; /* Hidden by default */
        justify-content: center; align-items: center; flex-direction: column;
        z-index: 1000;
    }
    .loader {
        border: 8px solid #f3f3f3; border-top: 8px solid #486f99;
        border-radius: 50%; width: 60px; height: 60px;
        animation: spin 1s linear infinite; margin-bottom: 20px;
    }
    @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
</style>
"""

@app.route("/login", methods=["GET", "POST", "HEAD"])
def login():
    if request.method in {"GET", "HEAD"}:
        error = request.args.get("error") == "1"
        error_message = request.args.get("error_message")
        success_message = request.args.get("success_message")
        oauth_error = request.args.get("oauth_error")
        error_html = "<div class='error-message'>Invalid username or password.</div>" if error else ""
        if error_message:
            error_html = f"<div class='error-message'>{escape(error_message)}</div>"
        if success_message:
            error_html = f"<div class='status-box' style='background:#c6f6d5; color:#276749; border:1px solid #9ae6b4; font-weight:700;'>{escape(success_message)}</div>"
        if oauth_error:
            error_html = f"<div class='error-message'>{escape(oauth_error)}</div>"
        oauth_buttons = "<a class='oauth-btn' href='/oauth/google/start'>Continue with Google</a>"
        if provider_is_configured("github"):
            oauth_buttons += "<a class='oauth-btn' href='/oauth/github/start'>Continue with GitHub</a>"
        return f"""
        {MODERN_CSS}
        <div class="card">
            <h2>🔐 Secure KYC Login</h2>
            <p>Sign in to access the verification portal.</p>
            {error_html}
            <div class="oauth-grid">
                {oauth_buttons}
            </div>
            <div class="divider">OR</div>
            <form method="post">
                <label style="float:left; font-weight:600">Email</label>
                <input name="username" type="text" autocomplete="email" required>

                <label style="float:left; font-weight:600">Password</label>
                <input name="password" type="password" autocomplete="current-password" required>

                <button type="submit" class="btn">Login</button>
            </form>
            <p class="helper-text">New user? <a class="auth-link" href="/register">Create an account</a></p>
        </div>
        """

    username = (request.form.get("username") or "").strip().lower()
    password = request.form.get("password") or ""
    user = find_user_by_email(username)
    if user and check_password_hash(user["password_hash"], password):
        return complete_local_login(user)

    if secrets.compare_digest(username, LOGIN_USERNAME.lower()) and secrets.compare_digest(password, LOGIN_PASSWORD):
        session.clear()
        session["logged_in"] = True
        session["login_provider"] = "admin"
        session["login_user"] = username
        return redirect("/")
    return redirect("/login?error=1")


@app.route("/register", methods=["GET", "POST", "HEAD"])
def register():
    if request.method in {"GET", "HEAD"}:
        error_message = request.args.get("error_message")
        success = request.args.get("success") == "1"
        message_html = ""
        if error_message:
            message_html = f"<div class='error-message'>{escape(error_message)}</div>"
        if success:
            message_html = "<div class='status-box' style='background:#c6f6d5; color:#276749; border:1px solid #9ae6b4; font-weight:700;'>Account created. Please login.</div>"
        return f"""
        {MODERN_CSS}
        <div class="card">
            <h2>📝 Create Account</h2>
            <p>Register to use Secure KYC without Google Sign-In.</p>
            {message_html}
            <form method="post">
                <label style="float:left; font-weight:600">Full Name</label>
                <input name="name" type="text" autocomplete="name" required>

                <label style="float:left; font-weight:600">Email</label>
                <input name="email" type="text" autocomplete="email" required>

                <label style="float:left; font-weight:600">Password</label>
                <input name="password" type="password" autocomplete="new-password" minlength="8" required>

                <label style="float:left; font-weight:600">Confirm Password</label>
                <input name="confirm_password" type="password" autocomplete="new-password" minlength="8" required>

                <button type="submit" class="btn">Create Account</button>
            </form>
            <p class="helper-text">Already registered? <a class="auth-link" href="/login">Login</a></p>
        </div>
        """

    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""
    confirm_password = request.form.get("confirm_password") or ""

    if not name:
        return redirect(f"/register?error_message={urllib.parse.quote('Please enter your name.')}")
    if "@" not in email or "." not in email:
        return redirect(f"/register?error_message={urllib.parse.quote('Please enter a valid email address.')}")
    if len(password) < 8:
        return redirect(f"/register?error_message={urllib.parse.quote('Password must be at least 8 characters.')}")
    if password != confirm_password:
        return redirect(f"/register?error_message={urllib.parse.quote('Passwords do not match.')}")
    if find_user_by_email(email):
        return redirect(f"/register?error_message={urllib.parse.quote('An account already exists for this email. Please login.')}")

    password_hash = generate_password_hash(password)
    create_user(name, email, password_hash)
    return redirect("/login?success_message=Account%20created.%20Please%20login.")


@app.route("/oauth/<provider>/start")
def oauth_start(provider):
    config = get_provider(provider)
    if not config:
        return redirect("/login?oauth_error=Unsupported%20login%20provider.")
    if not provider_is_configured(provider):
        return redirect(f"/login?oauth_error={urllib.parse.quote(config['label'] + ' login is not configured yet.')}")

    state = secrets.token_urlsafe(24)
    session["oauth_state"] = state
    session["oauth_provider"] = provider
    params = {
        "client_id": config["client_id"],
        "redirect_uri": callback_url(provider),
        "response_type": "code",
        "scope": config["scope"],
        "state": state,
    }
    if provider == "google":
        params["prompt"] = "select_account"
    return redirect(f"{config['auth_url']}?{urllib.parse.urlencode(params)}")


@app.route("/oauth/<provider>/callback")
def oauth_callback(provider):
    config = get_provider(provider)
    expected_state = session.get("oauth_state")
    expected_provider = session.get("oauth_provider")
    received_state = request.args.get("state")
    code = request.args.get("code")
    if not config or expected_provider != provider or not expected_state or not secrets.compare_digest(expected_state, received_state or ""):
        return redirect("/login?oauth_error=Login%20session%20expired.%20Please%20try%20again.")
    if not code:
        return redirect("/login?oauth_error=Login%20was%20cancelled%20or%20failed.")

    try:
        token_response = post_form_json(config["token_url"], {
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "code": code,
            "redirect_uri": callback_url(provider),
            "grant_type": "authorization_code",
        })
        access_token = token_response.get("access_token")
        if not access_token:
            return redirect("/login?oauth_error=Could%20not%20get%20login%20token.")

        profile = get_json(config["userinfo_url"], access_token)
        if provider == "github" and not profile.get("email"):
            profile["email"] = github_primary_email(access_token)
        return complete_login(provider, profile)
    except (urllib.error.URLError, json.JSONDecodeError) as error:
        return redirect(f"/login?oauth_error={urllib.parse.quote('OAuth login failed: ' + str(error))}")


@app.route("/digilocker/start")
def digilocker_start():
    login_redirect = require_login()
    if login_redirect:
        return login_redirect
    if "user" not in session:
        return redirect("/")
    if not digilocker_is_configured():
        return redirect("/upload?digilocker_error=1")

    state = secrets.token_urlsafe(24)
    session["digilocker_state"] = state
    params = {
        "client_id": DIGILOCKER_CLIENT_ID,
        "redirect_uri": digilocker_callback_url(),
        "response_type": "code",
        "scope": DIGILOCKER_SCOPE,
        "state": state,
    }
    return redirect(f"{DIGILOCKER_AUTH_URL}?{urllib.parse.urlencode(params)}")


@app.route("/digilocker/callback")
def digilocker_callback():
    login_redirect = require_login()
    if login_redirect:
        return login_redirect

    expected_state = session.get("digilocker_state")
    received_state = request.args.get("state")
    code = request.args.get("code")
    if not expected_state or not secrets.compare_digest(expected_state, received_state or ""):
        return redirect("/upload?digilocker_error=session")
    if not code:
        return redirect("/upload?digilocker_error=cancelled")

    try:
        token_response = post_form_json(DIGILOCKER_TOKEN_URL, {
            "client_id": DIGILOCKER_CLIENT_ID,
            "client_secret": DIGILOCKER_CLIENT_SECRET,
            "code": code,
            "redirect_uri": digilocker_callback_url(),
            "grant_type": "authorization_code",
        })
        access_token = token_response.get("access_token")
        if not access_token:
            return redirect("/upload?digilocker_error=token")

        profile = {}
        if DIGILOCKER_PROFILE_URL:
            profile = get_json(DIGILOCKER_PROFILE_URL, access_token)
        normalized = normalize_digilocker_profile(profile)
        user = session.get("user", {})

        if normalized.get("aadhaar_last4") and normalized["aadhaar_last4"] != user.get("aadhaar_last4"):
            return redirect("/upload?digilocker_error=mismatch")

        session["ocr_aadhaar"] = {
            "status": "DIGILOCKER_VERIFIED",
            "aadhaar_number": normalized.get("aadhaar_number") or user.get("aadhaar_last4"),
            "masked_number": normalized.get("masked_number") or mask_identifier(user.get("aadhaar_last4")),
            "full_text": "Identity data fetched from DigiLocker.",
        }
        session["ocr_pan"] = {"status": "SKIPPED", "pan_number": None}
        session["digilocker_kyc"] = {
            "name": normalized.get("name"),
            "dob": normalized.get("dob"),
            "aadhaar_masked": session["ocr_aadhaar"]["masked_number"],
            "verified": True,
        }

        if normalized.get("photo_path"):
            session["doc_path_for_face"] = normalized["photo_path"]
            return redirect("/face-verify")

        return f"""
        {MODERN_CSS}
        <div class="card">
            {stepper(2)}
            <h2>DigiLocker Connected</h2>
            <p>Your identity data was fetched, but no face photo was returned by the configured DigiLocker profile endpoint.</p>
            <div class="status-box" style="background:#fefcbf; border:1px solid #faf089;">
                Upload an Aadhaar image once so the app has an ID face to compare with live capture.
            </div>
            <a href="/upload" class="btn" style="display:inline-block; text-decoration:none;">Upload ID Photo</a>
        </div>
        """
    except (urllib.error.URLError, json.JSONDecodeError) as error:
        return redirect(f"/upload?digilocker_error={urllib.parse.quote(str(error))}")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/", methods=["GET", "POST", "HEAD"])
def home():
    login_redirect = require_login()
    if login_redirect:
        return login_redirect

    if request.method in {"GET", "HEAD"}:
        return f"""
        {MODERN_CSS}
        <div class="card">
            <a class="top-link" href="/logout">Logout</a>
            {stepper(1)}
            <h2>🔐 Secure KYC Portal</h2>
            <p>Identity Verification System</p>
            <form method="post">
                <label style="float:left; font-weight:600">Full Name</label>
                <input name="name" type="text" placeholder="e.g. Rahul Sharma" required>
                
                <label style="float:left; font-weight:600">Date of Birth</label>
                <input name="dob" type="date" required>

                <label style="float:left; font-weight:600">Aadhaar (Last 4 Digits)</label>
                <input name="aadhaar_last4" type="text" maxlength="4" placeholder="XXXX" required>
                
                <label style="float:left; font-weight:600">PAN Number <small>(Optional)</small></label>
                <input name="pan_number" type="text" placeholder="ABCDE1234F">
                
                <button type="submit" class="btn">Next Step ➜</button>
            </form>
        </div>
        """

    name = (request.form.get("name") or "").strip()
    dob = request.form.get("dob") or ""
    aadhaar_last4 = (request.form.get("aadhaar_last4") or "").strip()
    pan_number = (request.form.get("pan_number") or "").strip().upper() or None

    if not aadhaar_last4.isdigit() or len(aadhaar_last4) != 4:
        return f"{MODERN_CSS}<div class='card'><h2>Invalid Aadhaar Last 4</h2><p>Please enter exactly 4 digits.</p><a href='/' class='btn' style='display:inline-block; text-decoration:none;'>Try Again</a></div>", 400

    session["user"] = {
        "name": name,
        "dob": dob,
        "aadhaar_last4": aadhaar_last4,
        "pan_number": pan_number
    }
    return redirect("/upload")

@app.route("/upload", methods=["GET", "POST"])
def upload():
    login_redirect = require_login()
    if login_redirect:
        return login_redirect
    if "user" not in session: return redirect("/")
    
    if request.method == "GET":
        digilocker_error = request.args.get("digilocker_error")
        digilocker_error_html = ""
        if digilocker_error:
            messages = {
                "1": "DigiLocker is not configured yet. Add client ID, client secret, auth URL, and token URL.",
                "session": "DigiLocker session expired. Please try again.",
                "cancelled": "DigiLocker authorization was cancelled.",
                "token": "DigiLocker did not return an access token.",
                "mismatch": "DigiLocker Aadhaar details do not match the last 4 digits you entered.",
            }
            message = messages.get(digilocker_error, f"DigiLocker failed: {digilocker_error}")
            digilocker_error_html = f"<div class='error-message'>{escape(message)}</div>"
        return f"""
        {MODERN_CSS}
        
        <div id="loader" class="loader-overlay">
            <div class="loader"></div>
            <h3 style="color:#333;">Processing Documents...</h3>
            <p>Our AI is reading your ID. This takes about 5-8 seconds.</p>
        </div>

        <script>
            function showLoader() {{
                document.getElementById('loader').style.display = 'flex';
                document.getElementById('submitBtn').disabled = true;
                document.getElementById('submitBtn').innerText = "Processing...";
            }}
        </script>

        <div class="card">
            <a class="top-link" href="/logout">Logout</a>
            {stepper(2)}
            <h2>📂 Upload Documents</h2>
            <p>Use DigiLocker for official KYC, or upload documents manually.</p>
            {digilocker_error_html}
            <a href="/digilocker/start" class="oauth-btn" style="margin-bottom:16px;">Fetch KYC from DigiLocker</a>
            <div class="divider">OR UPLOAD</div>
            <form method="post" enctype="multipart/form-data" onsubmit="showLoader()">
                <label style="float:left; font-weight:600">Aadhaar Card (Front)</label>
                <input type="file" name="aadhaar" accept="image/*,application/pdf" required>
                
                <label style="float:left; font-weight:600">PAN Card <small>(Optional)</small></label>
                <input type="file" name="pan" accept="image/*,application/pdf">
                
                <button type="submit" class="btn" id="submitBtn">Verify Docs ➜</button>
            </form>
        </div>
        """

    user = session["user"]
    errors = []
    
    # 1. PROCESS AADHAAR
    f_aadhaar = request.files.get("aadhaar")
    if not f_aadhaar: return "Missing Aadhaar", 400
    if not allowed_file(f_aadhaar.filename):
        return "Unsupported Aadhaar file type. Upload JPG, PNG, or PDF.", 400
    
    save_path_a = upload_path("aadhaar", f_aadhaar.filename)
    
    try:
        img_a, real_path_a = convert_pdf_to_image(f_aadhaar, save_path_a)
        if img_a is None:
            errors.append("❌ Could not read Aadhaar image.")
        elif img_a.shape[0] < 80 or img_a.shape[1] < 80:
            errors.append("❌ Aadhaar image is too small or unreadable.")
        
        # OCR
        ocr_aadhaar = extract_aadhaar_text(img_a) if img_a is not None else {}
        
        if not ocr_aadhaar.get("aadhaar_number"):
            errors.append("❌ Could not read Aadhaar Number.")
        elif ocr_aadhaar["aadhaar_number"][-4:] != user["aadhaar_last4"]:
            errors.append(f"❌ Aadhaar Mismatch: Found ...{ocr_aadhaar['aadhaar_number'][-4:]}")
            
        session["doc_path_for_face"] = real_path_a

    except Exception as e:
        errors.append(f"❌ Error processing Aadhaar: {str(e)}")
        ocr_aadhaar = {}

    # 2. PROCESS PAN
    f_pan = request.files.get("pan")
    ocr_pan = {"status": "SKIPPED", "pan_number": None} 
    
    if f_pan and f_pan.filename != '':
        if not allowed_file(f_pan.filename):
            errors.append("❌ Unsupported PAN file type. Upload JPG, PNG, or PDF.")
            save_path_p = None
        else:
            save_path_p = upload_path("pan", f_pan.filename)
        try:
            if save_path_p:
                img_p, _ = convert_pdf_to_image(f_pan, save_path_p)
                if img_p is None:
                    errors.append("❌ Could not read PAN image.")
                else:
                    ocr_pan = extract_pan_text(img_p)
                
                if user["pan_number"]:
                     if not ocr_pan["pan_number"]:
                         errors.append("❌ Uploaded PAN but could not read number.")
                     elif ocr_pan["pan_number"] != user["pan_number"]:
                         errors.append(f"❌ PAN Mismatch: Found {ocr_pan['pan_number']}")
        except Exception as e:
            errors.append(f"❌ Error processing PAN: {str(e)}")

    if errors:
        error_html = "".join([f"<p style='color:red; margin:5px 0;'>{e}</p>" for e in errors])
        return f"""
        {MODERN_CSS}
        <div class="card">
            <h2 style="color:#e53e3e">Verification Failed</h2>
            <div class="status-box" style="background:#f8d7da; border:1px solid #f5c6cb;">
                {error_html}
            </div>
            <a href='/upload' class='btn' style='background:#718096; display:inline-block; text-decoration:none;'>Try Again</a>
        </div>
        """

    session["ocr_aadhaar"] = ocr_aadhaar
    session["ocr_pan"] = ocr_pan
    
    return redirect("/face-verify")

@app.route("/face-verify", methods=["GET"])
def face_verify_page():
    login_redirect = require_login()
    if login_redirect:
        return login_redirect
    if "doc_path_for_face" not in session: return redirect("/")
    challenges = [
        "Look straight and blink once before capturing.",
        "Turn your head slightly left, then face the camera.",
        "Raise your chin slightly, then face the camera.",
    ]
    challenge = challenges[int(time.time()) % len(challenges)]
    session["liveness_challenge"] = challenge
    
    return f"""
    {MODERN_CSS}
    
    <div id="loader" class="loader-overlay">
        <div class="loader"></div>
        <h3 style="color:#333;">Verifying Face...</h3>
        <p>Analyzing facial features. Please wait.</p>
    </div>

    <div class="card" style="max-width: 600px;">
        <a class="top-link" href="/logout">Logout</a>
        {stepper(3)}
        <h2>📸 User Verification</h2>
        <p>Choose how you want to verify your identity.</p>
        <div class="challenge">Liveness prompt: {escape(challenge)}</div>
        
        <div class="tab-container">
            <button class="tab-btn active" onclick="switchTab('camera')" id="btn-camera">Use Camera</button>
            <button class="tab-btn" onclick="switchTab('upload')" id="btn-upload">Upload Photo</button>
        </div>
        
        <div id="section-camera">
            <div class="webcam-container">
                <video id="video" autoplay playsinline></video>
                <canvas id="canvas" style="display:none;"></canvas>
            </div>
            <p id="status" style="font-weight:bold; color:#2b6cb0;">Waiting for camera...</p>
            <button id="capture-btn" class="btn" onclick="captureAndVerify()">Verify with Camera</button>
        </div>

        <div id="section-upload" style="display:none;">
            <div style="border: 2px dashed #cbd5e0; padding: 20px; border-radius: 10px; margin: 20px 0;">
                <form id="face-form-upload" method="post" action="/process-face" enctype="multipart/form-data" onsubmit="showLoader()">
                    <label style="float:none;">Upload Your Selfie/Photo</label>
                    <input type="file" name="user_photo" accept="image/*" required>
                    <input type="hidden" name="source_type" value="upload">
                    <input type="hidden" name="liveness_ack" value="yes">
                    <p style="margin:0 0 12px 0; color:#4a5568;">Use a recent, front-facing photo after doing the liveness prompt.</p>
                    <button type="submit" class="btn" style="background: #4a5568;">Verify Uploaded Photo</button>
                </form>
            </div>
        </div>

        <form id="face-form-cam" method="post" action="/process-face" style="display:none;">
            <input type="hidden" name="image_data" id="image-data">
            <input type="hidden" name="source_type" value="webcam">
            <input type="hidden" name="liveness_ack" id="liveness-ack" value="no">
        </form>

        <script>
            // --- GLOBAL VARIABLES ---
            let video = document.getElementById('video');
            let canvas = document.getElementById('canvas');
            let stream = null;

            // --- TAB LOGIC ---
            function switchTab(tab) {{
                if(tab === 'camera') {{
                    document.getElementById('section-camera').style.display = 'block';
                    document.getElementById('section-upload').style.display = 'none';
                    document.getElementById('btn-camera').classList.add('active');
                    document.getElementById('btn-upload').classList.remove('active');
                    startCamera(); // Try starting camera again
                }} else {{
                    document.getElementById('section-camera').style.display = 'none';
                    document.getElementById('section-upload').style.display = 'block';
                    document.getElementById('btn-camera').classList.remove('active');
                    document.getElementById('btn-upload').classList.add('active');
                    stopCamera(); // Stop camera to save battery
                }}
            }}

            // --- CAMERA LOGIC ---
            async function startCamera() {{
                const statusText = document.getElementById('status');
                const captureBtn = document.getElementById('capture-btn');
                
                statusText.innerText = "Requesting permissions...";
                statusText.style.color = "#2b6cb0";

                try {{
                    // 'facingMode: user' uses the front camera on phones
                    stream = await navigator.mediaDevices.getUserMedia({{ 
                        video: {{ facingMode: 'user', width: {{ ideal: 640 }}, height: {{ ideal: 480 }} }},
                        audio: false 
                    }});
                    
                    video.srcObject = stream;
                    statusText.innerText = "Camera Active. Stay still.";
                    statusText.style.color = "green";
                    captureBtn.disabled = false;
                }} catch (err) {{
                    console.error("Camera Error:", err);
                    statusText.innerText = "❌ Camera Error: " + err.message + ". (Use Upload option)";
                    statusText.style.color = "red";
                    captureBtn.disabled = true;
                    
                    // Alert for Secure Context issue
                    if (window.location.hostname !== 'localhost' && window.location.protocol !== 'https:') {{
                        alert("⚠️ CAMERA BLOCKED: Browsers block cameras on unsecured (http) connections.\\n\\nPlease use the 'Upload Photo' tab instead.");
                    }}
                }}
            }}

            function stopCamera() {{
                if (stream) {{
                    stream.getTracks().forEach(track => track.stop());
                    stream = null;
                }}
            }}

            function captureAndVerify() {{
                if (!stream) return;
                if (!confirm("Did you complete the liveness prompt shown on the page?")) return;
                
                const context = canvas.getContext('2d');
                canvas.width = video.videoWidth;
                canvas.height = video.videoHeight;
                context.drawImage(video, 0, 0);
                
                const dataURL = canvas.toDataURL('image/jpeg', 0.8);
                document.getElementById('image-data').value = dataURL;
                document.getElementById('liveness-ack').value = "yes";

                // Show Loader
                document.getElementById('loader').style.display = 'flex';
                
                // Submit Form
                document.getElementById('face-form-cam').submit();
            }}
            
            function showLoader() {{
                document.getElementById('loader').style.display = 'flex';
            }}

            // Auto-start camera on load
            window.onload = startCamera;
        </script>
    </div>
    """

@app.route("/process-face", methods=["POST"])
def process_face():
    login_redirect = require_login()
    if login_redirect:
        return login_redirect
    if "doc_path_for_face" not in session: return redirect("/")

    img_live = None
    source_type = request.form.get("source_type")
    liveness_ack = request.form.get("liveness_ack") == "yes"
    saved_photo_path = None

    if not liveness_ack:
        return "Liveness prompt was not completed. Please try again.", 400
    
    # --- HANDLE IMAGE SOURCE ---
    try:
        if source_type == "webcam":
            data_url = request.form.get("image_data")
            if not data_url: return "No image captured", 400
            
            encoded_data = data_url.split(',')[1]
            nparr = np.frombuffer(base64.b64decode(encoded_data), np.uint8)
            img_live = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        elif source_type == "upload":
            f_photo = request.files.get("user_photo")
            if not f_photo: return "No file uploaded", 400
            if not allowed_image_file(f_photo.filename):
                return "Unsupported photo file type. Upload JPG or PNG.", 400

            saved_photo_path = upload_path("selfie", f_photo.filename)
            f_photo.save(saved_photo_path)
            img_live = cv2.imread(saved_photo_path)

    except Exception as e:
        return f"Error processing image: {str(e)}", 400

    if img_live is None:
        return "Could not load image. Please try again.", 400
    if img_live.shape[0] < 80 or img_live.shape[1] < 80:
        return "Photo is too small or unreadable. Please upload a clearer selfie.", 400

    # Load ID Card Image
    img_doc_path = session["doc_path_for_face"]
    img_doc = cv2.imread(img_doc_path)
    if img_doc is None:
        return "Could not load saved document image. Please restart the KYC flow.", 400
    
    # --- CALL FACE VERIFICATION ---
    try:
        face_result = verify_face_match(img_doc, img_live)
    except Exception as face_error:
        return f"Face verification failed: {str(face_error)}", 500
    finally:
        if saved_photo_path and os.path.exists(saved_photo_path):
            os.remove(saved_photo_path)
    
    # Prepare Result Page
    decision = face_result.get("decision", "REJECTED")
    is_approved = decision == "APPROVED"
    is_manual = decision == "MANUAL_REVIEW"
    status_header = "✅ KYC APPROVED" if is_approved else "⚠️ MANUAL REVIEW" if is_manual else "⛔ KYC REJECTED"
    header_color = "#38a169" if is_approved else "#d69e2e" if is_manual else "#e53e3e"
    face_pill = "pill-ok" if is_approved else "pill-warn" if is_manual else "pill-bad"
    
    ocr_aadhaar = session.get("ocr_aadhaar", {})
    ocr_pan = session.get("ocr_pan", {})
    user = session.get("user", {})
    record_id = create_kyc_record(
        user=user,
        ocr_aadhaar=ocr_aadhaar,
        ocr_pan=ocr_pan,
        face_result=face_result,
        document_path=img_doc_path,
        source_type=source_type,
        liveness_completed=liveness_ack,
    )
    debug_html = ""
    if DEBUG_KYC:
        debug_html = f"""
        <div class="status-box">
            <h3 style="margin-top:0;">Debug Details</h3>
            <div class="debug-box">
                Database record ID: {escape(record_id)}<br>
                Decision: {escape(decision)}<br>
                Face distance: {escape(face_result.get('distance'))}<br>
                Similarity score: {escape(face_result.get('score'))}%<br>
                Model: {escape(face_result.get('model'))}<br>
                Detector: {escape(face_result.get('detector'))}<br>
                Candidate: {escape(face_result.get('candidate'))}<br>
                Orientation: {escape(face_result.get('orientation'))}<br>
                OCR sample: {compact_debug_text(ocr_aadhaar.get('full_text'))}
            </div>
        </div>
        """

    return f"""
    {MODERN_CSS}
    <div class="card" style="max-width:550px;">
        <a class="top-link" href="/logout">Logout</a>
        {stepper(4)}
        <h2 style="color:{header_color}">{status_header}</h2>
        <p>Verification Complete ({escape(source_type or 'photo').title()} Method)</p>
        <p style="color:#4a5568; margin-bottom:12px;">Saved to database as record #{record_id}</p>
        
        <div class="status-box" style="background:#f7fafc; border:1px solid #e2e8f0;">
            <h3 style="margin-top:0;">1. Face Verification</h3>
            
            <p><strong>Status:</strong> <span class="pill {face_pill}">{escape(decision.replace('_', ' '))}</span></p>
            <p><strong>Similarity Score:</strong> {face_result['score']}%</p>
            <p><strong>Liveness:</strong> <span class="pill pill-ok">Prompt Completed</span></p>
            <p style="font-size:0.85rem; color:#718096"><i>{face_result.get('error') or 'Identity Confirmed'}</i></p>
        </div>
        
        <div class="status-box" style="background:#f7fafc; border:1px solid #e2e8f0;">
            <h3 style="margin-top:0;">2. Document Details</h3>
             
            <p><strong>Name:</strong> {user.get('name')}</p>
            <p><strong>DOB:</strong> {user.get('dob')}</p>
            <p><strong>Aadhaar:</strong> {mask_identifier(ocr_aadhaar.get('aadhaar_number'))}</p>
            <p><strong>PAN:</strong> {mask_identifier(ocr_pan.get('pan_number')) if ocr_pan.get('pan_number') else 'Not Provided'}</p>
        </div>

        {debug_html}
        
        <br>
        <a href="/" class="btn" style="background:#2d3748;">Start New KYC</a>
    </div>
    """

if __name__ == "__main__":
    # Host='0.0.0.0' makes it accessible on network (e.g. from phone)
    app.run(debug=True, port=5000, host='0.0.0.0')
