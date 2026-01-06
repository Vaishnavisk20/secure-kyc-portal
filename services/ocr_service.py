import requests
import re
import cv2
import json

# ------------------------------------------
# YOUR OCR.SPACE API KEY
API_KEY = 'K85191139988957'
# ------------------------------------------

def extract_text_via_api(image):
    """
    Helper function: Sends the image to OCR.Space Cloud API.
    """
    try:
        # 1. Convert OpenCV Image (numpy array) to Bytes
        # We must encode it as .jpg to send over the internet
        _, img_encoded = cv2.imencode('.jpg', image)
        file_bytes = img_encoded.tobytes()

        # 2. Prepare the Data
        payload = {
            'apikey': API_KEY,
            'language': 'eng',
            'isOverlayRequired': False,
            'scale': True,       # Helps with low resolution images
            'OCREngine': 2       # Engine 2 is BEST for Numbers & ID Cards
        }
        
        files = {
            'file': ('image.jpg', file_bytes, 'image/jpeg')
        }

        # 3. Send Request to Cloud
        print("--- ☁️ Sending Image to OCR.Space API... ---")
        response = requests.post('https://api.ocr.space/parse/image', files=files, data=payload)
        
        # 4. Parse Response
        result = response.json()
        
        # Check for API Errors
        if result.get('IsErroredOnProcessing'):
            error_msg = result.get('ErrorMessage')
            print(f"❌ API Error: {error_msg}")
            return ""
            
        # Extract Text
        parsed_results = result.get('ParsedResults', [])
        if parsed_results:
            text = parsed_results[0].get('ParsedText', "")
            # Merge lines into one single string for easier searching
            clean_text = text.replace('\r\n', ' ').replace('\n', ' ')
            print(f"✅ Cloud Response: {clean_text}") # Debug log
            return clean_text
            
        return ""

    except Exception as e:
        print(f"❌ Connection Error: {e}")
        return ""

def extract_aadhaar_text(image):
    """
    Uses Cloud API to find 12-digit Aadhaar number.
    """
    # 1. Get Text from Cloud
    full_text = extract_text_via_api(image)
    
    if not full_text:
        return {"aadhaar_number": None, "full_text": ""}

    # 2. Clean Text (Remove spaces/dashes)
    clean_text = full_text.replace(" ", "").replace("-", "")

    # 3. Look for 12 Digits
    # Since the Cloud API is accurate, we just grab all 12-digit sequences.
    matches = re.findall(r'\d{12}', clean_text)
    
    if matches:
        # We select the LAST match found. 
        # Why? On Aadhaar cards, the main number is at the bottom.
        # The top numbers might be Enrollment IDs or Phone numbers.
        return {"aadhaar_number": matches[-1], "full_text": full_text}

    return {"aadhaar_number": None, "full_text": full_text}

def extract_pan_text(image):
    """
    Uses Cloud API to find PAN Number.
    """
    # 1. Get Text from Cloud
    full_text = extract_text_via_api(image)
    
    if not full_text:
        return {"pan_number": None}
    
    # 2. Search word by word
    words = full_text.split()
    for word in words:
        word = word.strip().upper()
        # Keep only Letters and Numbers
        word = re.sub(r'[^A-Z0-9]', '', word)
        
        # Check if it matches PAN Pattern (5 Letters, 4 Digits, 1 Letter)
        if len(word) == 10:
            if re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]$', word):
                return {"pan_number": word}
    
    return {"pan_number": None}