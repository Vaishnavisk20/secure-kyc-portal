import mimetypes
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from services.env_loader import load_env_file

load_env_file()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "kyc-uploads")


def supabase_storage_configured():
    return bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY and SUPABASE_STORAGE_BUCKET)


def persist_upload(local_path, kind):
    metadata = {
        "kind": kind,
        "local_path": local_path,
        "storage_bucket": None,
        "storage_path": None,
        "storage_url": None,
        "storage_error": None,
    }

    if not local_path or not os.path.exists(local_path) or not supabase_storage_configured():
        return metadata

    try:
        storage_path = upload_to_supabase_storage(local_path, kind)
        metadata["storage_bucket"] = SUPABASE_STORAGE_BUCKET
        metadata["storage_path"] = storage_path
        metadata["storage_url"] = storage_object_url(storage_path)
    except Exception as exc:
        metadata["storage_error"] = str(exc)

    return metadata


def upload_to_supabase_storage(local_path, kind):
    project_url = SUPABASE_URL.rstrip("/")
    safe_filename = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(local_path).name).strip("._")
    object_name = f"{kind}/{int(time.time() * 1000)}_{safe_filename or 'upload.bin'}"
    encoded_path = urllib.parse.quote(object_name)
    upload_url = f"{project_url}/storage/v1/object/{SUPABASE_STORAGE_BUCKET}/{encoded_path}"

    content_type = mimetypes.guess_type(local_path)[0] or "application/octet-stream"
    with open(local_path, "rb") as file:
        request_obj = urllib.request.Request(
            upload_url,
            data=file.read(),
            headers={
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Content-Type": content_type,
                "x-upsert": "true",
            },
            method="POST",
        )

    try:
        with urllib.request.urlopen(request_obj, timeout=30):
            return object_name
    except urllib.error.HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Supabase Storage upload failed: HTTP {exc.code} {message}") from exc


def storage_object_url(storage_path):
    encoded_path = urllib.parse.quote(storage_path)
    return f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/{SUPABASE_STORAGE_BUCKET}/{encoded_path}"
