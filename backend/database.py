"""
database.py — SQLite via sqlite3 (no ORM needed, zero extra deps)
Tables:
  users                — auth + profile + session_token (single-device enforcement)
  interview_sessions   — every completed interview + full feedback JSON
  daily_streak         — streak tracking per user
  skill_scores         — per-skill score history
  recordings           — video/audio/screenshot file paths per session
  feedback_submissions — user ratings stored + emailed to admin
  support_tickets      — support emails stored + emailed to admin
"""
import sqlite3, os, hashlib, secrets, json, smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, date
from dotenv import load_dotenv

load_dotenv()

#<<<<<<< HEAD
# ✅ FIX: Use Railway Volume for persistent storage
# On Railway: add a Volume at /data mount point in Railway dashboard
# Locally: falls back to prepsense.db in project root
DB_PATH = os.getenv("DB_PATH", "/data/prepsense.db" if os.path.isdir("/data") else "prepsense.db")
ADMIN_EMAIL   = os.getenv("ADMIN_EMAIL", "")
RESEND_KEY    = os.getenv("RESEND_API_KEY", "")      # preferred: resend.com (works on Railway)
NOTIFY_EMAIL  = os.getenv("NOTIFY_EMAIL", ADMIN_EMAIL)
# Gmail SMTP fallback (works locally, blocked on Railway free tier)
_SMTP_PASS    = (os.getenv("SMTP_APP_PASSWORD", "") or "").split("#")[0].strip()
_SMTP_HOST    = os.getenv("SMTP_HOST", "smtp.gmail.com")
_SMTP_PORT    = int(os.getenv("SMTP_PORT", "587"))
#=======
DB_PATH     = os.getenv("DB_PATH", "prepsense.db")   # Render sets this to /app/data/prepsense.db
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")        # set in .env  e.g. you@gmail.com
SMTP_PASS   = os.getenv("SMTP_APP_PASSWORD", "")  # Gmail app-password (16 chars)
SMTP_HOST   = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT   = int(os.getenv("SMTP_PORT", "587"))
ADMIN_KEY   = os.getenv("ADMIN_KEY", "")          # Secret key for /api/admin/export
#>>>>>>> 6fc2046 (Added deployment config and environment setup)


# ─────────────────────────────────────────────────────────────
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()

    # Users — session_token enforces single-device login
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        name          TEXT NOT NULL,
        email         TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        avatar_color  TEXT DEFAULT '#4f8fff',
        session_token TEXT DEFAULT NULL,
        last_device   TEXT DEFAULT '',
        created_at    TEXT DEFAULT (datetime('now')),
        last_login    TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS interview_sessions (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id             INTEGER NOT NULL,
        role                TEXT,
        skills              TEXT,
        difficulty          TEXT,
        experience_level    TEXT,
        overall_score       INTEGER,
        verdict             TEXT,
        hire_recommendation TEXT,
        communication_score INTEGER DEFAULT 0,
        confidence_score    INTEGER DEFAULT 0,
        technical_score     INTEGER DEFAULT 0,
        filler_words        INTEGER DEFAULT 0,
        speaking_speed      TEXT DEFAULT 'Normal',
        feedback_json       TEXT,
        duration_secs       INTEGER DEFAULT 0,
        created_at          TEXT DEFAULT (datetime('now')),
        FOREIGN KEY(user_id) REFERENCES users(id)
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS daily_streak (
        id                 INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id            INTEGER NOT NULL UNIQUE,
        current_streak     INTEGER DEFAULT 0,
        longest_streak     INTEGER DEFAULT 0,
        last_practice_date TEXT,
        total_sessions     INTEGER DEFAULT 0,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS skill_scores (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL,
        skill       TEXT NOT NULL,
        score       INTEGER,
        recorded_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY(user_id) REFERENCES users(id)
    )""")

    # Recordings: video, audio answer files, screenshots — all stored on disk, path saved here
    c.execute("""
    CREATE TABLE IF NOT EXISTS recordings (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL,
        session_id  TEXT NOT NULL,
        file_type   TEXT NOT NULL,
        file_path   TEXT NOT NULL,
        created_at  TEXT DEFAULT (datetime('now')),
        FOREIGN KEY(user_id) REFERENCES users(id)
    )""")

    # User feedback / ratings — every submission emailed to admin
    c.execute("""
    CREATE TABLE IF NOT EXISTS feedback_submissions (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER DEFAULT 0,
        user_email TEXT DEFAULT '',
        stars      INTEGER,
        aspects    TEXT DEFAULT '',
        comment    TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now'))
    )""")

    # Support tickets — stored + emailed to admin, auto-reply sent to user
    c.execute("""
    CREATE TABLE IF NOT EXISTS support_tickets (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER DEFAULT 0,
        name       TEXT DEFAULT '',
        email      TEXT NOT NULL,
        subject    TEXT DEFAULT '',
        message    TEXT NOT NULL,
        status     TEXT DEFAULT 'open',
        created_at TEXT DEFAULT (datetime('now'))
    )""")

    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────
# EMAIL HELPER
# ─────────────────────────────────────────────────────────────
#<<<<<<< HEAD
def _send_via_resend(to: str, subject: str, body_html: str) -> bool:
    """Send via Resend HTTP API — works on Railway (HTTPS port 443, not blocked)."""
    if not RESEND_KEY or not to:
        return False
    try:
        payload = json.dumps({
            "from":    "IQ Platform <onboarding@resend.dev>",
            "to":      [to],
            "subject": subject,
            "html":    body_html,
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://api.resend.com/emails",
            data    = payload,
            headers = {"Authorization": f"Bearer {RESEND_KEY}",
                       "Content-Type": "application/json"},
            method  = "POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            print(f"[EMAIL via Resend] → {to} | {subject}")
            return True
    except Exception as e:
        print(f"[EMAIL Resend ERROR] → {to} | {e}")
        return False

def _send_via_smtp(to: str, subject: str, body_html: str) -> bool:
    """Gmail SMTP fallback — works locally, blocked on Railway free tier."""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    if not ADMIN_EMAIL or not _SMTP_PASS or not to:
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"IQ Interview <{ADMIN_EMAIL}>"
        msg["To"]      = to
        msg.attach(MIMEText(body_html, "html"))
        with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=15) as server:
            server.ehlo(); server.starttls(); server.ehlo()
            server.login(ADMIN_EMAIL, _SMTP_PASS)
            server.sendmail(ADMIN_EMAIL, [to], msg.as_string())
        print(f"[EMAIL via Gmail] → {to} | {subject}")
        return True
    except Exception as e:
        print(f"[EMAIL Gmail ERROR] → {to} | {e}")
        return False

def _email_worker(to: str, subject: str, body_html: str):
    """Background worker: try Resend first, then Gmail SMTP."""
    if not _send_via_resend(to, subject, body_html):
        _send_via_smtp(to, subject, body_html)

def send_email(to: str, subject: str, body_html: str) -> bool:
    """
    Non-blocking email in background thread.
    Tries Resend API first (works on Railway), falls back to Gmail SMTP (works locally).
    Add RESEND_API_KEY to Railway Variables for emails to work on Railway.
    """
    if not to:
        return False
    threading.Thread(target=_email_worker, args=(to, subject, body_html), daemon=True).start()
    return True

#=======
def send_email(to: str, subject: str, body_html: str):
    """Send email via SMTP. Silently prints if not configured."""
    if not ADMIN_EMAIL or not SMTP_PASS or not to:
        print(f"[EMAIL SKIPPED — not configured] To:{to} | Subject:{subject}")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"IQ Interview <{ADMIN_EMAIL}>"
        msg["To"]      = to
        msg.attach(MIMEText(body_html, "html"))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(ADMIN_EMAIL, SMTP_PASS)
            server.sendmail(ADMIN_EMAIL, [to], msg.as_string())
        print(f"[EMAIL SENT] To:{to} | Subject:{subject}")
        return True
    except Exception as e:
        print(f"[EMAIL ERROR] To:{to} | {e}")
        return False

#>>>>>>> 6fc2046 (Added deployment config and environment setup)

# ─────────────────────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    salt = "prepsense_secret_2026"
    return hashlib.sha256((password + salt).encode()).hexdigest()

def register_user(name: str, email: str, password: str):
    conn = get_conn()
    try:
        c = conn.cursor()
        ph    = hash_password(password)
        colors = ["#4f8fff","#14b8a6","#8b5cf6","#f59e0b","#ef4444","#22c55e"]
        color  = colors[hash(email) % len(colors)]
        token  = secrets.token_hex(32)
        c.execute(
            "INSERT INTO users (name,email,password_hash,avatar_color,session_token) VALUES (?,?,?,?,?)",
            (name, email.lower(), ph, color, token)
        )
        user_id = c.lastrowid
        c.execute("INSERT INTO daily_streak (user_id) VALUES (?)", (user_id,))
        conn.commit()

        # Welcome email to user
        send_email(
            email,
            "Welcome to IQ — Elite AI Interview Intelligence",
            f"""<h2>Welcome, {name}!</h2>
            <p>Your IQ account is ready. Start practising AI mock interviews, track your progress, and land your dream role.</p>
            <p>Need help? Reply to this email anytime.</p>
            <p>Best,<br>Team IQ</p>"""
        )
        # Notify admin of new signup
        send_email(
            ADMIN_EMAIL,
            f"[IQ] New Signup: {name}",
            f"<p>New user <strong>{name}</strong> ({email}) registered at {datetime.now().isoformat()}</p>"
        )
        return {"ok": True, "user_id": user_id, "name": name, "email": email,
                "avatar_color": color, "session_token": token}
    except sqlite3.IntegrityError:
        return {"ok": False, "error": "Email already registered"}
    finally:
        conn.close()

def login_user(email: str, password: str, device_info: str = ""):
    """
    Single-device enforcement:
    A new session_token is generated on every login.
    Previous tokens (other tabs/devices) become invalid immediately.
    """
    conn = get_conn()
    c = conn.cursor()
    ph  = hash_password(password)
    row = c.execute(
        "SELECT * FROM users WHERE email=? AND password_hash=?",
        (email.lower(), ph)
    ).fetchone()
    if not row:
        conn.close()
        return {"ok": False, "error": "Invalid email or password"}

    new_token = secrets.token_hex(32)
    # Store device_info if column exists (graceful — older DBs may not have it)
    try:
        c.execute(
            "UPDATE users SET last_login=datetime('now'), session_token=?, last_device=? WHERE id=?",
            (new_token, device_info[:200], row["id"])
        )
    except Exception:
        c.execute(
            "UPDATE users SET last_login=datetime('now'), session_token=? WHERE id=?",
            (new_token, row["id"])
        )
    conn.commit()
    conn.close()
    return {
        "ok":            True,
        "user_id":       row["id"],
        "name":          row["name"],
        "email":         row["email"],
        "avatar_color":  row["avatar_color"],
        "session_token": new_token,
    }

def validate_token(user_id: int, token: str) -> bool:
    """Returns True only if the token matches the DB (single-device check)."""
    if not token:
        return False
    conn = get_conn()
    row  = conn.execute(
        "SELECT session_token FROM users WHERE id=?", (user_id,)
    ).fetchone()
    conn.close()
    return bool(row and row["session_token"] == token)

def logout_user(user_id: int):
    """Clears session_token — logs out all devices."""
    conn = get_conn()
    conn.execute("UPDATE users SET session_token=NULL WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


# ─────────────────────────────────────────────────────────────
# RECORDINGS
# ─────────────────────────────────────────────────────────────
def save_recording(user_id: int, session_id: str, file_type: str, file_path: str):
    """
    file_type: 'video' | 'audio' | 'screenshot'
    file_path: server-side path inside recordings/ folder
    """
    conn = get_conn()
    conn.execute(
        "INSERT INTO recordings (user_id,session_id,file_type,file_path) VALUES (?,?,?,?)",
        (user_id, session_id, file_type, file_path)
    )
    conn.commit()
    conn.close()

def get_recordings(user_id: int, session_id: str = None) -> list:
    conn = get_conn()
    if session_id:
        rows = conn.execute(
            "SELECT * FROM recordings WHERE user_id=? AND session_id=? ORDER BY created_at",
            (user_id, session_id)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM recordings WHERE user_id=? ORDER BY created_at DESC",
            (user_id,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────
# INTERVIEW HISTORY
# ─────────────────────────────────────────────────────────────
def save_interview(user_id: int, session_meta: dict, feedback: dict, duration_secs: int = 0):
    conn = get_conn()
    c = conn.cursor()

    qs       = feedback.get("question_scores", [])
    tech_avg = int(sum(q.get("score",5) for q in qs) / max(len(qs),1))
    overall  = feedback.get("overall_score", 5)
    comm_score = max(1, min(10, overall + (1 if len(session_meta.get("answers",[])) > 0 else 0)))
    conf_score = max(1, min(10, overall))

    c.execute("""
    INSERT INTO interview_sessions
    (user_id,role,skills,difficulty,experience_level,
     overall_score,verdict,hire_recommendation,
     communication_score,confidence_score,technical_score,
     feedback_json,duration_secs)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        user_id,
        session_meta.get("role",""),
        session_meta.get("skills",""),
        session_meta.get("difficulty","medium"),
        session_meta.get("experience_level","fresher"),
        overall,
        feedback.get("verdict","Average"),
        feedback.get("hire_recommendation","Maybe"),
        comm_score,
        conf_score,
        tech_avg,
        json.dumps(feedback),
        duration_secs,
    ))

    _update_streak(c, user_id)

    for skill in session_meta.get("skills","").split(","):
        skill = skill.strip()
        if skill:
            c.execute(
                "INSERT INTO skill_scores (user_id,skill,score) VALUES (?,?,?)",
                (user_id, skill, tech_avg)
            )

    conn.commit()

    # ── Send post-interview result email to user ──────────
    try:
        user_row = conn.execute("SELECT name, email FROM users WHERE id=?", (user_id,)).fetchone()
        if user_row:
            verdict    = feedback.get("verdict", "Average")
            overall    = feedback.get("overall_score", 5)
            strengths  = "".join(f"<li>{s}</li>" for s in feedback.get("strengths", [])[:3])
            imps       = "".join(f"<li>{i}</li>" for i in feedback.get("improvements", [])[:3])
            next_steps = feedback.get("next_steps", "Keep practising!")
            hire       = feedback.get("hire_recommendation", "Maybe")
            send_email(
                user_row["email"],
                f"[IQ] Your Interview Results — {overall}/10 ({verdict})",
                f"""<h2>Hi {user_row['name']},</h2>
                <p>Your mock interview for <strong>{session_meta.get('role','')}</strong> is complete!</p>
                <table style="width:100%;border-collapse:collapse;margin:12px 0;font-family:sans-serif">
                  <tr style="background:#111827"><td style="padding:10px;color:#a78bfa"><strong>Overall Score</strong></td><td style="padding:10px;color:#fff">{overall} / 10</td></tr>
                  <tr><td style="padding:10px"><strong>Verdict</strong></td><td style="padding:10px">{verdict}</td></tr>
                  <tr style="background:#111827"><td style="padding:10px;color:#a78bfa"><strong>Hire Recommendation</strong></td><td style="padding:10px;color:#fff">{hire}</td></tr>
                  <tr><td style="padding:10px"><strong>Communication</strong></td><td style="padding:10px">{feedback.get('communication_score',5)} / 10</td></tr>
                  <tr style="background:#111827"><td style="padding:10px;color:#a78bfa"><strong>Confidence</strong></td><td style="padding:10px;color:#fff">{feedback.get('confidence_score',5)} / 10</td></tr>
                  <tr><td style="padding:10px"><strong>Technical</strong></td><td style="padding:10px">{feedback.get('technical_score',5)} / 10</td></tr>
                </table>
                <h3>&#10003; Strengths</h3><ul>{strengths}</ul>
                <h3>&#128200; Areas to Improve</h3><ul>{imps}</ul>
                <h3>&#128640; Next Steps</h3><p>{next_steps}</p>
                <p>Log in to your <strong>IQ Dashboard</strong> to view the full session breakdown.</p>
                <p>Best of luck,<br><strong>Team IQ</strong></p>"""
            )
    except Exception as email_err:
        print(f"[POST-INTERVIEW EMAIL ERROR] {email_err}")

    conn.close()

def _update_streak(c, user_id: int):
    today = date.today().isoformat()
    row = c.execute("SELECT * FROM daily_streak WHERE user_id=?", (user_id,)).fetchone()
    if not row:
        c.execute(
            "INSERT INTO daily_streak (user_id,current_streak,longest_streak,last_practice_date,total_sessions) VALUES (?,1,1,?,1)",
            (user_id, today)
        )
        return
    last   = row["last_practice_date"]
    streak = row["current_streak"]
    if last == today:
        new_streak = streak
    elif last and (date.fromisoformat(today) - date.fromisoformat(last)).days == 1:
        new_streak = streak + 1
    else:
        new_streak = 1
    longest = max(row["longest_streak"], new_streak)
    c.execute("""
        UPDATE daily_streak
        SET current_streak=?,longest_streak=?,last_practice_date=?,total_sessions=total_sessions+1
        WHERE user_id=?
    """, (new_streak, longest, today, user_id))


# ─────────────────────────────────────────────────────────────
# FEEDBACK / RATINGS
# ─────────────────────────────────────────────────────────────
def save_feedback(user_id: int, user_email: str, stars: int, aspects: str, comment: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO feedback_submissions (user_id,user_email,stars,aspects,comment) VALUES (?,?,?,?,?)",
        (user_id, user_email, stars, aspects, comment)
    )
    conn.commit()
    conn.close()

    # Email admin
    send_email(
        ADMIN_EMAIL,
        f"[IQ Feedback] {stars}\u2605 from {user_email or 'guest'}",
        f"""<h3>New User Feedback</h3>
        <p><strong>User:</strong> {user_email or user_id}</p>
        <p><strong>Stars:</strong> {stars} / 5</p>
        <p><strong>Aspects:</strong> {aspects}</p>
        <p><strong>Comment:</strong><br>{comment}</p>
        <p><em>{datetime.now().isoformat()}</em></p>"""
    )

    # Send confirmation to user
    if user_email:
        send_email(
            user_email,
            "[IQ] Thank you for your feedback!",
            f"""<h2>Thank you for your feedback!</h2>
            <p>We received your <strong>{stars}/5 star</strong> rating. Your input helps us improve IQ for everyone.</p>
            <p>We truly appreciate you taking the time to share your thoughts.</p>
            <p>Best,<br><strong>Team IQ</strong></p>"""
        )

    return {"ok": True}


# ─────────────────────────────────────────────────────────────
# SUPPORT TICKETS
# ─────────────────────────────────────────────────────────────
def submit_support(user_id: int, name: str, email: str, subject: str, message: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO support_tickets (user_id,name,email,subject,message) VALUES (?,?,?,?,?)",
        (user_id, name, email, subject, message)
    )
    ticket_id = c.lastrowid
    conn.commit()
    conn.close()

    # Email admin
    send_email(
        ADMIN_EMAIL,
        f"[IQ Support #{ticket_id}] {subject}",
        f"""<h3>Support Ticket #{ticket_id}</h3>
        <p><strong>Name:</strong> {name}</p>
        <p><strong>Email:</strong> {email}</p>
        <p><strong>Subject:</strong> {subject}</p>
        <p><strong>Message:</strong><br>{message}</p>
        <p><em>{datetime.now().isoformat()}</em></p>"""
    )

    # Auto-reply to user
    send_email(
        email,
        f"[IQ Support] We received your message — Ticket #{ticket_id}",
        f"""<h3>Hi {name},</h3>
        <p>Thank you for reaching out. We've received your support request (Ticket #{ticket_id}) and will respond within 24 hours.</p>
        <p><strong>Your message:</strong><br>{message}</p>
        <p>Best,<br>Team IQ</p>"""
    )
    return {"ok": True, "ticket_id": ticket_id}


# ─────────────────────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────────────────────
def get_dashboard(user_id: int) -> dict:
    conn = get_conn()
    c = conn.cursor()

    user = c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not user:
        conn.close()
        return {}

    sessions = c.execute(
        "SELECT * FROM interview_sessions WHERE user_id=? ORDER BY created_at DESC",
        (user_id,)
    ).fetchall()

    streak = c.execute("SELECT * FROM daily_streak WHERE user_id=?", (user_id,)).fetchone()

    trend = [{"date": s["created_at"][:10], "score": s["overall_score"], "role": s["role"]}
             for s in sessions[:10]][::-1]

    n           = len(sessions)
    avg_overall = round(sum(s["overall_score"] for s in sessions) / max(n,1), 1)
    avg_comm    = round(sum(s["communication_score"] for s in sessions) / max(n,1), 1)
    avg_conf    = round(sum(s["confidence_score"] for s in sessions) / max(n,1), 1)
    avg_tech    = round(sum(s["technical_score"] for s in sessions) / max(n,1), 1)

    # Sync streak total_sessions to actual interview count so dashboard is always accurate
    if streak and streak["total_sessions"] != n:
        c.execute("UPDATE daily_streak SET total_sessions=? WHERE user_id=?", (n, user_id))

    skills_raw = c.execute("""
        SELECT skill, AVG(score) as avg_score, COUNT(*) as cnt
        FROM skill_scores WHERE user_id=?
        GROUP BY skill ORDER BY avg_score DESC
    """, (user_id,)).fetchall()
    skill_data = [{"skill": r["skill"], "score": round(r["avg_score"],1), "count": r["cnt"]}
                  for r in skills_raw]

    recent = [
        {"id": s["id"], "role": s["role"], "score": s["overall_score"],
         "verdict": s["verdict"], "difficulty": s["difficulty"],
         "hire": s["hire_recommendation"], "date": s["created_at"][:10]}
        for s in sessions[:5]
    ]

    conn.commit()
    conn.close()
    return {
        "user":   {"name": user["name"], "email": user["email"],
                   "avatar_color": user["avatar_color"], "member_since": user["created_at"][:10]},
        "stats":  {"total_interviews": n, "avg_score": avg_overall,
                   "avg_communication": avg_comm, "avg_confidence": avg_conf,
                   "avg_technical": avg_tech,
                   "best_score": max((s["overall_score"] for s in sessions), default=0)},
        "streak": {"current": streak["current_streak"] if streak else 0,
                   "longest": streak["longest_streak"] if streak else 0,
                   "total":   n},
        "trend":      trend,
        "skill_data": skill_data,
        "recent":     recent,
    }

def get_session_detail(session_id: int, user_id: int) -> dict:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM interview_sessions WHERE id=? AND user_id=?",
        (session_id, user_id)
    ).fetchone()
    conn.close()
    if not row:
        return {}
    return {
        "id":       row["id"],   "role":     row["role"],
        "score":    row["overall_score"],    "verdict":  row["verdict"],
        "hire":     row["hire_recommendation"],
        "feedback": json.loads(row["feedback_json"]) if row["feedback_json"] else {},
        "date":     row["created_at"],
        "difficulty": row["difficulty"],
        "duration": row["duration_secs"],
    }


# ─────────────────────────────────────────────────────────────
# ADMIN EXPORT — full data dump for admin dashboard
# Protected by ADMIN_KEY in .env
# GET /api/admin/export?key=your_admin_key
# ─────────────────────────────────────────────────────────────
def admin_export_all() -> dict:
    conn = get_conn()
    c    = conn.cursor()

    users = c.execute(
        "SELECT id, name, email, avatar_color, created_at, last_login, last_device FROM users ORDER BY created_at DESC"
    ).fetchall()

    sessions = c.execute(
        "SELECT * FROM interview_sessions ORDER BY created_at DESC LIMIT 200"
    ).fetchall()

    tickets = c.execute(
        "SELECT * FROM support_tickets ORDER BY created_at DESC LIMIT 100"
    ).fetchall()

    feedback = c.execute(
        "SELECT * FROM feedback_submissions ORDER BY created_at DESC LIMIT 100"
    ).fetchall()

    conn.close()
    return {
        "users":    [dict(u) for u in users],
        "sessions": [
            {k: v for k, v in dict(s).items() if k != "feedback_json"}
            for s in sessions
        ],
        "support_tickets":     [dict(t) for t in tickets],
        "feedback_submissions":[dict(f) for f in feedback],
        "exported_at": datetime.now().isoformat(),
        "total_users":    len(users),
        "total_sessions": len(sessions),
    }


# ── Run init on import ────────────────────────────────────────
init_db()
