"""
cloudinary_helper.py — Cloudinary upload helper for IQ
Place this file inside your backend/ folder.

Setup:
  1. Sign up free at https://cloudinary.com
  2. Dashboard → copy Cloud Name, API Key, API Secret
  3. Add to .env:
       CLOUDINARY_CLOUD_NAME=your_cloud_name
       CLOUDINARY_API_KEY=your_api_key
       CLOUDINARY_API_SECRET=your_api_secret
  4. pip install cloudinary

What this does:
  • Uploads audio answers, interview videos, screenshots to Cloudinary
  • Returns a permanent public URL that works forever (even after Railway restart)
  • Falls back gracefully — if Cloudinary is not configured, returns local path
  • Automatically sets correct resource_type (video for audio/video, image for screenshots)
  • Organises files into folders: iq/audio/, iq/video/, iq/screenshots/
"""
import os
from dotenv import load_dotenv

load_dotenv()

CLOUD_NAME  = os.getenv("CLOUDINARY_CLOUD_NAME", "")
API_KEY     = os.getenv("CLOUDINARY_API_KEY", "")
API_SECRET  = os.getenv("CLOUDINARY_API_SECRET", "")

# Check if Cloudinary is configured
CLOUDINARY_ENABLED = bool(CLOUD_NAME and API_KEY and API_SECRET)

if CLOUDINARY_ENABLED:
    import cloudinary
    import cloudinary.uploader
    cloudinary.config(
        cloud_name = CLOUD_NAME,
        api_key    = API_KEY,
        api_secret = API_SECRET,
        secure     = True,          # always use https URLs
    )
    print(f"[Cloudinary] Configured — cloud: {CLOUD_NAME}")
else:
    print("[Cloudinary] NOT configured — files will use local paths only")


def upload_file(local_path: str, file_type: str, session_id: str = "", user_id: int = 0) -> dict:
    """
    Upload a file to Cloudinary and return its permanent URL.

    Args:
        local_path: path to the file on disk  e.g. "recordings/audio_xyz.webm"
        file_type:  "audio" | "video" | "screenshot"
        session_id: interview session UUID (used for Cloudinary public_id)
        user_id:    user ID (used for folder organisation)

    Returns:
        {
          "url":      "https://res.cloudinary.com/...",  # permanent URL
          "public_id": "iq/audio/user_1_session_abc",
          "ok":       True,
          "provider": "cloudinary" | "local"
        }
    """
    if not os.path.exists(local_path):
        print(f"[Cloudinary] File not found: {local_path}")
        return {"url": local_path, "public_id": "", "ok": False, "provider": "local"}

    if not CLOUDINARY_ENABLED:
        # Return local path as URL — works on localhost, not persistent on Railway
        return {"url": f"/{local_path}", "public_id": "", "ok": True, "provider": "local"}

    try:
        # Determine Cloudinary resource_type
        # "video" handles both audio and video files in Cloudinary
        # "image" for screenshots / PNG
        if file_type == "screenshot":
            resource_type = "image"
            folder        = f"iq/screenshots/user_{user_id}"
        else:
            resource_type = "video"   # Cloudinary uses "video" for all audio+video
            folder        = f"iq/{file_type}/user_{user_id}"

        # Build a clean public_id from session + type
        import uuid as _uuid
        short_id   = (session_id or _uuid.uuid4().hex)[:12]
        public_id  = f"{folder}/{file_type}_{short_id}"

        result = cloudinary.uploader.upload(
            local_path,
            resource_type = resource_type,
            public_id     = public_id,
            overwrite     = True,
            # Auto-delete after 30 days to save storage (remove this line to keep forever)
            # invalidate  = True,
        )

        url = result.get("secure_url", "")
        print(f"[Cloudinary] Uploaded {file_type}: {url}")
        return {"url": url, "public_id": result.get("public_id",""), "ok": True, "provider": "cloudinary"}

    except Exception as e:
        print(f"[Cloudinary ERROR] {e}")
        # Fall back to local path so the app doesn't break
        return {"url": f"/{local_path}", "public_id": "", "ok": False, "provider": "local", "error": str(e)}


def delete_file(public_id: str, file_type: str = "video") -> bool:
    """Delete a file from Cloudinary by its public_id."""
    if not CLOUDINARY_ENABLED or not public_id:
        return False
    try:
        resource_type = "image" if file_type == "screenshot" else "video"
        cloudinary.uploader.destroy(public_id, resource_type=resource_type)
        return True
    except Exception as e:
        print(f"[Cloudinary DELETE ERROR] {e}")
        return False
