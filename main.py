"""
main.py — FastAPI backend for IQ
New in this version:
  • Single-device login enforcement (session_token header check on protected routes)
  • /api/logout
  • /api/support  — stores ticket + emails admin + auto-replies user
  • /api/rating   — stores feedback in DB + emails admin
  • /api/save-recording — saves video/audio/screenshot path to DB
  • /api/recordings — retrieve saved recordings
  • LLM helper is abstracted to support Gemini, OpenAI, or Anthropic
Performance tips (see SCALING NOTES at bottom):
  • Run with multiple uvicorn workers: uvicorn main:app --workers 4
  • Consider Redis for session storage when scaling horizontally
"""
from fastapi import FastAPI, UploadFile, File, Form, Request, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from backend.resume import analyze_resume
from backend.interview import start_interview, next_question, generate_career_path
from backend.database import (
    register_user, login_user, logout_user, validate_token,
    get_dashboard, save_interview, get_session_detail,
    save_feedback, submit_support,
    save_recording, get_recordings,
    admin_export_all, ADMIN_KEY,
)
import os, shutil, uuid

app = FastAPI(title="PrepSense API")

# ─────────────────────────────────────────────────────────────
# CLOUDINARY — used only on Railway (when env var is set)
# Locally: files stay in recordings/ on your laptop as before
# On Railway: files upload to Cloudinary for permanent storage
# ─────────────────────────────────────────────────────────────
IS_RAILWAY = bool(os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("CLOUDINARY_CLOUD_NAME"))

if IS_RAILWAY:
    try:
        from backend.cloudinary_helper import upload_file as cloud_upload
        print("[Storage] Cloudinary enabled — files will upload to cloud")
    except Exception as e:
        cloud_upload = None
        print(f"[Storage] Cloudinary import failed: {e} — using local storage")
else:
    cloud_upload = None
    print("[Storage] Running locally — files saved to recordings/ on your machine")

os.makedirs("uploads",     exist_ok=True)
os.makedirs("audio_files", exist_ok=True)
os.makedirs("recordings",  exist_ok=True)   # ← video/audio/screenshots stored here

app.mount("/frontend",   StaticFiles(directory="frontend"),   name="frontend")
app.mount("/audio",      StaticFiles(directory="audio_files"),name="audio")
app.mount("/recordings", StaticFiles(directory="recordings"), name="recordings")


# ─────────────────────────────────────────────────────────────
# HELPER — single-device token check
# Call this on any route that needs to be protected.
# ─────────────────────────────────────────────────────────────
def require_auth(user_id: int, token: str):
    """Raises 401 if token is invalid (wrong device / logged out)."""
    if not validate_token(user_id, token):
        raise HTTPException(status_code=401, detail="Session expired or logged in on another device. Please sign in again.")


@app.get("/")
def home():
    return FileResponse("frontend/index.html")

@app.get("/app")
def serve_ui():
    return FileResponse("frontend/index.html")


# ═══════════════════════════════════════════════
# AUTH
# ═══════════════════════════════════════════════
@app.post("/api/register")
async def api_register(
    name:     str = Form(...),
    email:    str = Form(...),
    password: str = Form(...),
):
    result = register_user(name, email, password)
    if not result["ok"]:
        return JSONResponse(status_code=400, content=result)
    return result

@app.post("/api/login")
async def api_login(
    request:  Request,
    email:    str = Form(...),
    password: str = Form(...),
):
    # ✅ FIX: capture device/browser info for admin view
    device_info = request.headers.get("user-agent", "unknown")[:200]
    result = login_user(email, password, device_info=device_info)
    if not result["ok"]:
        return JSONResponse(status_code=401, content=result)
    return result

@app.post("/api/logout")
async def api_logout(
    user_id: int = Form(...),
    token:   str = Form(...),
):
    require_auth(user_id, token)
    return logout_user(user_id)


# ═══════════════════════════════════════════════
# DASHBOARD
# ═══════════════════════════════════════════════
@app.get("/api/dashboard/{user_id}")
def api_dashboard(user_id: int, token: str = ""):
    # Token is passed as query param: /api/dashboard/1?token=abc
    require_auth(user_id, token)
    data = get_dashboard(user_id)
    if not data:
        return JSONResponse(status_code=404, content={"error": "User not found"})
    return data

@app.get("/api/session/{session_id}")
def api_session_detail(session_id: int, user_id: int, token: str = ""):
    require_auth(user_id, token)
    data = get_session_detail(session_id, user_id)
    if not data:
        return JSONResponse(status_code=404, content={"error": "Session not found"})
    return data


# ═══════════════════════════════════════════════
# RESUME
# ═══════════════════════════════════════════════
@app.post("/upload-resume/")
async def upload_resume(file: UploadFile = File(...)):
    content = await file.read()
    path = f"uploads/{file.filename}"
    with open(path, "wb") as f:
        f.write(content)
    return analyze_resume(path)


# ═══════════════════════════════════════════════
# INTERVIEW
# ═══════════════════════════════════════════════
@app.post("/start-interview/")
async def start(
    role:                str  = Form(...),
    skills:              str  = Form(...),
    experience_level:    str  = Form("fresher"),
    years_of_experience: int  = Form(0),
    difficulty:          str  = Form("medium"),
    num_questions:       int  = Form(5),
    jd_text:             str  = Form(""),
    resume_text:         str  = Form(""),
    user_id:             int  = Form(0),
    token:               str  = Form(""),
    jd_file:     UploadFile   = File(None),
    resume_file: UploadFile   = File(None),
):
    if user_id and token:
        require_auth(user_id, token)

    if jd_file and jd_file.filename:
        raw = await jd_file.read()
        p   = f"uploads/jd_{jd_file.filename}"
        with open(p, "wb") as f: f.write(raw)
        try:
            import fitz
            doc = fitz.open(p)
            jd_text = "".join(pg.get_text() for pg in doc)
        except: pass

    if resume_file and resume_file.filename:
        raw = await resume_file.read()
        p   = f"uploads/res_{resume_file.filename}"
        with open(p, "wb") as f: f.write(raw)
        try:
            import fitz
            doc = fitz.open(p)
            resume_text = "".join(pg.get_text() for pg in doc)
        except: pass

    result = start_interview(
        role=role, skills=skills,
        experience_level=experience_level,
        years_of_experience=years_of_experience,
        difficulty=difficulty,
        num_questions=num_questions,
        jd_text=jd_text,
        resume_text=resume_text,
    )
    if user_id and result.get("session_id"):
        from backend.interview import sessions
        if result["session_id"] in sessions:
            sessions[result["session_id"]]["user_id"] = user_id
    return result


@app.post("/next-question/")
async def next_q(
    session_id:  str        = Form(...),
    file:        UploadFile = File(...),
    text_answer: str        = Form(""),   # fallback if Whisper returns nothing
):
    # ── Save audio locally (always — Whisper reads from local path) ──
    filename    = f"audio_{session_id}_{uuid.uuid4().hex}{os.path.splitext(file.filename)[1] or '.webm'}"
    local_path  = f"recordings/{filename}"
    upload_path = f"uploads/{file.filename or 'ans.webm'}"
    content     = await file.read()

    with open(local_path,  "wb") as f: f.write(content)
    with open(upload_path, "wb") as f: f.write(content)
    print(f"[AUDIO] session={session_id} size={len(content)} bytes")

    # ── Register recording URL in DB ──────────────────────────────────
    from backend.interview import sessions as iv_sessions
    sess = iv_sessions.get(session_id, {})
    uid  = sess.get("user_id", 0)

    if uid:
        if IS_RAILWAY and cloud_upload:
            # 🌐 RAILWAY: upload to Cloudinary → permanent URL saved in DB
            result   = cloud_upload(local_path, "audio", session_id=session_id, user_id=uid)
            file_url = result["url"]
            print(f"[Cloudinary] audio → {file_url}")
        else:
            # 💻 LOCAL: just save the local path — file stays on your laptop
            file_url = f"/recordings/{filename}"

        save_recording(uid, session_id, "audio", file_url)

    return next_question(session_id, upload_path, text_answer.strip())


# ═══════════════════════════════════════════════
# SAVE INTERVIEW
# ═══════════════════════════════════════════════
@app.post("/api/save-interview")
async def api_save(
    user_id:       int  = Form(...),
    session_id:    str  = Form(...),
    feedback_json: str  = Form(...),
    duration_secs: int  = Form(0),
    token:         str  = Form(""),
):
    if token:
        require_auth(user_id, token)
    import json
    from backend.interview import sessions
    sess = sessions.get(session_id, {})
    try:
        feedback = json.loads(feedback_json)
        save_interview(user_id, sess, feedback, duration_secs)
        return {"ok": True}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ═══════════════════════════════════════════════
# RECORDINGS — save video/screenshot from frontend
# ═══════════════════════════════════════════════
@app.post("/api/save-recording")
async def api_save_recording(
    user_id:    int        = Form(...),
    session_id: str        = Form(...),
    file_type:  str        = Form(...),   # 'video' | 'screenshot'
    token:      str        = Form(""),
    file:       UploadFile = File(...),
):
    if token:
        require_auth(user_id, token)

    ext        = os.path.splitext(file.filename)[1] or (".webm" if file_type == "video" else ".png")
    filename   = f"{file_type}_{session_id}_{uuid.uuid4().hex}{ext}"
    local_path = f"recordings/{filename}"
    content    = await file.read()

    with open(local_path, "wb") as f:
        f.write(content)

    if IS_RAILWAY and cloud_upload:
        # 🌐 RAILWAY: upload to Cloudinary → permanent URL
        result   = cloud_upload(local_path, file_type, session_id=session_id, user_id=user_id)
        file_url = result["url"]
        print(f"[Cloudinary] {file_type} → {file_url}")
    else:
        # 💻 LOCAL: file stays in recordings/ on your laptop
        file_url = f"/recordings/{filename}"

    save_recording(user_id, session_id, file_type, file_url)
    return {"ok": True, "url": file_url, "storage": "cloudinary" if IS_RAILWAY else "local"}

@app.get("/api/recordings/{user_id}")
def api_get_recordings(user_id: int, token: str = "", session_id: str = ""):
    require_auth(user_id, token)
    recs = get_recordings(user_id, session_id if session_id else None)
    return {"recordings": recs}


# ═══════════════════════════════════════════════
# CAREER PATH
# ═══════════════════════════════════════════════
@app.post("/api/career-path")
async def api_career_path(
    skills:           str = Form(...),
    goal:             str = Form(...),
    experience_level: str = Form("fresher"),
):
    return generate_career_path(skills, goal, experience_level)


# ═══════════════════════════════════════════════
# RATING / FEEDBACK — stored in DB + emailed to admin
# ═══════════════════════════════════════════════
@app.post("/api/rating")
async def api_rating(
    user_id: int = Form(0),
    stars:   int = Form(...),
    aspects: str = Form(""),
    comment: str = Form(""),
    email:   str = Form(""),
):
    return save_feedback(user_id, email, stars, aspects, comment)


# ═══════════════════════════════════════════════
# SUPPORT — ticket stored in DB + emailed to admin + auto-reply
# ═══════════════════════════════════════════════
@app.post("/api/support")
async def api_support(
    user_id: int = Form(0),
    name:    str = Form(...),
    email:   str = Form(...),
    subject: str = Form(""),
    message: str = Form(...),
):
    return submit_support(user_id, name, email, subject, message)


# ═══════════════════════════════════════════════
# ADMIN — view all users, sessions, Q&A, devices
# ✅ Protected by ADMIN_KEY set in .env
# Usage: GET /api/admin/export?key=your_admin_key
# ═══════════════════════════════════════════════
@app.get("/api/admin/export")
def api_admin_export(key: str = ""):
    if not ADMIN_KEY or key != ADMIN_KEY:
        return JSONResponse(status_code=403, content={"error": "Forbidden — wrong admin key"})
    return admin_export_all()


# ═══════════════════════════════════════════════
# HEALTH CHECK
# ═══════════════════════════════════════════════
@app.get("/health")
def health():
    return {"status": "ok", "db": __import__("backend.database", fromlist=["DB_PATH"]).DB_PATH}


# ═══════════════════════════════════════════════
# SCALING NOTES
# ═══════════════════════════════════════════════
# To handle many concurrent users without lag:
#
# 1. RUN MULTIPLE WORKERS (immediate win):
#    uvicorn main:app --workers 4 --host 0.0.0.0 --port 8000
#
# 2. ADD RATE LIMITING (install slowapi):
#    pip install slowapi
#    from slowapi import Limiter; limiter = Limiter(key_func=get_remote_address)
#    @limiter.limit("10/minute") on heavy routes like /start-interview/
#
# 3. CACHE LLM RESPONSES (for same role+skills combos):
#    Use functools.lru_cache or Redis for question generation.
#
# 4. MOVE WHISPER TO A QUEUE (for many simultaneous submissions):
#    Use Celery + Redis. Route audio → queue → worker → response.
#
# 5. ALTERNATIVE LLMs (swap Gemini for any of these in interview.py):
#    • OpenAI GPT-4o:   openai>=1.0  — os.getenv("OPENAI_API_KEY")
#    • Anthropic Claude: anthropic>=0.20 — os.getenv("ANTHROPIC_API_KEY")
#    • Groq (fast+free): groq>=0.4  — os.getenv("GROQ_API_KEY")
#    • Ollama (offline): requests to http://localhost:11434/api/generate
#    See call_llm() in interview.py — just set LLM_PROVIDER in .env
