"""
interview.py — Interview engine
New in this version:
  • call_llm() is LLM-agnostic: supports Gemini, OpenAI, Anthropic Claude, Groq, Ollama
    Set LLM_PROVIDER in .env to switch. Default: gemini
  • make_audio() saves to recordings/ folder so answers persist on disk
"""
from backend.utils import speech_to_text, text_to_speech
import requests, os, uuid, json
from dotenv import load_dotenv

load_dotenv()

# ── LLM PROVIDER SELECTION ─────────────────────────────────
# Set LLM_PROVIDER in your .env file to switch AI provider:
#   LLM_PROVIDER=gemini       (default — needs GEMINI_API_KEY)
#   LLM_PROVIDER=openai       (needs OPENAI_API_KEY)
#   LLM_PROVIDER=anthropic    (needs ANTHROPIC_API_KEY)
#   LLM_PROVIDER=groq         (needs GROQ_API_KEY — fastest, often free tier)
#   LLM_PROVIDER=ollama       (fully offline, needs Ollama running locally)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()

GEMINI_KEY    = os.getenv("GEMINI_API_KEY", "")
OPENAI_KEY    = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GROQ_KEY      = os.getenv("GROQ_API_KEY", "")
OLLAMA_MODEL  = os.getenv("OLLAMA_MODEL", "llama3")
OLLAMA_URL    = os.getenv("OLLAMA_URL", "http://localhost:11434")

sessions = {}


# ── LLM ABSTRACTION ────────────────────────────────────────
def call_llm(prompt: str) -> str:
    """
    Single function to call whichever LLM is configured.
    Change LLM_PROVIDER in .env without touching any other code.
    """
    if LLM_PROVIDER == "openai":
        return _call_openai(prompt)
    elif LLM_PROVIDER == "anthropic":
        return _call_anthropic(prompt)
    elif LLM_PROVIDER == "groq":
        return _call_groq(prompt)
    elif LLM_PROVIDER == "ollama":
        return _call_ollama(prompt)
    else:
        return _call_gemini(prompt)  # default

# Keep old name as alias so nothing else breaks
def call_gemini(prompt: str) -> str:
    return call_llm(prompt)

def _call_gemini(prompt: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=60)
    return res.json()["candidates"][0]["content"]["parts"][0]["text"]

def _call_openai(prompt: str) -> str:
    import openai
    client = openai.OpenAI(api_key=OPENAI_KEY)
    resp   = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2000,
    )
    return resp.choices[0].message.content

def _call_anthropic(prompt: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    msg    = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text

def _call_groq(prompt: str) -> str:
    url  = "https://api.groq.com/openai/v1/chat/completions"
    res  = requests.post(
        url,
        headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
        json={"model": "llama3-70b-8192", "messages": [{"role":"user","content":prompt}]},
        timeout=60,
    )
    return res.json()["choices"][0]["message"]["content"]

def _call_ollama(prompt: str) -> str:
    res = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
        timeout=120,
    )
    return res.json()["response"]


# ── helpers ───────────────────────────────────────────────────
def make_audio(text: str) -> str:
    filename = f"audio_{uuid.uuid4().hex}.mp3"
    path     = os.path.join("audio_files", filename)
    text_to_speech(text, path)
    return filename

FILLER_WORDS = ["uh","um","like","you know","basically","actually","literally",
                "sort of","kind of","right","okay so","so yeah","i mean"]

def count_fillers(text: str) -> int:
    text_lower = text.lower()
    return sum(text_lower.count(fw) for fw in FILLER_WORDS)

def estimate_speaking_speed(text: str, duration_hint: int = 30) -> str:
    words = len(text.split())
    wpm = (words / max(duration_hint, 1)) * 60
    if wpm < 100: return "Too Slow"
    if wpm < 130: return "Slow"
    if wpm < 180: return "Normal"
    if wpm < 220: return "Fast"
    return "Too Fast"


# ─────────────────────────────────────────────────────────────
# START INTERVIEW
# ─────────────────────────────────────────────────────────────
def start_interview(role, skills, experience_level="fresher", years_of_experience=0,
                    difficulty="medium", num_questions=5, jd_text="", resume_text=""):
    session_id = str(uuid.uuid4())

    context = []
    if jd_text.strip():     context.append(f"Job Description:\n{jd_text[:3000]}")
    if resume_text.strip(): context.append(f"Candidate Resume:\n{resume_text[:3000]}")
    context_block = "\n\n".join(context)

    diff_desc = {
        "easy":   "beginner-friendly, fundamentals and concepts",
        "medium": "intermediate — theory, practical scenarios, problem-solving",
        "hard":   "advanced — system design, edge cases, architecture",
    }.get(difficulty, "intermediate mix")

    exp_note = (
        f"Candidate has {years_of_experience} year(s) experience. Ask mid/senior level questions."
        if experience_level == "experienced"
        else "Candidate is a fresher. Focus on fundamentals, projects, learning attitude."
    )

    skill_gap_note = ""
    if jd_text.strip() and resume_text.strip():
        skill_gap_note = "Also note any skills mentioned in the JD but missing from the Resume — ask questions that expose those gaps naturally."

    prompt = f"""You are a senior technical interviewer at a top tech company conducting a REAL interview.

Generate EXACTLY {num_questions} interview questions.

Role: {role}
Skills: {skills}
Experience: {experience_level.capitalize()}{f" ({years_of_experience} yrs)" if experience_level=="experienced" else ""}
Difficulty: {difficulty.capitalize()} — {diff_desc}

{context_block}

{exp_note}
{skill_gap_note}

STRICT RULES:
- Output ONLY the questions, nothing else
- No numbering, bullets, dashes or intro text
- One question per line
- Align to JD if provided; reference resume projects/tech if provided
- Mix behavioral and technical questions
- Start easier, increase difficulty progressively
"""

    raw       = call_llm(prompt)
    questions = [q.strip() for q in raw.split("\n") if q.strip()][:num_questions]

    skill_gaps = []
    if jd_text.strip():
        gap_prompt = f"""Compare these:
JD requires: {jd_text[:1500]}
Candidate skills: {skills}
Resume: {resume_text[:1000]}

List ONLY the skill gaps (skills in JD but NOT in candidate profile).
Output: JSON array of strings, e.g. ["Docker","Kubernetes"]
No markdown, no explanation."""
        try:
            gap_raw = call_llm(gap_prompt).strip()
            if gap_raw.startswith("```"): gap_raw = gap_raw.split("```")[1].lstrip("json")
            skill_gaps = json.loads(gap_raw)
        except: skill_gaps = []

    sessions[session_id] = {
        "role": role, "skills": skills,
        "experience_level": experience_level,
        "years_of_experience": years_of_experience,
        "difficulty": difficulty,
        "num_questions": num_questions,
        "questions": questions,
        "answers": [],
        "current": 0,
        "follow_ups": {},
        "in_follow_up": False,
        "follow_up_answer": None,
        "filler_counts": [],
        "jd_text": jd_text,
        "resume_text": resume_text,
        "skill_gaps": skill_gaps,
        "start_time": __import__("time").time(),
        "user_id": 0,
    }

    intro    = f"Hello! Welcome to your {role} interview. I'll ask you {len(questions)} questions. Let's begin."
    first_q  = questions[0]
    filename = make_audio(intro + " " + first_q)

    return {
        "session_id":      session_id,
        "question":        first_q,
        "question_number": 1,
        "total_questions": len(questions),
        "audio":           f"http://127.0.0.1:8000/audio/{filename}",
        "skill_gaps":      skill_gaps,
    }


# ─────────────────────────────────────────────────────────────
# NEXT QUESTION
# ─────────────────────────────────────────────────────────────
def next_question(session_id: str, audio_path: str, text_answer: str = ""):
    session = sessions.get(session_id)
    if not session:
        return {"error": "Invalid session"}

    # ── Transcribe audio with Whisper ──────────────────────────
    answer = ""
    try:
        transcribed = speech_to_text(audio_path)
        if transcribed and transcribed.strip():
            answer = transcribed.strip()
            print(f"[WHISPER] Transcribed: '{answer[:80]}...' " if len(answer)>80 else f"[WHISPER] Transcribed: '{answer}'")
        else:
            print(f"[WHISPER] Empty transcription from audio: {audio_path}")
    except Exception as e:
        print(f"[WHISPER ERROR] {e}")

    # ── Fallback: use text typed/passed from frontend if Whisper got nothing ──
    if not answer and text_answer:
        answer = text_answer
        print(f"[FALLBACK] Using text_answer: '{answer[:80]}'")

    # ── Last resort: mark as no answer ──
    if not answer:
        answer = "[No answer provided]"
        print("[WARNING] No audio and no text answer received")

    fillers = count_fillers(answer)
    session["filler_counts"].append(fillers)

    if session["in_follow_up"]:
        session["follow_up_answer"] = answer
        session["in_follow_up"] = False
        session["current"] += 1
        if session["current"] >= len(session["questions"]):
            return _finish(session)
        return _ask_next(session)

    session["answers"].append(answer)

    should_follow_up = _should_follow_up(answer, session)
    if should_follow_up:
        follow_up_q = _generate_follow_up(answer, session)
        if follow_up_q:
            session["in_follow_up"] = True
            session["follow_ups"][session["current"]] = follow_up_q
            filename = make_audio(follow_up_q)
            return {
                "question":        follow_up_q,
                "question_number": session["current"] + 1,
                "total_questions": len(session["questions"]),
                "audio":           f"http://127.0.0.1:8000/audio/{filename}",
                "is_follow_up":    True,
                "follow_up_reason":"AI wants to dig deeper into your answer",
            }

    session["current"] += 1
    if session["current"] >= len(session["questions"]):
        return _finish(session)
    return _ask_next(session)


def _should_follow_up(answer: str, session: dict) -> bool:
    if session["difficulty"] == "easy": return False
    words = len(answer.split())
    if words < 20: return True
    vague_keywords = ["something","etc","and stuff","i think","maybe","probably","not sure"]
    return any(kw in answer.lower() for kw in vague_keywords)

def _generate_follow_up(answer: str, session: dict) -> str:
    prompt = f"""You are a strict technical interviewer.
The candidate just answered: "{answer[:500]}"

Generate ONE sharp follow-up question to probe deeper or challenge a vague point.
Rules:
- Only the question, no intro text
- Be direct and challenging
- Under 30 words"""
    try:
        return call_llm(prompt).strip()
    except:
        return ""

def _ask_next(session: dict) -> dict:
    nxt      = session["questions"][session["current"]]
    filename = make_audio(nxt)
    return {
        "question":        nxt,
        "question_number": session["current"] + 1,
        "total_questions": len(session["questions"]),
        "audio":           f"http://127.0.0.1:8000/audio/{filename}",
        "is_follow_up":    False,
    }

def _finish(session: dict) -> dict:
    import time
    duration = int(time.time() - session.get("start_time", time.time()))
    session["duration"] = duration
    return generate_feedback(session)


# ─────────────────────────────────────────────────────────────
# GENERATE FEEDBACK
# ─────────────────────────────────────────────────────────────
def generate_feedback(session: dict):
    qa = ""
    for i, (q, a) in enumerate(zip(session["questions"], session["answers"]), 1):
        qa += f"\nQ{i}: {q}\nA{i}: {a}\n"
        fu = session["follow_ups"].get(i-1)
        if fu:
            qa += f"Follow-up: {fu}\nFollow-up Answer: {session.get('follow_up_answer','N/A')}\n"

    total_fillers  = sum(session["filler_counts"])
    all_answers    = " ".join(session["answers"])
    speaking_speed = estimate_speaking_speed(all_answers, session.get("duration", 120))

    prompt = f"""You are a senior technical interviewer. Evaluate this interview.

Role: {session["role"]}
Skills: {session["skills"]}
Experience: {session["experience_level"]}{f" ({session['years_of_experience']} yrs)" if session["experience_level"]=="experienced" else ""}
Difficulty: {session["difficulty"]}
Skill gaps identified: {session.get("skill_gaps",[])}

Interview Q&A:
{qa}

Communication notes:
- Filler words used: {total_fillers} times
- Speaking speed: {speaking_speed}

Return ONLY valid JSON (no markdown, no backticks):
{{
  "overall_score": <1-10>,
  "verdict": "<Excellent|Good|Average|Below Average|Poor>",
  "summary": "<2-3 sentence assessment>",
  "communication_score": <1-10>,
  "confidence_score": <1-10>,
  "technical_score": <1-10>,
  "strengths":    ["<point>"],
  "weaknesses":   ["<point>"],
  "skill_gaps":   ["<gap>"],
  "improvements": ["<tip>"],
  "question_scores": [{{"q":"<short q>","score":<1-10>,"feedback":"<one line>"}}],
  "hire_recommendation": "<Strong Yes|Yes|Maybe|No>",
  "next_steps": "<next step>",
  "filler_words_count": {total_fillers},
  "speaking_speed": "{speaking_speed}",
  "career_path": ["<step1>","<step2>","<step3>","<step4>","<step5>"]
}}"""

    raw = call_llm(prompt)
    try:
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"): clean = clean[4:]
        feedback = json.loads(clean.strip())
    except:
        feedback = {
            "overall_score":5,"verdict":"Average","summary":raw,
            "communication_score":5,"confidence_score":5,"technical_score":5,
            "strengths":[],"weaknesses":[],"skill_gaps":[],"improvements":[],
            "question_scores":[],"hire_recommendation":"Maybe",
            "next_steps":"Keep practising.",
            "filler_words_count": total_fillers,
            "speaking_speed": speaking_speed,
            "career_path": [],
        }

    feedback["filler_words_count"] = total_fillers
    feedback["speaking_speed"]     = speaking_speed

    spoken = (
        f"Interview complete! Your score is {feedback.get('overall_score',5)} out of 10. "
        f"Verdict: {feedback.get('verdict','Average')}. "
        f"{feedback.get('summary','')} "
        f"Next steps: {feedback.get('next_steps','')}"
    )
    filename = make_audio(spoken)

    return {
        "completed":     True,
        "feedback":      feedback,
        "audio":         f"http://127.0.0.1:8000/audio/{filename}",
        "session_meta":  session,
        "duration_secs": session.get("duration", 0),
    }


# ─────────────────────────────────────────────────────────────
# CAREER PATH
# ─────────────────────────────────────────────────────────────
def generate_career_path(skills: str, goal: str, experience_level: str) -> dict:
    prompt = f"""You are a world-class career coach and technical mentor.
Create a detailed, actionable career roadmap for this candidate.

Current skills: {skills}
Career goal: {goal}
Experience level: {experience_level}

Return ONLY valid JSON (no markdown, no backticks, no explanation):
{{
  "title": "<specific descriptive path title>",
  "timeline": "<estimated realistic timeline>",
  "steps": [
    {{
      "month": "1-2",
      "action": "<detailed specific action to take>",
      "skill": "<specific skill or technology to learn>",
      "youtube_searches": ["<YouTube search query 1>", "<YouTube search query 2>"],
      "docs_links": [
        {{"label": "<site name>", "url": "<real working URL of official docs or free course>"}},
        {{"label": "<site name>", "url": "<real working URL>"}}
      ],
      "project_idea": "<a small hands-on project to build this skill>"
    }},
    {{
      "month": "3-4",
      "action": "<detailed specific action>",
      "skill": "<skill>",
      "youtube_searches": ["<query 1>", "<query 2>"],
      "docs_links": [
        {{"label": "<site name>", "url": "<real URL>"}},
        {{"label": "<site name>", "url": "<real URL>"}}
      ],
      "project_idea": "<hands-on project idea>"
    }},
    {{
      "month": "5-6",
      "action": "<detailed action>",
      "skill": "<skill>",
      "youtube_searches": ["<query>"],
      "docs_links": [{{"label": "<site>", "url": "<url>"}}],
      "project_idea": "<project>"
    }},
    {{
      "month": "7-9",
      "action": "<detailed action>",
      "skill": "<skill>",
      "youtube_searches": ["<query>"],
      "docs_links": [{{"label": "<site>", "url": "<url>"}}],
      "project_idea": "<project>"
    }},
    {{
      "month": "10-12",
      "action": "<detailed action>",
      "skill": "<skill>",
      "youtube_searches": ["<query>"],
      "docs_links": [{{"label": "<site>", "url": "<url>"}}],
      "project_idea": "<project>"
    }}
  ],
  "missing_skills": ["<skill1>", "<skill2>", "<skill3>"],
  "recommended_roles": ["<specific job title 1>", "<specific job title 2>", "<specific job title 3>"],
  "salary_range": "<realistic salary range in INR and USD for the goal role>",
  "job_search_keywords": ["<keyword 1 for job search>", "<keyword 2>", "<keyword 3>"],
  "top_companies": ["<company1>", "<company2>", "<company3>", "<company4>", "<company5>"]
}}

IMPORTANT: Use real, working URLs for docs_links. Examples:
- Python: https://docs.python.org/3/
- NumPy: https://numpy.org/doc/
- TensorFlow: https://www.tensorflow.org/learn
- Coursera: https://www.coursera.org/
- freeCodeCamp: https://www.freecodecamp.org/
- MDN Web Docs: https://developer.mozilla.org/
- Fast.ai: https://course.fast.ai/
- Kaggle: https://www.kaggle.com/learn
- LeetCode: https://leetcode.com/
- HackerRank: https://www.hackerrank.com/
- CS50: https://cs50.harvard.edu/

For youtube_searches, write search queries that will find real tutorials (e.g., "Python for beginners full course freeCodeCamp").
"""
    raw = call_llm(prompt)
    try:
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"): clean = clean[4:]
        return json.loads(clean.strip())
    except:
        return {"error": "Could not generate career path", "raw": raw}
