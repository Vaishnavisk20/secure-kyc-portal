from deepface import DeepFace
import cv2
import numpy as np
import os
import tempfile

MODEL_NAME = os.getenv("KYC_FACE_MODEL", "ArcFace")
DETECTOR_BACKEND = os.getenv("KYC_FACE_DETECTOR", "retinaface")
DISTANCE_METRIC = os.getenv("KYC_FACE_METRIC", "cosine")
APPROVE_THRESHOLD = float(os.getenv("KYC_FACE_APPROVE_THRESHOLD", "0.75"))
MANUAL_THRESHOLD = float(os.getenv("KYC_FACE_MANUAL_THRESHOLD", "0.90"))


def image_orientations(image):
    return {
        "original": image,
        "rotate_90_clockwise": cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE),
        "rotate_90_counterclockwise": cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE),
        "rotate_180": cv2.rotate(image, cv2.ROTATE_180),
    }


def save_face_crops(image_path, temp_dir, prefix):
    crop_paths = []
    try:
        faces = DeepFace.extract_faces(
            img_path=image_path,
            detector_backend=DETECTOR_BACKEND,
            enforce_detection=False,
            align=True,
        )
    except Exception as exc:
        print(f"⚠️ Face crop skipped for {prefix}: {exc}")
        return crop_paths

    for index, face_obj in enumerate(faces):
        face = face_obj.get("face")
        if face is None:
            continue

        face_img = np.asarray(face)
        if face_img.dtype != np.uint8:
            face_img = np.clip(face_img * 255, 0, 255).astype(np.uint8)

        if face_img.ndim == 3 and face_img.shape[2] == 3:
            face_img = cv2.cvtColor(face_img, cv2.COLOR_RGB2BGR)

        crop_path = os.path.join(temp_dir, f"{prefix}_face_{index}.jpg")
        cv2.imwrite(crop_path, face_img)
        crop_paths.append(crop_path)

    return crop_paths

def verify_face_match(id_card_image, selfie_image):
    """
    Verifies if the ID Card photo matches the Selfie using DeepFace.
    """
    temp_paths = []

    try:
        # DeepFace works much better with file paths than numpy arrays.
        temp_dir = tempfile.mkdtemp(prefix="kyc_face_")
        temp_selfie_path = os.path.join(temp_dir, "selfie.jpg")
        cv2.imwrite(temp_selfie_path, selfie_image)
        temp_paths.append(temp_selfie_path)

        print("--- 🧠 Running DeepFace AI Analysis... ---")

        id_candidates = []
        for orientation, id_variant in image_orientations(id_card_image).items():
            temp_id_path = os.path.join(temp_dir, f"id_{orientation}.jpg")
            cv2.imwrite(temp_id_path, id_variant)
            temp_paths.append(temp_id_path)
            id_candidates.append((orientation, "full_document", temp_id_path))

            for crop_path in save_face_crops(temp_id_path, temp_dir, f"id_{orientation}"):
                temp_paths.append(crop_path)
                id_candidates.append((orientation, "face_crop", crop_path))

        best_result = None
        best_orientation = None
        best_candidate = None
        for orientation, candidate_type, temp_id_path in id_candidates:
            result = DeepFace.verify(
                temp_id_path,
                temp_selfie_path,
                model_name = MODEL_NAME,
                detector_backend = DETECTOR_BACKEND,
                distance_metric = DISTANCE_METRIC,
                enforce_detection = False
            )

            if best_result is None or result["distance"] < best_result["distance"]:
                best_result = result
                best_orientation = orientation
                best_candidate = candidate_type

        distance = best_result['distance']
        if distance <= APPROVE_THRESHOLD:
            decision = "APPROVED"
            is_match = True
        elif distance <= MANUAL_THRESHOLD:
            decision = "MANUAL_REVIEW"
            is_match = False
        else:
            decision = "REJECTED"
            is_match = False
        
        accuracy_score = round((1 - distance) * 100, 2)

        print(
            f"✅ Face Result: Decision={decision}, Match={is_match}, Dist={distance}, "
            f"Score={accuracy_score}%, Model={MODEL_NAME}, "
            f"Detector={DETECTOR_BACKEND}, ApproveThreshold={APPROVE_THRESHOLD}, "
            f"ManualThreshold={MANUAL_THRESHOLD}, Orientation={best_orientation}, "
            f"Candidate={best_candidate}"
        )

        return {
            "match": is_match,
            "decision": decision,
            "distance": round(distance, 6),
            "score": accuracy_score,
            "model": MODEL_NAME,
            "detector": DETECTOR_BACKEND,
            "metric": DISTANCE_METRIC,
            "orientation": best_orientation,
            "candidate": best_candidate,
            "approve_threshold": APPROVE_THRESHOLD,
            "manual_threshold": MANUAL_THRESHOLD,
            "error": None if is_match else f"Distance {distance:.3f} needs {decision.replace('_', ' ').lower()}"
        }

    except Exception as e:
        print(f"❌ DeepFace Error: {e}")
        
        return {
            "match": False, 
            "decision": "REJECTED",
            "distance": None,
            "score": 0, 
            "model": MODEL_NAME,
            "detector": DETECTOR_BACKEND,
            "metric": DISTANCE_METRIC,
            "error": f"Face check failed: {str(e)}"
        }
    finally:
        for path in temp_paths:
            if os.path.exists(path):
                os.remove(path)
        if "temp_dir" in locals() and os.path.exists(temp_dir):
            os.rmdir(temp_dir)
