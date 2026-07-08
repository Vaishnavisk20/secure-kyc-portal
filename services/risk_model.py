# services/risk_model.py
import joblib
import os
import numpy as np

# Load ML Model if it exists
model_path = os.path.join(os.path.dirname(__file__), "../ml/risk_model.pkl")
try:
    _model = joblib.load(model_path)
except:
    _model = None

def _to_percent(value):
    # Ensures value is 0-100
    return value * 100 if value <= 1 else value

def predict_risk(face_match_score, name_match_score, verhoeff_valid, blur_score):
    """
    Calculates Risk Score (0 = Safe, 100 = High Risk)
    """
    face_pct = _to_percent(face_match_score)
    name_pct = _to_percent(name_match_score)
    verhoeff_flag = 1 if verhoeff_valid else 0

    # 1. USE ML MODEL IF AVAILABLE
    if _model is not None:
        try:
            # Predict probability of Fraud (Class 1)
            prob = _model.predict_proba([[face_pct, name_pct, verhoeff_flag]])[0][1]
            return prob * 100
        except:
            pass # Fallback

    # 2. FALLBACK MANUAL LOGIC
    risk = 50 
    
    # Penalties
    if not verhoeff_valid: risk += 50 # Invalid number is huge risk
    if blur_score < 60: risk += 20    # Blurry image
    
    # Rewards
    if name_pct > 80: risk -= 20
    if face_pct > 80: risk -= 20
    
    return max(0, min(100, risk))