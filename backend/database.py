"""
database.py — IQ Platform — Clean single file, zero conflicts
Tables: users, interview_sessions, daily_streak, skill_scores,
        recordings, feedback_submissions, support_tickets,
        login_history, rate_limits, admin_log
"""
import sqlite3, os, hashlib, secrets, json, smtplib, threading, urllib.request
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, date
from dotenv import load_dotenv

load_dotenv()

# ── Environment Variables ─────────────────────────────────────
DB_PATH      = os.getenv("DB_PATH", "prepsense.db")
ADMIN_EMAIL  = os.getenv("ADMIN_EMAIL", "")
ADMIN_KEY    = os.getenv("ADMIN_KEY", "")
SMTP_PASS    = os.getenv("SMTP_APP_PASSWORD", "")
SMTP_HOST    = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT    = int(os.getenv("SMTP_PORT", "587"))
RESEND_KEY   = os.getenv("RESEND_API_KEY", "")   # optional: resend.com works on cloud


# ─────────────────────────────────────────────────────────────
# DATABASE CONNECTION
# ─────────────────────────────────────────────────────────────
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _safe_add_column(cursor, table: str, column: str, col_def: str):
    """Add column only if it doesn't exist — safe for existing DBs."""
    try:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
    except Exception:
        pass  # column already exists — ignore


def init_db():
    conn = get_conn()
    c = conn.cursor()

    # ── USERS ─────────────────────────────────────────────────
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT NOT NULL,
        email           TEXT NOT NULL UNIQUE,
        password_hash   TEXT NOT NULL,
        avatar_color    TEXT DEFAULT '#4f8fff',
        session_token   TEXT DEFAULT NULL,
        last_device     TEXT DEFAULT '',
        last_ip         TEXT DEFAULT '',
        last_browser    TEXT DEFAULT '',
        last_os         TEXT DEFAULT '',
        is_banned       INTEGER DEFAULT 0,
        ban_reason      TEXT DEFAULT '',
        is_admin        INTEGER DEFAULT 0,
        total_logins    INTEGER DEFAULT 0,
        created_at      TEXT DEFAULT (datetime('now')),
        last_login      TEXT
    )""")

    # ── INTERVIEW SESSIONS ─────────────────────────────────────
    c.execute("""
    CREATE TABLE IF NOT EXISTS interview_sessions (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id             INTEGER NOT NULL,
        role                TEXT,
        skills              TEXT,
        difficulty          TEXT,
        experience_level    TEXT,
        overall_score       INTEGER DEFAULT 0,
        verdict             TEXT,
        hire_recommendation TEXT,
        communication_score INTEGER DEFAULT 0,
        confidence_score    INTEGER DEFAULT 0,
        technical_score     INTEGER DEFAULT 0,
        filler_words        INTEGER DEFAULT 0,
        speaking_speed      TEXT DEFAULT 'Normal',
        feedback_json       TEXT,
        qa_history          TEXT DEFAULT '[]',
        duration_secs       INTEGER DEFAULT 0,
        ip_address          TEXT DEFAULT '',
        created_at          TEXT DEFAULT (datetime('now')),
        FOREIGN KEY(user_id) REFERENCES users(id)
    )""")

    # ── DAILY STREAK ───────────────────────────────────────────
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

    # ── SKILL SCORES ───────────────────────────────────────────
    c.execute("""
    CREATE TABLE IF NOT EXISTS skill_scores (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL,
        skill       TEXT NOT NULL,
        score       INTEGER,
        recorded_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY(user_id) REFERENCES users(id)
    )""")

    # ── RECORDINGS ─────────────────────────────────────────────
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

    # ── FEEDBACK / RATINGS ─────────────────────────────────────
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

    # ── SUPPORT TICKETS ────────────────────────────────────────
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

    # ── LOGIN HISTORY ──────────────────────────────────────────
    c.execute("""
    CREATE TABLE IF NOT EXISTS login_history (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER DEFAULT 0,
        email       TEXT NOT NULL,
        ip_address  TEXT DEFAULT '',
        device      TEXT DEFAULT '',
        browser     TEXT DEFAULT '',
        os_info     TEXT DEFAULT '',
        status      TEXT DEFAULT 'success',
        created_at  TEXT DEFAULT (datetime('now'))
    )""")

    # ── ADMIN LOG ──────────────────────────────────────────────
    c.execute("""
    CREATE TABLE IF NOT EXISTS admin_log (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id   INTEGER DEFAULT 0,
        action     TEXT NOT NULL,
        target     TEXT DEFAULT '',
        detail     TEXT DEFAULT '',
        ip_address TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now'))
    )""")

    # ── Safe migrations for existing DBs ──────────────────────
    _safe_add_column(c, "users", "last_ip",      "TEXT DEFAULT ''")
    _safe_add_column(c, "users", "last_browser", "TEXT DEFAULT ''")
    _safe_add_column(c, "users", "last_os",      "TEXT DEFAULT ''")
    _safe_add_column(c, "users", "is_banned",    "INTEGER DEFAULT 0")
    _safe_add_column(c, "users", "ban_reason",   "TEXT DEFAULT ''")
    _safe_add_column(c, "users", "is_admin",     "INTEGER DEFAULT 0")
    _safe_add_column(c, "users", "total_logins", "INTEGER DEFAULT 0")
    _safe_add_column(c, "interview_sessions", "qa_history",  "TEXT DEFAULT '[]'")
    _safe_add_column(c, "interview_sessions", "ip_address",  "TEXT DEFAULT ''")

    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────
# EMAIL — Gmail SMTP (local) + Resend API (cloud)
# ─────────────────────────────────────────────────────────────
def _send_via_resend(to: str, subject: str, body_html: str) -> bool:
    """Resend.com HTTP API — works on cloud servers."""
    if not RESEND_KEY or not to:
        return False
    try:
        payload = json.dumps({
            "from":    f"IQ Platform <{ADMIN_EMAIL or 'noreply@resend.dev'}>",
            "to":      [to],
            "subject": subject,
            "html":    body_html,
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://api.resend.com/emails",
            data    = payload,
            headers = {"Authorization": f"Bearer {RESEND_KEY}",
                       "Content-Type":  "application/json"},
            method  = "POST",
        )
        with urllib.request.urlopen(req, timeout=10):
            print(f"[EMAIL Resend] → {to}")
            return True
    except Exception as e:
        print(f"[EMAIL Resend ERROR] {e}")
        return False


def _send_via_smtp(to: str, subject: str, body_html: str) -> bool:
    """Gmail SMTP — works locally."""
    if not ADMIN_EMAIL or not SMTP_PASS or not to:
        print(f"[EMAIL SKIPPED — not configured] To:{to}")
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
        print(f"[EMAIL SMTP] → {to}")
        return True
    except Exception as e:
        print(f"[EMAIL SMTP ERROR] {e}")
        return False


def _email_worker(to: str, subject: str, body_html: str):
    if not _send_via_resend(to, subject, body_html):
        _send_via_smtp(to, subject, body_html)


def send_email(to: str, subject: str, body_html: str) -> bool:
    """Send email in background thread — non-blocking."""
    if not to:
        return False
    threading.Thread(
        target=_email_worker,
        args=(to, subject, body_html),
        daemon=True
    ).start()
    return True


# ─────────────────────────────────────────────────────────────
# AUTH HELPERS
# ─────────────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    salt = "prepsense_secret_2026"
    return hashlib.sha256((password + salt).encode()).hexdigest()


def _parse_ua(ua: str):
    """Extract browser and OS from user-agent string."""
    ua = ua.lower()
    browser = "Unknown"
    os_info = "Unknown"
    if "edg" in ua:                              browser = "Edge"
    elif "chrome" in ua:                         browser = "Chrome"
    elif "firefox" in ua:                        browser = "Firefox"
    elif "safari" in ua and "chrome" not in ua:  browser = "Safari"
    elif "opera" in ua or "opr" in ua:           browser = "Opera"
    if "windows" in ua:                          os_info = "Windows"
    elif "android" in ua:                        os_info = "Android"
    elif "iphone" in ua or "ipad" in ua:         os_info = "iOS"
    elif "mac" in ua:                            os_info = "macOS"
    elif "linux" in ua:                          os_info = "Linux"
    return browser, os_info


# ─────────────────────────────────────────────────────────────
# USER REGISTRATION & LOGIN
# ─────────────────────────────────────────────────────────────
def register_user(name: str, email: str, password: str):
    conn = get_conn()
    try:
        c = conn.cursor()
        ph     = hash_password(password)
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
        # Welcome email
        send_email(email, "Welcome to IQ — Elite AI Interview Intelligence",
            f"""<h2>Welcome, {name}!</h2>
            <p>Your IQ account is ready. Start practising AI mock interviews, track your progress, and land your dream role.</p>
            <p>Need help? Reply to this email anytime.</p>
            <p>Best,<br>Team IQ</p>""")
        send_email(ADMIN_EMAIL, f"[IQ] New Signup: {name}",
            f"<p>New user <strong>{name}</strong> ({email}) registered at {datetime.now().isoformat()}</p>")
        return {"ok": True, "user_id": user_id, "name": name, "email": email,
                "avatar_color": color, "session_token": token}
    except sqlite3.IntegrityError:
        return {"ok": False, "error": "Email already registered"}
    finally:
        conn.close()


def login_user(email: str, password: str, device_info: str = "", ip_address: str = ""):
    """Single-device enforcement + full login tracking."""
    conn = get_conn()
    c    = conn.cursor()
    ph   = hash_password(password)
    row  = c.execute(
        "SELECT * FROM users WHERE email=? AND password_hash=?",
        (email.lower(), ph)
    ).fetchone()

    if not row:
        # Log failed attempt
        try:
            c.execute(
                "INSERT INTO login_history (user_id,email,ip_address,device,status) VALUES (0,?,?,?,'failed')",
                (email.lower(), ip_address, device_info[:200])
            )
            conn.commit()
        except Exception:
            pass
        conn.close()
        return {"ok": False, "error": "Invalid email or password"}

    # Check if banned
    try:
        if row["is_banned"]:
            conn.close()
            return {"ok": False, "error": f"Account suspended: {row['ban_reason'] or 'Contact support'}"}
    except Exception:
        pass

    browser, os_info = _parse_ua(device_info)
    new_token = secrets.token_hex(32)

    # Update user record
    try:
        c.execute("""UPDATE users SET
            last_login=datetime('now'), session_token=?,
            last_device=?, last_ip=?, last_browser=?, last_os=?,
            total_logins=COALESCE(total_logins,0)+1
            WHERE id=?""",
            (new_token, device_info[:200], ip_address, browser, os_info, row["id"]))
    except Exception:
        c.execute(
            "UPDATE users SET last_login=datetime('now'), session_token=? WHERE id=?",
            (new_token, row["id"]))

    # Log login history
    try:
        c.execute(
            "INSERT INTO login_history (user_id,email,ip_address,device,browser,os_info,status) VALUES (?,?,?,?,?,?,'success')",
            (row["id"], email.lower(), ip_address, device_info[:200], browser, os_info))
    except Exception:
        pass

    conn.commit()
    conn.close()

    is_admin = 0
    try:
        is_admin = row["is_admin"] or 0
    except Exception:
        pass

    return {
        "ok":            True,
        "user_id":       row["id"],
        "name":          row["name"],
        "email":         row["email"],
        "avatar_color":  row["avatar_color"],
        "session_token": new_token,
        "is_admin":      is_admin,
    }


def validate_token(user_id: int, token: str) -> bool:
    if not token:
        return False
    conn = get_conn()
    row  = conn.execute(
        "SELECT session_token FROM users WHERE id=?", (user_id,)
    ).fetchone()
    conn.close()
    return bool(row and row["session_token"] == token)


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
def save_interview(user_id: int, session_meta: dict, feedback: dict,
                   duration_secs: int = 0, ip_address: str = ""):
    conn = get_conn()
    c    = conn.cursor()

    qs        = feedback.get("question_scores", [])
    tech_avg  = int(sum(q.get("score", 5) for q in qs) / max(len(qs), 1))
    overall   = feedback.get("overall_score", 5)
    comm_score = max(1, min(10, overall))
    conf_score = max(1, min(10, overall))

    # Build Q&A history
    qa_list = []
    questions = session_meta.get("questions", [])
    answers   = session_meta.get("answers", [])
    for i, (q, a) in enumerate(zip(questions, answers), 1):
        qa_list.append({
            "q_num":    i,
            "question": q,
            "answer":   a,
            "score":    qs[i-1].get("score", 5)    if i-1 < len(qs) else 5,
            "feedback": qs[i-1].get("feedback", "") if i-1 < len(qs) else "",
        })

    c.execute("""
    INSERT INTO interview_sessions
        (user_id, role, skills, difficulty, experience_level,
         overall_score, verdict, hire_recommendation,
         communication_score, confidence_score, technical_score,
         feedback_json, qa_history, duration_secs, ip_address)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        user_id,
        session_meta.get("role", ""),
        session_meta.get("skills", ""),
        session_meta.get("difficulty", "medium"),
        session_meta.get("experience_level", "fresher"),
        overall,
        feedback.get("verdict", "Average"),
        feedback.get("hire_recommendation", "Maybe"),
        comm_score,
        conf_score,
        tech_avg,
        json.dumps(feedback),
        json.dumps(qa_list),
        duration_secs,
        ip_address,
    ))

    _update_streak(c, user_id)

    for skill in session_meta.get("skills", "").split(","):
        skill = skill.strip()
        if skill:
            c.execute(
                "INSERT INTO skill_scores (user_id,skill,score) VALUES (?,?,?)",
                (user_id, skill, tech_avg)
            )

    conn.commit()

    # Post-interview result email
    try:
        user_row = conn.execute(
            "SELECT name, email FROM users WHERE id=?", (user_id,)
        ).fetchone()
        if user_row:
            verdict    = feedback.get("verdict", "Average")
            score      = feedback.get("overall_score", 5)
            strengths  = "".join(f"<li>{s}</li>" for s in feedback.get("strengths", [])[:3])
            imps       = "".join(f"<li>{i}</li>" for i in feedback.get("improvements", [])[:3])
            next_steps = feedback.get("next_steps", "Keep practising!")
            hire       = feedback.get("hire_recommendation", "Maybe")
            send_email(
                user_row["email"],
                f"[IQ] Your Interview Results — {score}/10 ({verdict})",
                f"""<h2>Hi {user_row['name']},</h2>
                <p>Your mock interview for <strong>{session_meta.get('role','')}</strong> is complete!</p>
                <table style="width:100%;border-collapse:collapse;margin:12px 0;font-family:sans-serif">
                  <tr style="background:#111827"><td style="padding:10px;color:#a78bfa"><strong>Overall Score</strong></td><td style="padding:10px;color:#fff">{score} / 10</td></tr>
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
                <p>Best,<br><strong>Team IQ</strong></p>"""
            )
    except Exception as e:
        print(f"[POST-INTERVIEW EMAIL ERROR] {e}")

    conn.close()


def _update_streak(c, user_id: int):
    today = date.today().isoformat()
    row   = c.execute(
        "SELECT * FROM daily_streak WHERE user_id=?", (user_id,)
    ).fetchone()
    if not row:
        c.execute(
            "INSERT INTO daily_streak (user_id,current_streak,longest_streak,last_practice_date,total_sessions) VALUES (?,1,1,?,1)",
            (user_id, today)
        )
        return
    last = row["last_practice_date"]
    curr = row["current_streak"] or 0
    lon  = row["longest_streak"]  or 0
    tot  = row["total_sessions"]  or 0
    if last == today:
        c.execute(
            "UPDATE daily_streak SET total_sessions=? WHERE user_id=?",
            (tot + 1, user_id)
        )
    else:
        from datetime import timedelta
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        new_streak = curr + 1 if last == yesterday else 1
        new_longest = max(lon, new_streak)
        c.execute("""UPDATE daily_streak SET
            current_streak=?, longest_streak=?, last_practice_date=?, total_sessions=?
            WHERE user_id=?""",
            (new_streak, new_longest, today, tot + 1, user_id)
        )


# ─────────────────────────────────────────────────────────────
# FEEDBACK & SUPPORT
# ─────────────────────────────────────────────────────────────
def save_feedback(user_id: int, user_email: str, stars: int, aspects: str, comment: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO feedback_submissions (user_id,user_email,stars,aspects,comment) VALUES (?,?,?,?,?)",
        (user_id, user_email, stars, aspects, comment)
    )
    conn.commit()
    conn.close()
    send_email(ADMIN_EMAIL, f"[IQ Feedback] {stars}\u2605 from {user_email or 'guest'}",
        f"""<h3>New User Feedback</h3>
        <p><strong>Stars:</strong> {stars}/5</p>
        <p><strong>Aspects:</strong> {aspects}</p>
        <p><strong>Comment:</strong><br>{comment}</p>""")
    if user_email:
        send_email(user_email, "[IQ] Thank you for your feedback!",
            f"""<h2>Thank you for your feedback!</h2>
            <p>We received your <strong>{stars}/5 star</strong> rating.</p>
            <p>Best,<br><strong>Team IQ</strong></p>""")
    return {"ok": True}


def submit_support(user_id: int, name: str, email: str, subject: str, message: str):
    conn = get_conn()
    c    = conn.cursor()
    c.execute(
        "INSERT INTO support_tickets (user_id,name,email,subject,message) VALUES (?,?,?,?,?)",
        (user_id, name, email, subject, message)
    )
    ticket_id = c.lastrowid
    conn.commit()
    conn.close()
    send_email(ADMIN_EMAIL, f"[IQ Support #{ticket_id}] {subject}",
        f"""<h3>Support Ticket #{ticket_id}</h3>
        <p><strong>Name:</strong> {name}</p>
        <p><strong>Email:</strong> {email}</p>
        <p><strong>Message:</strong><br>{message}</p>""")
    send_email(email, f"[IQ Support] Ticket #{ticket_id} received",
        f"""<h3>Hi {name},</h3>
        <p>We received your request (Ticket #{ticket_id}) and will reply within 24 hours.</p>
        <p><strong>Your message:</strong><br>{message}</p>
        <p>Best,<br>Team IQ</p>""")
    return {"ok": True, "ticket_id": ticket_id}


# ─────────────────────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────────────────────
def get_dashboard(user_id: int) -> dict:
    conn = get_conn()
    c    = conn.cursor()

    user = c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not user:
        conn.close()
        return {}

    sessions = c.execute(
        "SELECT * FROM interview_sessions WHERE user_id=? ORDER BY created_at DESC",
        (user_id,)
    ).fetchall()

    streak = c.execute(
        "SELECT * FROM daily_streak WHERE user_id=?", (user_id,)
    ).fetchone()

    n          = len(sessions)
    avg_overall = round(sum(s["overall_score"] for s in sessions) / max(n, 1), 1)
    avg_comm    = round(sum(s["communication_score"] for s in sessions) / max(n, 1), 1)
    avg_conf    = round(sum(s["confidence_score"] for s in sessions) / max(n, 1), 1)
    avg_tech    = round(sum(s["technical_score"] for s in sessions) / max(n, 1), 1)

    if streak and streak["total_sessions"] != n:
        c.execute("UPDATE daily_streak SET total_sessions=? WHERE user_id=?", (n, user_id))

    skills_raw = c.execute("""
        SELECT skill, AVG(score) as avg_score, COUNT(*) as cnt
        FROM skill_scores WHERE user_id=? GROUP BY skill ORDER BY avg_score DESC
    """, (user_id,)).fetchall()
    skill_data = [{"skill": r["skill"], "score": round(r["avg_score"], 1), "count": r["cnt"]}
                  for r in skills_raw]

    trend  = [{"date": s["created_at"][:10], "score": s["overall_score"], "role": s["role"]}
              for s in sessions[:10]][::-1]
    recent = [{"id": s["id"], "role": s["role"], "score": s["overall_score"],
               "verdict": s["verdict"], "difficulty": s["difficulty"],
               "hire": s["hire_recommendation"], "date": s["created_at"][:10]}
              for s in sessions[:5]]

    conn.commit()
    conn.close()
    return {
        "user":   {"name": user["name"], "email": user["email"],
                   "avatar_color": user["avatar_color"],
                   "member_since": user["created_at"][:10]},
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
    row  = conn.execute(
        "SELECT * FROM interview_sessions WHERE id=? AND user_id=?",
        (session_id, user_id)
    ).fetchone()
    conn.close()
    if not row:
        return {}
    return {
        "id":       row["id"],
        "role":     row["role"],
        "score":    row["overall_score"],
        "verdict":  row["verdict"],
        "hire":     row["hire_recommendation"],
        "feedback": json.loads(row["feedback_json"]) if row["feedback_json"] else {},
        "date":     row["created_at"],
        "difficulty": row["difficulty"],
        "duration": row["duration_secs"],
    }


# ─────────────────────────────────────────────────────────────
# ADMIN ACTIONS
# ─────────────────────────────────────────────────────────────
def ban_user(user_id: int, reason: str = "Violation of terms",
             admin_id: int = 0, ip: str = "") -> dict:
    conn = get_conn()
    conn.execute(
        "UPDATE users SET is_banned=1, ban_reason=?, session_token=NULL WHERE id=?",
        (reason, user_id)
    )
    try:
        conn.execute(
            "INSERT INTO admin_log (admin_id,action,target,detail,ip_address) VALUES (?,?,?,?,?)",
            (admin_id, "ban_user", str(user_id), reason, ip)
        )
    except Exception:
        pass
    conn.commit()
    conn.close()
    return {"ok": True, "message": f"User {user_id} banned"}


def unban_user(user_id: int, admin_id: int = 0, ip: str = "") -> dict:
    conn = get_conn()
    conn.execute(
        "UPDATE users SET is_banned=0, ban_reason='' WHERE id=?", (user_id,)
    )
    try:
        conn.execute(
            "INSERT INTO admin_log (admin_id,action,target,ip_address) VALUES (?,?,?,?)",
            (admin_id, "unban_user", str(user_id), ip)
        )
    except Exception:
        pass
    conn.commit()
    conn.close()
    return {"ok": True, "message": f"User {user_id} unbanned"}


def delete_user(user_id: int, admin_id: int = 0, ip: str = "") -> dict:
    conn = get_conn()
    conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.execute("DELETE FROM interview_sessions WHERE user_id=?", (user_id,))
    conn.execute("DELETE FROM daily_streak WHERE user_id=?", (user_id,))
    conn.execute("DELETE FROM skill_scores WHERE user_id=?", (user_id,))
    try:
        conn.execute(
            "INSERT INTO admin_log (admin_id,action,target,ip_address) VALUES (?,?,?,?)",
            (admin_id, "delete_user", str(user_id), ip)
        )
    except Exception:
        pass
    conn.commit()
    conn.close()
    return {"ok": True}


def close_support_ticket(ticket_id: int, admin_id: int = 0) -> dict:
    conn = get_conn()
    conn.execute(
        "UPDATE support_tickets SET status='closed' WHERE id=?", (ticket_id,)
    )
    conn.commit()
    conn.close()
    return {"ok": True}


def get_login_history(user_id: int) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM login_history WHERE user_id=? ORDER BY created_at DESC LIMIT 50",
        (user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_full_session_qa(session_id: int, user_id: int) -> dict:
    conn = get_conn()
    row  = conn.execute(
        "SELECT * FROM interview_sessions WHERE id=? AND user_id=?",
        (session_id, user_id)
    ).fetchone()
    conn.close()
    if not row:
        return {}
    fb = json.loads(row["feedback_json"]) if row["feedback_json"] else {}
    try:
        qa = json.loads(row["qa_history"]) if row["qa_history"] else []
    except Exception:
        qa = []
    return {
        "session_id": row["id"],
        "role":       row["role"],
        "date":       row["created_at"],
        "score":      row["overall_score"],
        "qa_history": qa,
        "feedback":   fb,
        "duration":   row["duration_secs"],
    }


def admin_export_all() -> dict:
    conn = get_conn()
    c    = conn.cursor()

    users = c.execute("""
        SELECT id, name, email, avatar_color, is_banned, ban_reason,
               is_admin, total_logins, last_ip, last_browser, last_os,
               last_device, created_at, last_login
        FROM users ORDER BY created_at DESC
    """).fetchall()

    sessions = c.execute("""
        SELECT id, user_id, role, skills, difficulty, experience_level,
               overall_score, verdict, hire_recommendation,
               communication_score, confidence_score, technical_score,
               duration_secs, ip_address, qa_history, created_at
        FROM interview_sessions ORDER BY created_at DESC LIMIT 500
    """).fetchall()

    tickets  = c.execute(
        "SELECT * FROM support_tickets ORDER BY created_at DESC LIMIT 200"
    ).fetchall()

    feedback = c.execute(
        "SELECT * FROM feedback_submissions ORDER BY created_at DESC LIMIT 200"
    ).fetchall()

    login_hist = c.execute(
        "SELECT * FROM login_history ORDER BY created_at DESC LIMIT 500"
    ).fetchall()

    # Per-user stats
    user_stats = c.execute("""
        SELECT user_id, COUNT(*) as session_count,
               AVG(overall_score) as avg_score,
               MAX(overall_score) as best_score
        FROM interview_sessions GROUP BY user_id
    """).fetchall()
    stats_map = {r["user_id"]: dict(r) for r in user_stats}

    users_out = []
    for u in users:
        ud = dict(u)
        ud["interview_stats"] = stats_map.get(
            u["id"], {"session_count": 0, "avg_score": 0, "best_score": 0}
        )
        users_out.append(ud)

    conn.close()
    return {
        "users":               users_out,
        "sessions":            [dict(s) for s in sessions],
        "support_tickets":     [dict(t) for t in tickets],
        "feedback_submissions":[dict(f) for f in feedback],
        "login_history":       [dict(l) for l in login_hist],
        "exported_at":         datetime.now().isoformat(),
        "total_users":         len(users),
        "total_sessions":      len(sessions),
    }


# ── Run init on import ────────────────────────────────────────
init_db()
