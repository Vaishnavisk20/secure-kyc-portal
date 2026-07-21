import cv2
import numpy as np


MIN_FRAMES = 3
MIN_FACE_FRAMES = 2
MIN_BLUR_SCORE = 35
MIN_MOTION_SCORE = 2.0
MIN_FACE_SHIFT = 0.012


def _face_detector():
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    return cv2.CascadeClassifier(cascade_path)


def _largest_face(faces):
    if len(faces) == 0:
        return None
    return max(faces, key=lambda face: face[2] * face[3])


def _center(face, width, height):
    x, y, w, h = face
    return ((x + w / 2) / width, (y + h / 2) / height)


def verify_liveness(frames):
    usable_frames = [frame for frame in frames if frame is not None and frame.size > 0]
    if len(usable_frames) < MIN_FRAMES:
        return {
            "passed": False,
            "status": "FAILED",
            "reason": "Capture multiple live frames using the camera.",
            "frames": len(usable_frames),
        }

    detector = _face_detector()
    face_centers = []
    blur_scores = []
    gray_frames = []

    for frame in usable_frames:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray_frames.append(gray)
        blur_scores.append(float(cv2.Laplacian(gray, cv2.CV_64F).var()))

        faces = detector.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(70, 70),
        )
        face = _largest_face(faces)
        if face is not None:
            height, width = gray.shape[:2]
            face_centers.append(_center(face, width, height))

    avg_blur = float(np.mean(blur_scores)) if blur_scores else 0.0
    if len(face_centers) < MIN_FACE_FRAMES:
        return {
            "passed": False,
            "status": "FAILED",
            "reason": "Could not detect a live face in enough frames.",
            "frames": len(usable_frames),
            "face_frames": len(face_centers),
            "blur_score": round(avg_blur, 2),
        }

    if avg_blur < MIN_BLUR_SCORE:
        return {
            "passed": False,
            "status": "FAILED",
            "reason": "Camera image is too blurry for liveness.",
            "frames": len(usable_frames),
            "face_frames": len(face_centers),
            "blur_score": round(avg_blur, 2),
        }

    motion_scores = []
    for previous, current in zip(gray_frames, gray_frames[1:]):
        resized_previous = cv2.resize(previous, (160, 120))
        resized_current = cv2.resize(current, (160, 120))
        diff = cv2.absdiff(resized_previous, resized_current)
        motion_scores.append(float(np.mean(diff)))

    max_motion = max(motion_scores) if motion_scores else 0.0
    max_shift = 0.0
    for previous, current in zip(face_centers, face_centers[1:]):
        max_shift = max(
            max_shift,
            abs(current[0] - previous[0]) + abs(current[1] - previous[1]),
        )

    passed = max_motion >= MIN_MOTION_SCORE or max_shift >= MIN_FACE_SHIFT
    return {
        "passed": passed,
        "status": "PASSED" if passed else "FAILED",
        "reason": "Live motion detected." if passed else "Please follow the prompt and move slightly before capture.",
        "frames": len(usable_frames),
        "face_frames": len(face_centers),
        "blur_score": round(avg_blur, 2),
        "motion_score": round(max_motion, 2),
        "face_shift": round(max_shift, 4),
    }
