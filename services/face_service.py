from deepface import DeepFace
import cv2
import numpy as np
import os

def verify_face_match(id_card_image, selfie_image):
    """
    Verifies if the ID Card photo matches the Selfie using DeepFace.
    """
    temp_id_path = "temp_id_card.jpg"
    temp_selfie_path = "temp_selfie.jpg"

    try:
        # 1. Save images to disk temporarily
        # DeepFace works much better with file paths than numpy arrays
        cv2.imwrite(temp_id_path, id_card_image)
        cv2.imwrite(temp_selfie_path, selfie_image)

        print("--- 🧠 Running DeepFace AI Analysis... ---")
        
        # 2. Run Verification
        # FIX: We pass the paths as the first two arguments directly (Positional Arguments)
        # This prevents the "unexpected keyword argument" error.
        result = DeepFace.verify(
            temp_id_path,           # First image (ID)
            temp_selfie_path,       # Second image (Selfie)
            model_name = "VGG-Face",
            detector_backend = "opencv", 
            distance_metric = "cosine",
            enforce_detection = False 
        )
        
        # 3. Cleanup temp files
        if os.path.exists(temp_id_path): os.remove(temp_id_path)
        if os.path.exists(temp_selfie_path): os.remove(temp_selfie_path)

        # 4. Process Results
        distance = result['distance']
        is_match = result['verified']
        
        # Calculate a simple accuracy score (0-100%)
        # Cosine distance is usually between 0 (exact) and 1 (diff).
        # We invert it to get "Similarity".
        accuracy_score = round((1 - distance) * 100, 2)

        print(f"✅ Face Result: Match={is_match}, Dist={distance}, Score={accuracy_score}%")

        return {
            "match": is_match,
            "score": accuracy_score,
            "error": None
        }

    except Exception as e:
        print(f"❌ DeepFace Error: {e}")
        # Cleanup in case of error
        if os.path.exists(temp_id_path): os.remove(temp_id_path)
        if os.path.exists(temp_selfie_path): os.remove(temp_selfie_path)
        
        return {
            "match": False, 
            "score": 0, 
            "error": f"Face check failed: {str(e)}"
        }