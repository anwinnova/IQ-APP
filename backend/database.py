"""
database.py — SQLite backend for IQ
BUG FIXES in this version:
  1. SMTP_APP_PASSWORD key name now matches .env (was causing ALL emails to silently fail)
  2. save_interview: user email lookup now runs BEFORE conn.close() (was using closed conn)
  3. hash(email) uses abs() to prevent negative modulo on some Python builds
  4. validate_token: safely handles None/empty token and user_id=0
  5. get_dashboard: streak sync update runs while conn is still open
  6. Added WAL journal mode for better concurrent access
"""
import sqlite3, os, hashlib, secrets, json, smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, date
from dotenv import load_dotenv

load_dotenv()

# ✅ FIX: Use Railway Volume for persistent storage
# On Railway: add a Volume at /data mount point in Railway dashboard
# Locally: falls back to prepsense.db in project root
DB_PATH = os.getenv("DB_PATH", "/data/prepsense.db" if os.path.isdir("/data") else "prepsense.db")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")
# FIX 1: was SMTP_APP_PASSWORD but .env had ADMIN_APP_PASSWORD — now both match
SMTP_PASS   = os.getenv("SMTP_APP_PASSWORD", "")
SMTP_HOST   = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT   = int(os.getenv("SMTP_PORT", "587"))


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()

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
    # Add last_device column if it doesn't exist yet (migration for existing DBs)
    try:
        c.execute("ALTER TABLE users ADD COLUMN last_device TEXT DEFAULT ''")
    except: pass

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
# EMAIL
# ─────────────────────────────────────────────────────────────
def send_email(to: str, subject: str, body_html: str) -> bool:
    """
    Sends via Gmail SMTP. Never crashes the app — prints error and returns False if anything fails.
    Requires in .env:
      ADMIN_EMAIL=you@gmail.com
      SMTP_APP_PASSWORD=abcd efgh ijkl mnop   (16-char Gmail App Password)
    """
    if not ADMIN_EMAIL or not SMTP_PASS or not to:
        print(f"[EMAIL SKIPPED] SMTP not configured. To:{to} | {subject}")
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
        print(f"[EMAIL SENT] To:{to} | {subject}")
        return True
    except Exception as e:
        print(f"[EMAIL ERROR] To:{to} | {e}")
        return False


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
        ph     = hash_password(password)
        colors = ["#4f8fff","#14b8a6","#8b5cf6","#f59e0b","#ef4444","#22c55e"]
        color  = colors[abs(hash(email)) % len(colors)]   # FIX 3: abs()
        token  = secrets.token_hex(32)
        c.execute(
            "INSERT INTO users (name,email,password_hash,avatar_color,session_token) VALUES (?,?,?,?,?)",
            (name, email.lower(), ph, color, token)
        )
        user_id = c.lastrowid
        c.execute("INSERT INTO daily_streak (user_id) VALUES (?)", (user_id,))
        conn.commit()
        send_email(email, "Welcome to IQ — Elite AI Interview Intelligence",
            f"""<div style="font-family:sans-serif;max-width:560px;margin:auto">
            <h2 style="color:#4f8fff">Welcome, {name}! 🎉</h2>
            <p>Your IQ account is ready. Start practising AI mock interviews and land your dream role.</p>
            <p>Need help? Visit the <strong>Support</strong> section anytime.</p>
            <p>Best,<br><strong>Team IQ</strong></p></div>""")
        send_email(ADMIN_EMAIL, f"[IQ] New Signup: {name}",
            f"<p>New user <strong>{name}</strong> ({email}) registered at {datetime.now().isoformat()}</p>")
        return {"ok": True, "user_id": user_id, "name": name, "email": email,
                "avatar_color": color, "session_token": token}
    except sqlite3.IntegrityError:
        return {"ok": False, "error": "Email already registered"}
    finally:
        conn.close()

def login_user(email: str, password: str, device_info: str = ""):
    """Single-device: rotates session_token every login. Old token/device gets 401."""
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
    c.execute("UPDATE users SET last_login=datetime('now'), session_token=? WHERE id=?",
              (new_token, row["id"]))
    conn.commit()
    conn.close()
    return {"ok": True, "user_id": row["id"], "name": row["name"],
            "email": row["email"], "avatar_color": row["avatar_color"],
            "session_token": new_token}

def validate_token(user_id: int, token: str) -> bool:
    """FIX 4: guard against None/empty/0 inputs."""
    if not token or not user_id:
        return False
    conn = get_conn()
    row  = conn.execute("SELECT session_token FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return bool(row and row["session_token"] and row["session_token"] == token)

def logout_user(user_id: int):
    conn = get_conn()
    conn.execute("UPDATE users SET session_token=NULL WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


# ─────────────────────────────────────────────────────────────
# RECORDINGS
# ─────────────────────────────────────────────────────────────
def save_recording(user_id: int, session_id: str, file_type: str, file_path: str):
    conn = get_conn()
    conn.execute("INSERT INTO recordings (user_id,session_id,file_type,file_path) VALUES (?,?,?,?)",
                 (user_id, session_id, file_type, file_path))
    conn.commit()
    conn.close()

def get_recordings(user_id: int, session_id: str = None) -> list:
    conn = get_conn()
    if session_id:
        rows = conn.execute(
            "SELECT * FROM recordings WHERE user_id=? AND session_id=? ORDER BY created_at",
            (user_id, session_id)).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM recordings WHERE user_id=? ORDER BY created_at DESC",
            (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────
# INTERVIEW HISTORY
# ─────────────────────────────────────────────────────────────
def save_interview(user_id: int, session_meta: dict, feedback: dict, duration_secs: int = 0):
    conn = get_conn()
    c = conn.cursor()

    qs         = feedback.get("question_scores", [])
    tech_avg   = int(sum(q.get("score", 5) for q in qs) / max(len(qs), 1))
    overall    = feedback.get("overall_score", 5)
    comm_score = max(1, min(10, overall + (1 if len(session_meta.get("answers", [])) > 0 else 0)))
    conf_score = max(1, min(10, overall))

    c.execute("""
    INSERT INTO interview_sessions
    (user_id,role,skills,difficulty,experience_level,
     overall_score,verdict,hire_recommendation,
     communication_score,confidence_score,technical_score,
     feedback_json,duration_secs)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (user_id, session_meta.get("role",""), session_meta.get("skills",""),
          session_meta.get("difficulty","medium"), session_meta.get("experience_level","fresher"),
          overall, feedback.get("verdict","Average"), feedback.get("hire_recommendation","Maybe"),
          comm_score, conf_score, tech_avg, json.dumps(feedback), duration_secs))

    _update_streak(c, user_id)

    for skill in session_meta.get("skills", "").split(","):
        skill = skill.strip()
        if skill:
            c.execute("INSERT INTO skill_scores (user_id,skill,score) VALUES (?,?,?)",
                      (user_id, skill, tech_avg))

    conn.commit()

    # FIX 2: fetch user BEFORE closing conn
    user_row = None
    try:
        user_row = conn.execute("SELECT name, email FROM users WHERE id=?", (user_id,)).fetchone()
    except Exception as e:
        print(f"[USER LOOKUP ERROR] {e}")

    conn.close()  # NOW we can close

    # Post-interview email (runs after conn closed — uses only local variables)
    if user_row:
        try:
            verdict    = feedback.get("verdict", "Average")
            strengths  = "".join(f"<li>{s}</li>" for s in feedback.get("strengths", [])[:3])
            imps       = "".join(f"<li>{i}</li>" for i in feedback.get("improvements", [])[:3])
            next_steps = feedback.get("next_steps", "Keep practising!")
            hire       = feedback.get("hire_recommendation", "Maybe")
            send_email(user_row["email"],
                f"[IQ] Your Interview Results — {overall}/10 ({verdict})",
                f"""<div style="font-family:sans-serif;max-width:600px;margin:auto">
                <h2 style="color:#4f8fff">Hi {user_row['name']},</h2>
                <p>Your mock interview for <strong>{session_meta.get('role','')}</strong> is complete!</p>
                <table style="width:100%;border-collapse:collapse;margin:12px 0">
                  <tr style="background:#1e1b4b"><td style="padding:10px;color:#a78bfa"><strong>Overall Score</strong></td><td style="padding:10px;color:#fff;font-size:1.2em"><strong>{overall}/10</strong></td></tr>
                  <tr style="background:#f9fafb"><td style="padding:10px"><strong>Verdict</strong></td><td style="padding:10px">{verdict}</td></tr>
                  <tr style="background:#1e1b4b"><td style="padding:10px;color:#a78bfa"><strong>Hire Recommendation</strong></td><td style="padding:10px;color:#fff">{hire}</td></tr>
                  <tr style="background:#f9fafb"><td style="padding:10px"><strong>Communication</strong></td><td style="padding:10px">{feedback.get('communication_score',5)}/10</td></tr>
                  <tr style="background:#1e1b4b"><td style="padding:10px;color:#a78bfa"><strong>Confidence</strong></td><td style="padding:10px;color:#fff">{feedback.get('confidence_score',5)}/10</td></tr>
                  <tr style="background:#f9fafb"><td style="padding:10px"><strong>Technical</strong></td><td style="padding:10px">{feedback.get('technical_score',5)}/10</td></tr>
                </table>
                <h3 style="color:#22c55e">✓ Strengths</h3><ul>{strengths}</ul>
                <h3 style="color:#f59e0b">📈 Improve</h3><ul>{imps}</ul>
                <h3 style="color:#4f8fff">🚀 Next Steps</h3><p>{next_steps}</p>
                <p>Best of luck,<br><strong>Team IQ</strong></p></div>""")
        except Exception as email_err:
            print(f"[POST-INTERVIEW EMAIL ERROR] {email_err}")


def _update_streak(c, user_id: int):
    today = date.today().isoformat()
    row   = c.execute("SELECT * FROM daily_streak WHERE user_id=?", (user_id,)).fetchone()
    if not row:
        c.execute("INSERT INTO daily_streak (user_id,current_streak,longest_streak,last_practice_date,total_sessions) VALUES (?,1,1,?,1)",
                  (user_id, today))
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
    c.execute("UPDATE daily_streak SET current_streak=?,longest_streak=?,last_practice_date=?,total_sessions=total_sessions+1 WHERE user_id=?",
              (new_streak, longest, today, user_id))


# ─────────────────────────────────────────────────────────────
# FEEDBACK
# ─────────────────────────────────────────────────────────────
def save_feedback(user_id: int, user_email: str, stars: int, aspects: str, comment: str):
    conn = get_conn()
    conn.execute("INSERT INTO feedback_submissions (user_id,user_email,stars,aspects,comment) VALUES (?,?,?,?,?)",
                 (user_id, user_email, stars, aspects, comment))
    conn.commit()
    conn.close()
    send_email(ADMIN_EMAIL, f"[IQ Feedback] {stars}★ from {user_email or 'guest'}",
        f"<h3>New Feedback</h3><p><strong>User:</strong> {user_email or user_id}</p><p><strong>Stars:</strong> {stars}/5</p><p><strong>Aspects:</strong> {aspects}</p><p><strong>Comment:</strong><br>{comment}</p><p><em>{datetime.now().isoformat()}</em></p>")
    if user_email:
        send_email(user_email, "[IQ] Thank you for your feedback!",
            f"<div style='font-family:sans-serif'><h2>Thank you! ⭐</h2><p>We received your <strong>{stars}/5 star</strong> rating. Your input helps us improve IQ for everyone.</p><p>Best,<br><strong>Team IQ</strong></p></div>")
    return {"ok": True}


# ─────────────────────────────────────────────────────────────
# SUPPORT
# ─────────────────────────────────────────────────────────────
def submit_support(user_id: int, name: str, email: str, subject: str, message: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO support_tickets (user_id,name,email,subject,message) VALUES (?,?,?,?,?)",
              (user_id, name, email, subject, message))
    ticket_id = c.lastrowid
    conn.commit()
    conn.close()
    send_email(ADMIN_EMAIL, f"[IQ Support #{ticket_id}] {subject}",
        f"<h3>Ticket #{ticket_id}</h3><p><strong>Name:</strong> {name}</p><p><strong>Email:</strong> {email}</p><p><strong>Subject:</strong> {subject}</p><p><strong>Message:</strong><br>{message}</p><p><em>{datetime.now().isoformat()}</em></p>")
    send_email(email, f"[IQ Support] We received your message — Ticket #{ticket_id}",
        f"<div style='font-family:sans-serif'><h3>Hi {name},</h3><p>We've received your request (Ticket #{ticket_id}) and will respond within 24 hours.</p><p><strong>Your message:</strong><br>{message}</p><p>Best,<br>Team IQ</p></div>")
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
    sessions = c.execute("SELECT * FROM interview_sessions WHERE user_id=? ORDER BY created_at DESC", (user_id,)).fetchall()
    streak   = c.execute("SELECT * FROM daily_streak WHERE user_id=?", (user_id,)).fetchone()
    trend    = [{"date": s["created_at"][:10], "score": s["overall_score"], "role": s["role"]} for s in sessions[:10]][::-1]
    n        = len(sessions)
    avg_overall = round(sum(s["overall_score"] for s in sessions) / max(n,1), 1)
    avg_comm    = round(sum(s["communication_score"] for s in sessions) / max(n,1), 1)
    avg_conf    = round(sum(s["confidence_score"] for s in sessions) / max(n,1), 1)
    avg_tech    = round(sum(s["technical_score"] for s in sessions) / max(n,1), 1)
    # FIX 5: update while conn is open
    if streak and streak["total_sessions"] != n:
        c.execute("UPDATE daily_streak SET total_sessions=? WHERE user_id=?", (n, user_id))
        conn.commit()
    skills_raw = c.execute("SELECT skill, AVG(score) as avg_score, COUNT(*) as cnt FROM skill_scores WHERE user_id=? GROUP BY skill ORDER BY avg_score DESC", (user_id,)).fetchall()
    skill_data = [{"skill": r["skill"], "score": round(r["avg_score"],1), "count": r["cnt"]} for r in skills_raw]
    recent = [{"id":s["id"],"role":s["role"],"score":s["overall_score"],"verdict":s["verdict"],"difficulty":s["difficulty"],"hire":s["hire_recommendation"],"date":s["created_at"][:10]} for s in sessions[:5]]
    conn.close()
    return {
        "user":   {"name":user["name"],"email":user["email"],"avatar_color":user["avatar_color"],"member_since":user["created_at"][:10]},
        "stats":  {"total_interviews":n,"avg_score":avg_overall,"avg_communication":avg_comm,"avg_confidence":avg_conf,"avg_technical":avg_tech,"best_score":max((s["overall_score"] for s in sessions),default=0)},
        "streak": {"current":streak["current_streak"] if streak else 0,"longest":streak["longest_streak"] if streak else 0,"total":n},
        "trend":trend,"skill_data":skill_data,"recent":recent,
    }

def get_session_detail(session_id: int, user_id: int) -> dict:
    conn = get_conn()
    row = conn.execute("SELECT * FROM interview_sessions WHERE id=? AND user_id=?", (session_id, user_id)).fetchone()
    conn.close()
    if not row:
        return {}
    return {"id":row["id"],"role":row["role"],"score":row["overall_score"],"verdict":row["verdict"],"hire":row["hire_recommendation"],"feedback":json.loads(row["feedback_json"]) if row["feedback_json"] else {},"date":row["created_at"],"difficulty":row["difficulty"],"duration":row["duration_secs"]}


init_db()


# ─────────────────────────────────────────────────────────────
# ADMIN — Export all data (questions, answers, user info)
# Access via /api/admin/export?key=YOUR_ADMIN_KEY
# ─────────────────────────────────────────────────────────────
ADMIN_KEY = os.getenv("ADMIN_KEY", "")  # set this in .env for security

def admin_export_all() -> dict:
    """Export everything: users, sessions with Q&A, devices."""
    conn = get_conn()
    c = conn.cursor()

    users = c.execute("""
        SELECT id, name, email, avatar_color, last_device, created_at, last_login
        FROM users ORDER BY created_at DESC
    """).fetchall()

    sessions = c.execute("""
        SELECT s.*, u.name as user_name, u.email as user_email, u.last_device
        FROM interview_sessions s
        JOIN users u ON s.user_id = u.id
        ORDER BY s.created_at DESC
    """).fetchall()

    feedback = c.execute("""
        SELECT * FROM feedback_submissions ORDER BY created_at DESC
    """).fetchall()

    support = c.execute("""
        SELECT * FROM support_tickets ORDER BY created_at DESC
    """).fetchall()

    conn.close()

    # Parse Q&A from feedback_json for each session
    sessions_out = []
    for s in sessions:
        row = dict(s)
        try:
            fb = json.loads(row.get("feedback_json") or "{}")
            row["question_scores"] = fb.get("question_scores", [])
            row["strengths"]       = fb.get("strengths", [])
            row["improvements"]    = fb.get("improvements", [])
            row["verdict"]         = fb.get("verdict", row.get("verdict", ""))
        except:
            row["question_scores"] = []
        del row["feedback_json"]  # don't double-send
        sessions_out.append(row)

    return {
        "exported_at":   datetime.now().isoformat(),
        "total_users":   len(users),
        "total_sessions":len(sessions),
        "users":         [dict(u) for u in users],
        "sessions":      sessions_out,
        "feedback":      [dict(f) for f in feedback],
        "support":       [dict(s) for s in support],
    }


init_db()
