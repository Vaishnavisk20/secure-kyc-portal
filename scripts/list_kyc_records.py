import json
import os
import sqlite3
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from services.db_service import DB_PATH, init_db


def main():
    init_db()
    with sqlite3.connect(DB_PATH) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT
                id,
                created_at,
                name,
                dob,
                aadhaar_masked,
                pan_masked,
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

    print(json.dumps([dict(row) for row in rows], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
