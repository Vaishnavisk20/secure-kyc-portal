# services/image_preprocess.py
import cv2
import numpy as np

def enhance_card_image(image):
    """
    1. Detects if image is a full A4 page (Portrait) -> Crops bottom 40%.
    2. Detects blur -> Sharpens if needed.
    """
    height, width, _ = image.shape
    
    # 1. SMART CROP (Fixes "Full Page" issue)
    # If height is significantly larger than width (Portrait mode A4 scan)
    if height > width * 1.4:
        # The card is usually at the bottom of the e-Aadhaar letter
        crop_start = int(height * 0.60)
        image = image[crop_start:height, 0:width]
        
    # 2. BLUR DETECTION & SHARPENING
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
    
    # If blur_score is low (blurry), but not too low (blank page)
    # We apply a sharpening kernel
    if 50 < blur_score < 200:
        kernel = np.array([[0, -1, 0], [-1, 5,-1], [0, -1, 0]])
        image = cv2.filter2D(image, -1, kernel)
        
    return image, blur_score