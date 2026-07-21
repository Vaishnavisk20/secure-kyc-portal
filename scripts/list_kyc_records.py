import json
import os
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from services.db_service import get_connection, init_db


def main():
    init_db()
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                created_at,
                name,
                dob,
                aadhaar_masked,
                pan_masked,
                aadhaar_document_path,
                aadhaar_storage_path,
                pan_document_path,
                pan_storage_path,
                selfie_path,
                selfie_storage_path,
                decision,
                face_score,
                face_distance,
                face_model,
                face_detector,
                face_orientation,
                face_candidate,
                verification_source
            FROM kyc_records
            ORDER BY id DESC
            LIMIT 20
            """
        ).fetchall()

    print(json.dumps([dict(row) for row in rows], indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
