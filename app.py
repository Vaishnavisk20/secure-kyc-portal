import os
import cv2
import base64
import numpy as np
import fitz  # PyMuPDF for PDF handling
from flask import Flask, request, session, redirect, jsonify

# --- IMPORT SERVICES ---
# Ensure you have services/ocr_service.py and services/face_service.py
from services.ocr_service import extract_aadhaar_text, extract_pan_text
from services.face_service import verify_face_match

app = Flask(__name__)
app.config["SECRET_KEY"] = "secure-kyc-key-999"
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB Max

# Upload Config
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

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
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
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
    
    input[type="text"], input[type="date"], input[type="file"] {
        width: 100%; padding: 12px; margin: 8px 0 20px 0;
        border: 2px solid #e2e8f0; border-radius: 10px; box-sizing: border-box; font-size: 1rem;
    }
    
    .btn {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
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
    .tab-btn.active { background: #667eea; color: white; }

    /* LOADING SPINNER */
    .loader-overlay {
        position: fixed; top: 0; left: 0; width: 100%; height: 100%;
        background: rgba(255, 255, 255, 0.9);
        display: none; /* Hidden by default */
        justify-content: center; align-items: center; flex-direction: column;
        z-index: 1000;
    }
    .loader {
        border: 8px solid #f3f3f3; border-top: 8px solid #667eea;
        border-radius: 50%; width: 60px; height: 60px;
        animation: spin 1s linear infinite; margin-bottom: 20px;
    }
    @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
</style>
"""

@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "GET":
        return f"""
        {MODERN_CSS}
        <div class="card">
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
    
    session["user"] = {
        "name": request.form.get("name").strip(),
        "dob": request.form.get("dob"),
        "aadhaar_last4": request.form.get("aadhaar_last4").strip(),
        "pan_number": request.form.get("pan_number").strip().upper() if request.form.get("pan_number") else None
    }
    return redirect("/upload")

@app.route("/upload", methods=["GET", "POST"])
def upload():
    if "user" not in session: return redirect("/")
    
    if request.method == "GET":
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
            <h2>📂 Upload Documents</h2>
            <p>Accepted: JPG, PNG, PDF</p>
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
    
    save_path_a = os.path.join(UPLOAD_FOLDER, f"aadhaar_{f_aadhaar.filename}")
    
    try:
        img_a, real_path_a = convert_pdf_to_image(f_aadhaar, save_path_a)
        
        # OCR
        ocr_aadhaar = extract_aadhaar_text(img_a)
        
        if not ocr_aadhaar["aadhaar_number"]:
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
        save_path_p = os.path.join(UPLOAD_FOLDER, f"pan_{f_pan.filename}")
        try:
            img_p, _ = convert_pdf_to_image(f_pan, save_path_p)
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
    if "doc_path_for_face" not in session: return redirect("/")
    
    return f"""
    {MODERN_CSS}
    
    <div id="loader" class="loader-overlay">
        <div class="loader"></div>
        <h3 style="color:#333;">Verifying Face...</h3>
        <p>Analyzing facial features. Please wait.</p>
    </div>

    <div class="card" style="max-width: 600px;">
        <h2>📸 User Verification</h2>
        <p>Choose how you want to verify your identity.</p>
        
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
                    <button type="submit" class="btn" style="background: #4a5568;">Verify Uploaded Photo</button>
                </form>
            </div>
        </div>

        <form id="face-form-cam" method="post" action="/process-face" style="display:none;">
            <input type="hidden" name="image_data" id="image-data">
            <input type="hidden" name="source_type" value="webcam">
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
                
                const context = canvas.getContext('2d');
                canvas.width = video.videoWidth;
                canvas.height = video.videoHeight;
                context.drawImage(video, 0, 0);
                
                const dataURL = canvas.toDataURL('image/jpeg', 0.8);
                document.getElementById('image-data').value = dataURL;

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
    if "doc_path_for_face" not in session: return redirect("/")

    img_live = None
    source_type = request.form.get("source_type")
    
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

            photo_path = os.path.join(UPLOAD_FOLDER, "temp_user_photo.jpg")
            f_photo.save(photo_path)
            img_live = cv2.imread(photo_path)

    except Exception as e:
        return f"Error processing image: {str(e)}", 400

    if img_live is None:
        return "Could not load image. Please try again.", 400

    # Load ID Card Image
    img_doc_path = session["doc_path_for_face"]
    img_doc = cv2.imread(img_doc_path)
    
    # --- CALL FACE VERIFICATION ---
    try:
        face_result = verify_face_match(img_doc, img_live)
    except Exception as face_error:
        return f"Face verification failed: {str(face_error)}", 500
    
    # Prepare Result Page
    is_approved = face_result["match"]
    status_header = "✅ KYC APPROVED" if is_approved else "⛔ KYC REJECTED"
    header_color = "#38a169" if is_approved else "#e53e3e"
    
    ocr_aadhaar = session.get("ocr_aadhaar", {})
    ocr_pan = session.get("ocr_pan", {})
    user = session.get("user", {})

    return f"""
    {MODERN_CSS}
    <div class="card" style="max-width:550px;">
        <h2 style="color:{header_color}">{status_header}</h2>
        <p>Verification Complete ({source_type.title()} Method)</p>
        
        <div class="status-box" style="background:#f7fafc; border:1px solid #e2e8f0;">
            <h3 style="margin-top:0;">1. Face Verification</h3>
            
            <p><strong>Status:</strong> {"MATCHED" if face_result['match'] else "MISMATCH"}</p>
            <p><strong>Similarity Score:</strong> {face_result['score']}%</p>
            <p style="font-size:0.85rem; color:#718096"><i>{face_result.get('error') or 'Identity Confirmed'}</i></p>
        </div>
        
        <div class="status-box" style="background:#f7fafc; border:1px solid #e2e8f0;">
            <h3 style="margin-top:0;">2. Document Details</h3>
             
            <p><strong>Name:</strong> {user.get('name')}</p>
            <p><strong>DOB:</strong> {user.get('dob')}</p>
            <p><strong>Aadhaar:</strong> {ocr_aadhaar.get('aadhaar_number', 'Not Detected')}</p>
            <p><strong>PAN:</strong> {ocr_pan.get('pan_number') if ocr_pan.get('pan_number') else 'Not Provided'}</p>
        </div>
        
        <br>
        <a href="/" class="btn" style="background:#2d3748;">Start New KYC</a>
    </div>
    """

if __name__ == "__main__":
    # Host='0.0.0.0' makes it accessible on network (e.g. from phone)
    app.run(debug=True, port=5000, host='0.0.0.0')