import json
import os
import sqlite3
from datetime import datetime, timezone


DB_PATH = os.getenv("KYC_DB_PATH", "data/kyc_records.db")


def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS kyc_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                name TEXT NOT NULL,
                dob TEXT NOT NULL,
                aadhaar_last4 TEXT NOT NULL,
                aadhaar_masked TEXT,
                pan_masked TEXT,
                document_path TEXT,
                verification_source TEXT,
                liveness_completed INTEGER NOT NULL DEFAULT 0,
                decision TEXT NOT NULL,
                face_match INTEGER NOT NULL DEFAULT 0,
                face_score REAL,
                face_distance REAL,
                face_model TEXT,
                face_detector TEXT,
                face_metric TEXT,
                face_orientation TEXT,
                face_candidate TEXT,
                debug_metadata TEXT
            )
            """
        )


def create_kyc_record(user, ocr_aadhaar, ocr_pan, face_result, document_path, source_type, liveness_completed):
    init_db()

    metadata = {
        "approve_threshold": face_result.get("approve_threshold"),
        "manual_threshold": face_result.get("manual_threshold"),
        "error": face_result.get("error"),
    }

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO kyc_records (
                created_at,
                name,
                dob,
                aadhaar_last4,
                aadhaar_masked,
                pan_masked,
                document_path,
                verification_source,
                liveness_completed,
                decision,
                face_match,
                face_score,
                face_distance,
                face_model,
                face_detector,
                face_metric,
                face_orientation,
                face_candidate,
                debug_metadata
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                user.get("name"),
                user.get("dob"),
                user.get("aadhaar_last4"),
                ocr_aadhaar.get("masked_number"),
                mask_identifier(ocr_pan.get("pan_number")) if ocr_pan.get("pan_number") else None,
                document_path,
                source_type,
                1 if liveness_completed else 0,
                face_result.get("decision", "REJECTED"),
                1 if face_result.get("match") else 0,
                face_result.get("score"),
                face_result.get("distance"),
                face_result.get("model"),
                face_result.get("detector"),
                face_result.get("metric"),
                face_result.get("orientation"),
                face_result.get("candidate"),
                json.dumps(metadata),
            ),
        )
        return cursor.lastrowid


def mask_identifier(value):
    if not value:
        return None
    return f"XXXX XXXX {str(value)[-4:]}"
