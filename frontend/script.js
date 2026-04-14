// ═══════════════════════════════════════════════════════
//  IQ — script.js  (Final — All bugs fixed)
//
//  BUG FIXES:
//  1. Interview page (#pg-iv) no longer shows through other pages
//     — CSS fix: display:none / display:grid (not !important)
//  2. Mic/Submit buttons guarded — only work if user is logged in
//     and an active session exists
//  3. "Learn More" → goes to Services page, not interview
//  4. About/Home nav → correct page, not interview
//  5. Interview page only reachable after login + session start
// ═══════════════════════════════════════════════════════

/* ── STATE ─────────────────────────────────────────── */
let user    = JSON.parse(localStorage.getItem("iq_user") || "null");
let theme   = localStorage.getItem("iq_theme") || "dark";

// Single-device enforcement: token is stored locally and sent with every request.
// If another device logs in, the token rotates and this session gets a 401.
function getToken() { return user ? (user.session_token || "") : ""; }

// Intercept 401 anywhere — log user out immediately
async function apiFetch(url, opts = {}) {
  const res = await fetch(url, opts);
  if (res.status === 401) {
    user = null;
    localStorage.removeItem("iq_user");
    setAuthUI(false);
    toast("You were signed in on another device. Please log in again.", "err");
    showPage("pg-login");
    throw new Error("401 — session invalidated");
  }
  return res;
}

let sessionId = "", currentQ = 0, totalQ = 0;
let expLevel = "fresher", difficulty = "easy", cpExp = "fresher";
let isRec = false, mediaRec = null, chunks = [];
let curAudio = null, recognition = null;
let camOn = true, camStream = null;
let timerSecs = 0, timerInt = null, wavInt = null;
let captFinal = "", ratingVal = 0, ratingAspects = [];
let lastFeedback = null, ivStartTime = 0;

const TIPS = [
  "Structure answers using STAR: Situation, Task, Action, Result.",
  "Quantify your impact — numbers make answers memorable.",
  "Pause briefly before answering to collect your thoughts.",
  "Relate every answer directly to the role requirements.",
  "If uncertain, walk through your reasoning rather than guessing.",
  "For system design: clarify requirements before proposing solutions.",
  "State the trade-offs of every technical decision you describe.",
  "Demonstrate enthusiasm — energy is noticed in every interview.",
  "Ask a clarifying question when the prompt is ambiguous.",
];

/* ── INIT ───────────────────────────────────────────── */
window.addEventListener("load", () => {
  applyTheme(theme);
  initSpeech();
  buildWavBars();

  if (user) {
    setAuthUI(true);
    showPage("pg-dash");
    loadDashboard();
  } else {
    setAuthUI(false);
    showPage("pg-land");
  }
});

/* ── PAGE ROUTING ───────────────────────────────────── */
/**
 * showPage: switches which page is visible.
 * The interview page (#pg-iv) uses display:grid when active,
 * all others use display:flex. The CSS handles this via:
 *   .page { display:none }
 *   .page.active { display:flex }
 *   #pg-iv { display:none }
 *   #pg-iv.active { display:grid }
 * So we just toggle .active and it works.
 */
function showPage(id) {
  document.querySelectorAll(".page").forEach(p => {
    p.classList.remove("active");
  });
  const pg = document.getElementById(id);
  if (!pg) return;
  pg.classList.add("active");
  window.scrollTo({ top: 0, behavior: "instant" });

  // Scroll the page element itself to top too
  if (pg.scrollTop !== undefined) pg.scrollTop = 0;
}

/**
 * navTo: public navigation function — guards protected pages.
 * Protected pages (dash, setup, career) require login.
 * Interview page (#pg-iv) is NOT directly navigable — only
 * reachable by completing startInterview() flow.
 */
function navTo(id) {
  const protected_pages = ["pg-dash", "pg-setup", "pg-career"];
  if (protected_pages.includes(id) && !user) {
    toast("Please sign in to access this feature", "err");
    showPage("pg-login");
    return;
  }
  // Prevent direct navigation to interview/feedback without a session
  if (id === "pg-iv" || id === "pg-fb") {
    if (!user) { toast("Please sign in first", "err"); showPage("pg-login"); return; }
    if (id === "pg-iv" && !sessionId) { toast("Please start an interview session first", "err"); showPage("pg-setup"); return; }
  }
  // Pre-fill support form with logged-in user details
  if (id === "pg-support" && user) {
    const n = document.getElementById("sup-name");
    const e = document.getElementById("sup-email");
    if (n && !n.value) n.value = user.name  || "";
    if (e && !e.value) e.value = user.email || "";
  }
  showPage(id);
}

function goHome() {
  navTo(user ? "pg-dash" : "pg-land");
}

/* ── AUTH UI ────────────────────────────────────────── */
function setAuthUI(loggedIn) {
  const els = {
    loginBtn:  document.getElementById("nav-login-btn"),
    signupBtn: document.getElementById("nav-signup-btn"),
    avatar:    document.getElementById("nav-avatar"),
    logout:    document.getElementById("nav-logout"),
    nlCareer:  document.getElementById("nl-career"),
    nlDash:    document.getElementById("nl-dash"),
  };

  if (loggedIn && user) {
    els.loginBtn  && (els.loginBtn.style.display  = "none");
    els.signupBtn && (els.signupBtn.style.display = "none");
    els.avatar?.classList.add("show");
    els.logout?.classList.add("show");
    els.nlCareer && (els.nlCareer.style.display = "");
    els.nlDash   && (els.nlDash.style.display   = "");
    if (els.avatar) {
      els.avatar.textContent        = user.name[0].toUpperCase();
      els.avatar.style.background   = user.avatar_color || "#4a7fff";
      els.avatar.style.color        = "#fff";
    }
  } else {
    els.loginBtn  && (els.loginBtn.style.display  = "");
    els.signupBtn && (els.signupBtn.style.display = "");
    els.avatar?.classList.remove("show");
    els.logout?.classList.remove("show");
    els.nlCareer && (els.nlCareer.style.display = "none");
    els.nlDash   && (els.nlDash.style.display   = "none");
  }
}

/* ── THEME ──────────────────────────────────────────── */
function applyTheme(t) {
  document.documentElement.setAttribute("data-theme", t);
  const btn = document.getElementById("theme-btn");
  if (btn) btn.textContent = t === "dark" ? "☀️" : "🌙";
}
function toggleTheme() {
  theme = theme === "dark" ? "light" : "dark";
  localStorage.setItem("iq_theme", theme);
  applyTheme(theme);
}

/* ── TOAST ──────────────────────────────────────────── */
function toast(msg, type = "ok") {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.className   = "toast show " + type;
  setTimeout(() => t.classList.remove("show"), 3600);
}
function esc(s) {
  return String(s || "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

/* ═══════════════════════════════════════════════════════
   AUTH
═══════════════════════════════════════════════════════ */
async function doRegister() {
  const name  = document.getElementById("r-name").value.trim();
  const email = document.getElementById("r-email").value.trim();
  const pass  = document.getElementById("r-pass").value;
  if (!name || !email || !pass) { toast("Please complete all fields", "err"); return; }
  if (pass.length < 6)          { toast("Password must be at least 6 characters", "err"); return; }

  const btn = document.getElementById("btn-reg");
  btn.disabled = true; btn.innerHTML = '<span class="spin"></span>';

  const fd = new FormData();
  fd.append("name", name); fd.append("email", email); fd.append("password", pass);

  try {
    const res  = await fetch("/api/register", { method: "POST", body: fd });
    const data = await res.json();
    if (!data.ok) { toast(data.error || "Registration failed", "err"); btn.disabled=false; btn.textContent="Create Account"; return; }
    user = data;
    localStorage.setItem("iq_user", JSON.stringify(user));
    setAuthUI(true);
    toast("Welcome to IQ, " + user.name + ".");
    showPage("pg-dash"); loadDashboard();
  } catch(e) {
    toast("Connection error — is the server running?", "err");
    btn.disabled=false; btn.textContent="Create Account";
  }
}

async function doLogin() {
  const email = document.getElementById("l-email").value.trim();
  const pass  = document.getElementById("l-pass").value;
  if (!email || !pass) { toast("Please complete all fields", "err"); return; }

  const btn = document.getElementById("btn-login");
  btn.disabled = true; btn.innerHTML = '<span class="spin"></span>';

  const fd = new FormData();
  fd.append("email", email); fd.append("password", pass);

  try {
    const res  = await fetch("/api/login", { method: "POST", body: fd });
    const data = await res.json();
    if (!data.ok) { toast(data.error || "Login failed", "err"); btn.disabled=false; btn.textContent="Sign In"; return; }
    user = data;
    localStorage.setItem("iq_user", JSON.stringify(user));
    setAuthUI(true);
    toast("Welcome back, " + user.name + ".");
    showPage("pg-dash"); loadDashboard();
  } catch(e) {
    toast("Connection error — is the server running?", "err");
    btn.disabled=false; btn.textContent="Sign In";
  }
}

async function doLogout() {
  if (user) {
    try {
      const fd = new FormData();
      fd.append("user_id", user.user_id);
      fd.append("token",   getToken());
      await fetch("/api/logout", { method: "POST", body: fd });
    } catch(e) {}
  }
  user = null; sessionId = "";
  localStorage.removeItem("iq_user");
  setAuthUI(false);
  toast("You have been signed out.");
  showPage("pg-land");
}

/* ═══════════════════════════════════════════════════════
   DASHBOARD
═══════════════════════════════════════════════════════ */
async function loadDashboard() {
  if (!user) return;

  document.getElementById("dash-name").textContent = "Welcome back, " + user.name;
  document.getElementById("dash-sub").textContent  = "Your performance at a glance";

  const av = document.getElementById("nav-avatar");
  if (av) { av.textContent = user.name[0].toUpperCase(); av.style.background = user.avatar_color || "#4a7fff"; av.style.color = "#fff"; }

  try {
    const res  = await apiFetch(`/api/dashboard/${user.user_id}?token=${encodeURIComponent(getToken())}`);
    const data = await res.json();
    if (data.error) return;

    document.getElementById("sc-total").textContent  = data.stats.total_interviews;
    document.getElementById("sc-avg").textContent    = data.stats.avg_score + " / 10";
    document.getElementById("sc-streak").textContent = data.streak.current;
    document.getElementById("sc-best").textContent   = data.stats.best_score + " / 10";
    document.getElementById("streak-num").textContent = data.streak.current;
    document.getElementById("streak-long").textContent = data.streak.longest;

    [["pb-comm","pv-comm",data.stats.avg_communication],["pb-conf","pv-conf",data.stats.avg_confidence],["pb-tech","pv-tech",data.stats.avg_technical],["pb-ov","pv-ov",data.stats.avg_score]].forEach(([b,v,val]) => {
      document.getElementById(b).style.width = (val*10)+"%";
      document.getElementById(v).textContent = val;
    });

    renderChart(data.trend);
    renderSkills(data.skill_data);
    renderHist(data.recent);
  } catch(e) { console.error("Dashboard error:", e); }
}

function renderChart(trend) {
  const el = document.getElementById("score-chart");
  if (!trend || trend.length === 0) return;
  el.innerHTML = trend.map(t => `
    <div class="c-bar-col">
      <div class="c-bar" style="height:${(t.score/10)*130}px" data-tip="${esc(t.role)}: ${t.score}/10"></div>
      <div class="c-lbl">${esc(t.date ? t.date.slice(5) : "")}</div>
    </div>`).join("");
}

function renderSkills(skills) {
  const el = document.getElementById("skill-perf");
  if (!skills || skills.length === 0) { el.innerHTML='<div style="color:var(--text3);font-size:.8rem">Practice more to see skill data</div>'; return; }
  el.innerHTML = skills.slice(0,5).map(s => `
    <div class="skill-row">
      <div class="skill-name">${esc(s.skill)}</div>
      <div class="skill-track"><div class="skill-fill" style="width:${s.score*10}%"></div></div>
      <div class="skill-val">${s.score}</div>
    </div>`).join("");
}

function renderHist(sessions) {
  const el = document.getElementById("hist-body");
  if (!sessions || sessions.length === 0) {
    el.innerHTML = '<div style="color:var(--text3);font-size:.85rem;text-align:center;padding:24px 0">No sessions yet. <a onclick="navTo(\'pg-setup\')" style="color:var(--gold);cursor:pointer;font-weight:500">Begin your first →</a></div>';
    return;
  }
  const vc = v => {
    const vl = (v||"").toLowerCase();
    return vl==="excellent"?"pill-teal":vl==="good"?"pill-gold":vl.includes("average")?"pill-muted":"pill-red";
  };
  el.innerHTML = `<table class="hist-table"><thead><tr>
    <th>Score</th><th>Role</th><th>Verdict</th><th>Level</th><th>Date</th>
  </tr></thead><tbody>` +
  sessions.map(s => `<tr>
    <td><div style="display:flex;align-items:center;gap:8px">
      <div class="ring-sm" style="--pct:${s.score*10}%"><span>${s.score}</span></div>
    </div></td>
    <td>${esc(s.role)}</td>
    <td><span class="pill ${vc(s.verdict)}">${esc(s.verdict)}</span></td>
    <td><span class="pill pill-muted">${esc(s.difficulty)}</span></td>
    <td style="color:var(--text3);font-size:.76rem">${esc(s.date)}</td>
  </tr>`).join("") + "</tbody></table>";
}

/* ═══════════════════════════════════════════════════════
   SETUP
═══════════════════════════════════════════════════════ */
function stab(id, btn) {
  document.querySelectorAll(".spane").forEach(p => p.classList.remove("on"));
  document.querySelectorAll(".stab").forEach(b => b.classList.remove("on"));
  document.getElementById("spane-"+id).classList.add("on");
  btn.classList.add("on");
}
function rvTab(id, btn) {
  document.querySelectorAll(".rv-pane").forEach(p => p.classList.remove("on"));
  document.querySelectorAll(".rv-tab").forEach(b => b.classList.remove("on"));
  document.getElementById("rvp-"+id).classList.add("on");
  btn.classList.add("on");
}
function setExp(val) {
  expLevel = val;
  document.getElementById("tgl-f").classList.toggle("on", val==="fresher");
  document.getElementById("tgl-e").classList.toggle("on", val==="experienced");
  const w = document.getElementById("years-wrap");
  val==="experienced" ? w.classList.add("show") : w.classList.remove("show");
}
function setDiff(val, el) {
  difficulty = val;
  document.querySelectorAll(".dbtn").forEach(b => b.classList.remove("e","m","h"));
  el.classList.add(val==="easy"?"e":val==="medium"?"m":"h");
}
function markFile(type, input) {
  if (!input.files[0]) return;
  document.getElementById(type+"-name").textContent = "✓ "+input.files[0].name;
  document.getElementById(type+"-zone").classList.add("ok");
}

/* ═══════════════════════════════════════════════════════
   START INTERVIEW
   Auth guard: user must be logged in to start an interview.
   Mic/Submit buttons are only enabled after this runs.
═══════════════════════════════════════════════════════ */
async function startInterview() {
  // GUARD: must be logged in
  if (!user) {
    toast("Please sign in to start an interview session", "err");
    showPage("pg-login");
    return;
  }

  const role   = document.getElementById("s-role").value.trim();
  const skills = document.getElementById("s-skills").value.trim();
  if (!role)   { toast("Please enter the job role", "err"); return; }
  if (!skills) { toast("Please enter required skills", "err"); return; }

  const btn = document.getElementById("btn-start-iv");
  btn.disabled = true; btn.innerHTML = '<span class="spin"></span>';
  document.getElementById("setup-status").textContent = "Generating your personalised questions…";

  const fd = new FormData();
  fd.append("role",               role);
  fd.append("skills",             skills);
  fd.append("experience_level",   expLevel);
  fd.append("years_of_experience",document.getElementById("sl-years").value);
  fd.append("difficulty",         difficulty);
  fd.append("num_questions",      document.getElementById("sl-nq").value);
  fd.append("jd_text",            document.getElementById("jd-text").value);
  fd.append("resume_text",        document.getElementById("res-text").value);
  fd.append("user_id",            user.user_id);
  fd.append("token",              getToken());

  const jdF  = document.getElementById("jd-file").files[0];
  const resF = document.getElementById("res-file").files[0];
  if (jdF)  fd.append("jd_file",     jdF);
  if (resF) fd.append("resume_file", resF);

  try {
    const res  = await fetch("/start-interview/", { method: "POST", body: fd });
    const data = await res.json();

    if (data.detail || data.error) {
      toast(data.detail || data.error, "err");
      btn.disabled=false; btn.textContent="Begin Interview Session";
      document.getElementById("setup-status").textContent="";
      return;
    }

    sessionId = data.session_id;
    totalQ    = data.total_questions;
    currentQ  = 1;
    ivStartTime = Date.now();

    // Show skill gaps
    if (data.skill_gaps && data.skill_gaps.length > 0) {
      document.getElementById("gap-banner").classList.remove("hide");
      document.getElementById("gap-tags").innerHTML = data.skill_gaps.map(g=>`<span class="gap-tag">${esc(g)}</span>`).join("");
    }

    // NOW navigate to interview page (only possible after session created)
    showPage("pg-iv");
    buildWavBars();
    startCamera(); startTimer(); buildQMap(totalQ);
    updateQ(data.question, 1, totalQ, false);

    const r = role.length>14 ? role.slice(0,14)+"…" : role;
    document.getElementById("si-role").textContent  = r;
    document.getElementById("si-exp").textContent   = expLevel==="experienced" ? `${document.getElementById("sl-years").value}y` : "Fresher";
    document.getElementById("si-diff").textContent  = difficulty;
    document.getElementById("si-total").textContent = totalQ+" Q";
    document.getElementById("si-jd").textContent    = (jdF||document.getElementById("jd-text").value) ? "Yes" : "No";
    document.getElementById("si-res").textContent   = (resF||document.getElementById("res-text").value) ? "Yes" : "No";

    // Enable mic now (was disabled before session)
    document.getElementById("mic-btn").disabled = false;

    setTimeout(() => playAudio(data.audio), 500);
    toast("Session started. Good luck.");

  } catch(e) {
    console.error(e);
    toast("Connection error — is uvicorn running?", "err");
    btn.disabled=false; btn.textContent="Begin Interview Session";
    document.getElementById("setup-status").textContent="";
  }
}

/* ── SPEECH RECOGNITION ─────────────────────────────── */
function initSpeech() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return;
  recognition = new SR();
  recognition.continuous = true; recognition.interimResults = true; recognition.lang = "en-US";
  recognition.onresult = (event) => {
    let interim = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      if (event.results[i].isFinal) {
        captFinal += event.results[i][0].transcript + " ";
        const ta = document.getElementById("ans-ta");
        if (ta) ta.value = captFinal.trim();
      } else { interim += event.results[i][0].transcript; }
    }
    renderCap(captFinal, interim);
  };
  recognition.onerror = e => { if (e.error!=="no-speech"&&e.error!=="aborted") console.warn(e.error); };
  recognition.onend   = () => { if (isRec) { try { recognition.start(); } catch(e){} } };
}

function renderCap(final, interim) {
  const el = document.getElementById("cap-body");
  if (!el) return;
  el.innerHTML = `<span class="fin">${esc(final)}</span>${interim?`<span class="int"> ${esc(interim)}</span>`:""}`;
  el.scrollTop = el.scrollHeight;
}

/* ── MIC TOGGLE ─────────────────────────────────────── */
async function toggleMic() {
  // GUARD: interview must be active
  if (!sessionId) { toast("No active interview session", "err"); return; }
  if (!isRec) await startRec(); else stopRec();
}

async function startRec() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    chunks = [];
    const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus"
               : MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "audio/wav";
    mediaRec = new MediaRecorder(stream, { mimeType: mime });
    mediaRec.ondataavailable = e => { if (e.data.size > 0) chunks.push(e.data); };
    mediaRec.start(250);

    isRec = true; captFinal = ""; renderCap("","");
    const ta = document.getElementById("ans-ta"); if (ta) ta.value = "";

    if (recognition) { try { recognition.start(); } catch(e){} }

    // NOTE: Video recording is NOT restarted here.
    // It runs continuously for the full session (started in startCamera).
    // Only mic audio is handled here.

    const btn = document.getElementById("mic-btn");
    btn.classList.add("active","off"); btn.textContent = "■";
    document.getElementById("cap-dot").style.background = "var(--green)";
    animWav(true); setIvStatus("Recording…");
    document.getElementById("btn-submit").disabled = false;
    toast("Recording. Speak clearly.");
  } catch(e) { toast("Microphone access denied", "err"); }
}

function stopRec() {
  isRec = false;
  if (recognition)  { try { recognition.stop(); } catch(e){} }
  if (mediaRec && mediaRec.state !== "inactive") mediaRec.stop();
  renderCap(captFinal, "");
  const btn = document.getElementById("mic-btn");
  btn.classList.remove("active","off"); btn.textContent = "◉";
  document.getElementById("cap-dot").style.background = "var(--text3)";
  animWav(false); setIvStatus("Answer recorded");
}

/* ── SUBMIT ANSWER ──────────────────────────────────── */
async function submitAnswer() {
  // GUARD
  if (!sessionId) { toast("No active interview session", "err"); return; }
  if (!user)      { toast("Please sign in first", "err"); return; }
  if (isRec) stopRec();
  if (chunks.length === 0 && captFinal.trim() === "") { toast("Please record your answer first", "err"); return; }

  const btn = document.getElementById("btn-submit");
  btn.disabled = true; btn.innerHTML = '<span class="spin"></span>';
  setIvStatus("Processing…");

  const dot = document.getElementById("qdot-"+currentQ);
  if (dot) { dot.classList.remove("cur"); dot.classList.add("done"); }

  try {
    const mime = chunks.length > 0 ? (chunks[0].type || "audio/webm") : "audio/webm";
    const ext  = mime.includes("webm") ? "webm" : mime.includes("ogg") ? "ogg" : "wav";
    const blob = chunks.length > 0 ? new Blob(chunks, {type:mime}) : new Blob([], {type:"audio/webm"});

    const fd = new FormData();
    fd.append("session_id", sessionId);
    fd.append("file", blob, `ans.${ext}`);

    const res  = await fetch("/next-question/", { method: "POST", body: fd });
    const data = await res.json();

    if (data.error) { toast(data.error, "err"); btn.disabled=false; btn.textContent="Submit Answer"; setIvStatus("Error"); return; }

    chunks = []; captFinal = "";

    if (data.completed) {
      clearInterval(timerInt);
      const dur = Math.round((Date.now() - ivStartTime) / 1000);
      if (user && data.feedback) {
        const fd2 = new FormData();
        fd2.append("user_id",       user.user_id);
        fd2.append("session_id",    sessionId);
        fd2.append("feedback_json", JSON.stringify(data.feedback));
        fd2.append("duration_secs", dur);
        fd2.append("token",         getToken());
        // Save interview, then reload dashboard data so count updates
        fetch("/api/save-interview", { method:"POST", body:fd2 })
          .then(() => loadDashboard())   // ← refresh dashboard session count
          .catch(()=>{});
        // Auto-take a final screenshot at interview end
        takeScreenshot(sessionId).catch(()=>{});
        // Save any pending video recording
        stopVideoRecording(sessionId).catch(()=>{});
      }
      lastFeedback = data.feedback;
      sessionId = ""; // clear session — interview is over
      setTimeout(() => playAudio(data.audio), 800);
      showFeedback(data.feedback, data.duration_secs || dur);
    } else {
      currentQ++;
      const nd = document.getElementById("qdot-"+currentQ);
      if (nd) nd.classList.add("cur");
      updateQ(data.question, data.question_number, data.total_questions, data.is_follow_up);
      setTimeout(() => playAudio(data.audio), 500);
      btn.disabled=false; btn.textContent="Submit Answer";
      setIvStatus(data.is_follow_up ? "Follow-up question" : "Next question");
      renderCap("","");
      const ta = document.getElementById("ans-ta"); if (ta) ta.value = "";
      toast(data.is_follow_up ? "AI wants to dig deeper." : "Next question ready.");
    }
  } catch(e) {
    console.error(e); toast("Network error — check uvicorn", "err");
    btn.disabled=false; btn.textContent="Submit Answer";
  }
}

/* ── HELPERS ────────────────────────────────────────── */
function updateQ(text, num, total, isFollowUp) {
  document.getElementById("iv-q-text").textContent = text;
  document.getElementById("qbox-num").textContent  = `Q${num}`;
  const pct = Math.round((num/total)*100);
  document.getElementById("iv-prog").style.width  = pct+"%";
  document.getElementById("iv-prog-lbl").textContent = `${num} / ${total}`;
  document.getElementById("iv-tip").textContent = TIPS[(num-1)%TIPS.length];
  const chip = document.getElementById("qbox-chip");
  chip.textContent = isFollowUp ? "Follow-Up Question" : "AI Interviewer";
  chip.classList.toggle("fu", !!isFollowUp);
}
function buildQMap(n) {
  const map = document.getElementById("iv-q-map"); map.innerHTML = "";
  for (let i=1; i<=n; i++) {
    const d = document.createElement("div");
    d.className = "qdot"+(i===1?" cur":""); d.id="qdot-"+i; d.textContent=i;
    map.appendChild(d);
  }
}
function setIvStatus(msg) { const el=document.getElementById("iv-status"); if(el) el.textContent=msg; }
function startTimer() {
  timerSecs=0; clearInterval(timerInt);
  timerInt = setInterval(() => {
    timerSecs++;
    const m=String(Math.floor(timerSecs/60)).padStart(2,"0");
    const s=String(timerSecs%60).padStart(2,"0");
    document.getElementById("iv-clock").textContent = m+":"+s;
  }, 1000);
}
function buildWavBars() {
  const wrap = document.getElementById("wav-bars"); if (!wrap) return;
  wrap.innerHTML = "";
  for (let i=0; i<16; i++) { const b=document.createElement("div"); b.className="wb"; b.id="wb"+i; wrap.appendChild(b); }
}
function animWav(on) {
  clearInterval(wavInt);
  if (on) {
    wavInt = setInterval(() => {
      for (let i=0; i<16; i++) { const b=document.getElementById("wb"+i); if(!b)continue; b.style.height=(Math.random()*18+3)+"px"; b.classList.add("lit"); }
    }, 75);
  } else {
    for (let i=0; i<16; i++) { const b=document.getElementById("wb"+i); if(!b)continue; b.style.height="4px"; b.classList.remove("lit"); }
  }
}
async function startCamera() {
  try {
    camStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
    document.getElementById("camera").srcObject = camStream;
    camOn = true;
    // ✅ FIX: Start video recording ONCE for the full session
    // It runs continuously across ALL questions — stops only when interview ends
    startVideoRecording();
    console.log("[Video] Full-session recording started");
  } catch(e) { console.warn("Camera unavailable:", e); }
}
function toggleCam() {
  if (!camStream) return; camOn=!camOn;
  camStream.getVideoTracks().forEach(t => t.enabled=camOn);
  document.getElementById("cam-btn").textContent = camOn ? "⬡" : "✕";
}
function playAudio(url) {
  if (!url) return;
  // Convert relative URL → absolute so Railway domain works
  // interview.py returns /audio/filename.mp3 — this makes it work on any domain
  if (url.startsWith("/")) url = window.location.origin + url;

  if (curAudio) { try { curAudio.pause(); curAudio.src = ""; } catch(e) {} }
  curAudio = new Audio(url);
  curAudio.preload = "auto";

  const orb = document.getElementById("ai-orb");
  if (orb) { orb.classList.add("speaking"); curAudio.onended = () => orb.classList.remove("speaking"); }

  curAudio.play().catch(err => {
    console.warn("[Audio] Autoplay blocked:", err.message);
    // Show tap-to-play hint when browser blocks autoplay (common on mobile/HTTPS)
    const hint = document.getElementById("audio-hint");
    if (hint) {
      hint.style.display = "flex";
      hint.onclick = () => {
        curAudio.play().catch(() => {});
        hint.style.display = "none";
      };
    }
  });
}
function endInterview() {
  if (!confirm("End this session? Your progress in this session will be lost.")) return;
  clearInterval(timerInt); stopRec(); sessionId = ""; showPage("pg-setup");
}

/* ═══════════════════════════════════════════════════════
   FEEDBACK
═══════════════════════════════════════════════════════ */
function showFeedback(fb, duration) {
  showPage("pg-fb");
  const score = fb.overall_score ?? 5;
  document.getElementById("fb-score").textContent = score;
  document.getElementById("fb-ring").style.setProperty("--pct", Math.round((score/10)*100)+"%");

  const v   = (fb.verdict || "Average").toLowerCase();
  const vEl = document.getElementById("fb-verdict");
  vEl.textContent = fb.verdict || "Average";
  vEl.className   = "verdict "+(v==="excellent"?"v-ex":v==="good"?"v-go":v.includes("average")?"v-av":"v-po");

  document.getElementById("fb-summary").textContent = fb.summary||"";
  document.getElementById("fb-comm").textContent    = (fb.communication_score??5)+"/10";
  document.getElementById("fb-conf").textContent    = (fb.confidence_score??5)+"/10";
  document.getElementById("fb-tech").textContent    = (fb.technical_score??5)+"/10";
  document.getElementById("va-fil").textContent     = fb.filler_words_count ?? 0;
  document.getElementById("va-spd").textContent     = fb.speaking_speed ?? "Normal";
  const mins=Math.floor((duration||0)/60), secs=(duration||0)%60;
  document.getElementById("va-dur").textContent     = `${mins}m ${secs}s`;

  const gaps = fb.skill_gaps || [];
  if (gaps.length > 0) {
    document.getElementById("fb-gap-banner").classList.remove("hide");
    document.getElementById("fb-gap-tags").innerHTML = gaps.map(g=>`<span class="gap-tag">${esc(g)}</span>`).join("");
  }

  rl("fb-str", fb.strengths   ||[], "li-s");
  rl("fb-wk",  fb.weaknesses  ||[], "li-w");
  rl("fb-gap", fb.skill_gaps  ||[], "li-g");
  rl("fb-imp", fb.improvements||[], "li-i");

  const qs = document.getElementById("fb-qs"); qs.innerHTML = "";
  (fb.question_scores||[]).forEach((item,i) => {
    const sc=item.score??5;
    const col=sc>=8?"var(--teal)":sc>=5?"var(--gold)":"var(--red)";
    const bg =sc>=8?"rgba(20,184,166,.08)":sc>=5?"rgba(201,168,76,.08)":"rgba(239,68,68,.08)";
    qs.innerHTML += `<div class="qs-item"><div class="qs-top"><div class="qs-q">Q${i+1}: ${esc(item.q||"")}</div><div class="qs-badge" style="color:${col};background:${bg}">${sc}/10</div></div><div class="qs-fb">${esc(item.feedback||"")}</div></div>`;
  });

  const hire  = fb.hire_recommendation || "Maybe";
  const hireEl = document.getElementById("fb-hire");
  hireEl.textContent = hire;
  hireEl.className   = "hire-pill "+(hire.toLowerCase().includes("yes")?"hp-y":hire.toLowerCase()==="no"?"hp-n":"hp-m");
  document.getElementById("fb-next").textContent = fb.next_steps||"";

  const cp = fb.career_path || [];
  document.getElementById("fb-career-steps").innerHTML = cp.slice(0,4).map((step,i) => `
    <div class="cp-step"><div class="cp-num">${i+1}</div><div class="cp-txt">${esc(step)}</div></div>`).join("") || '<div style="color:var(--text3);font-size:.82rem">Generate your full roadmap below.</div>';

  ratingVal=0; ratingAspects=[];
  document.querySelectorAll(".star").forEach(s=>s.classList.remove("lit"));
  document.querySelectorAll(".asp-item").forEach(a=>a.classList.remove("on"));
  document.getElementById("rating-comment").value = "";
  document.getElementById("rate-thanks").classList.remove("show");
}

function rl(id, items, cls) {
  document.getElementById(id).innerHTML = items.length
    ? items.map(i=>`<li class="${cls}">${esc(i)}</li>`).join("")
    : `<li style="color:var(--text3);font-size:.8rem">—</li>`;
}

function shareScore() {
  const sc   = lastFeedback ? lastFeedback.overall_score : "?";
  const v    = lastFeedback ? lastFeedback.verdict : "";
  const text = `I scored ${sc}/10 (${v}) on my AI mock interview at IQ — Elite Interview Intelligence.\n\nIQ uses adaptive AI to conduct realistic interview sessions with intelligent follow-up questions, skill gap detection, and deep structured feedback.\n\nTry it free: https://iqinterview.ai\n#IQ #InterviewPrep #CareerGrowth`;
  window.open(`https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent("https://hireiq.ai")}&summary=${encodeURIComponent(text)}`, "_blank");
  toast("Opening LinkedIn share…");
}

/* ── RATING ─────────────────────────────────────────── */
function rateStar(n) {
  ratingVal = n;
  document.querySelectorAll(".star").forEach((s,i) => s.classList.toggle("lit", i<n));
}
function toggleAspect(el, key) {
  el.classList.toggle("on");
  ratingAspects.includes(key) ? ratingAspects=ratingAspects.filter(k=>k!==key) : ratingAspects.push(key);
}
async function submitRating() {
  if (!ratingVal) { toast("Please select a star rating first", "err"); return; }
  const btn = document.getElementById("btn-rate");
  if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spin"></span> Submitting…'; }

  const fd = new FormData();
  fd.append("user_id", user ? user.user_id : 0);
  fd.append("email",   user ? user.email   : "");
  fd.append("stars",   ratingVal);
  fd.append("aspects", ratingAspects.join(","));
  fd.append("comment", document.getElementById("rating-comment").value.trim());

  try {
    const res  = await fetch("/api/rating", { method:"POST", body:fd });
    const data = await res.json();
    if (data.ok) {
      document.getElementById("rate-thanks").classList.add("show");
      toast("⭐ Thank you! Your feedback has been sent.");
    } else {
      toast("Could not submit feedback. Please try again.", "err");
    }
  } catch(e) {
    console.error("Rating submit error:", e);
    toast("Network error submitting feedback.", "err");
  }
  if (btn) { btn.disabled = false; btn.textContent = "Submit Feedback"; }
}

/* ── SUPPORT FORM ───────────────────────────────────── */
async function submitSupport() {
  const name    = document.getElementById("sup-name")    ? document.getElementById("sup-name").value.trim()    : (user ? user.name  : "");
  const email   = document.getElementById("sup-email")   ? document.getElementById("sup-email").value.trim()   : (user ? user.email : "");
  const subject = document.getElementById("sup-subject") ? document.getElementById("sup-subject").value.trim() : "";
  const message = document.getElementById("sup-message") ? document.getElementById("sup-message").value.trim() : "";

  if (!name)    { toast("Please enter your name", "err"); return; }
  if (!email)   { toast("Please enter your email", "err"); return; }
  if (!message) { toast("Please enter a message", "err"); return; }

  const btn = document.getElementById("btn-support");
  if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spin"></span> Sending…'; }

  const fd = new FormData();
  fd.append("user_id", user ? user.user_id : 0);
  fd.append("name",    name);
  fd.append("email",   email);
  fd.append("subject", subject || "Support Request");
  fd.append("message", message);

  try {
    const res  = await fetch("/api/support", { method: "POST", body: fd });
    const data = await res.json();
    if (data.ok) {
      // Clear all fields
      ["sup-name","sup-email","sup-subject","sup-message"].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = "";
      });

      // Show success notification in UI
      const successEl = document.getElementById("support-success");
      if (successEl) {
        successEl.style.display = "block";
        setTimeout(() => { successEl.style.display = "none"; }, 6000);
      }

      toast(`✓ Support ticket #${data.ticket_id} submitted! Check your email for confirmation.`, "ok");
    } else {
      toast("Could not submit. Please try again or email us directly.", "err");
    }
  } catch(e) {
    console.error("Support submit error:", e);
    toast("Network error — please check your connection.", "err");
  }
  if (btn) { btn.disabled = false; btn.textContent = "Send Message"; }
}

/* ═══════════════════════════════════════════════════════
   CAREER PATH — with resource links + job board
═══════════════════════════════════════════════════════ */
function setCpExp(val, el) {
  cpExp = val;
  document.getElementById("cp-f").classList.toggle("on", val==="fresher");
  document.getElementById("cp-e").classList.toggle("on", val==="experienced");
}

async function generateCareerPath() {
  const skills = document.getElementById("cp-skills").value.trim();
  const goal   = document.getElementById("cp-goal").value.trim();
  if (!skills || !goal) { toast("Please enter your skills and career goal", "err"); return; }

  const btn = document.getElementById("btn-cp");
  btn.disabled = true; btn.innerHTML = '<span class="spin"></span> Generating your roadmap…';

  const fd = new FormData();
  fd.append("skills", skills); fd.append("goal", goal); fd.append("experience_level", cpExp);

  try {
    const res  = await fetch("/api/career-path", { method:"POST", body:fd });
    const data = await res.json();
    if (data.error) { toast("Could not generate roadmap", "err"); btn.disabled=false; btn.textContent="Generate My Roadmap"; return; }

    document.getElementById("cp-result").style.display = "";
    document.getElementById("cp-title").textContent    = data.title || "Your Career Roadmap";
    document.getElementById("cp-timeline").textContent = "Estimated timeline: "+(data.timeline||"12 months");
    document.getElementById("cp-salary").textContent   = data.salary_range || "—";
    document.getElementById("cp-missing").innerHTML    = (data.missing_skills||[]).map(s=>`<span class="gap-tag">${esc(s)}</span>`).join("");

    // ─── Render steps with YouTube + docs links ───────────────
    document.getElementById("cp-steps").innerHTML = (data.steps||[]).map((s,i,arr) => {
      // YouTube links
      const ytLinks = (s.youtube_searches||[]).map(q => {
        const url = `https://www.youtube.com/results?search_query=${encodeURIComponent(q)}`;
        return `<a href="${url}" target="_blank" rel="noopener" class="res-link yt">▶ ${esc(q)}</a>`;
      }).join("");

      // Documentation / course links
      const docLinks = (s.docs_links||[]).map(d => {
        return `<a href="${esc(d.url||'#')}" target="_blank" rel="noopener" class="res-link doc">📖 ${esc(d.label||d.url)}</a>`;
      }).join("");

      // Project idea
      const project = s.project_idea
        ? `<div class="road-project">${esc(s.project_idea)}</div>`
        : "";

      return `
      <div class="road-step">
        <div class="road-line">
          <div class="road-dot">${i+1}</div>
          ${i<arr.length-1?'<div class="road-connector"></div>':""}
        </div>
        <div class="road-content">
          <div class="road-month">${esc(s.month||"")}</div>
          <div class="road-action">${esc(s.action||"")}</div>
          <div class="road-skill" style="font-size:.82rem;color:var(--text2);margin-top:5px">
            <strong>Learn:</strong> ${esc(s.skill||"")}
          </div>
          <div class="road-resource-row">${ytLinks}${docLinks}</div>
          ${project}
        </div>
      </div>`;
    }).join("");

    // ─── Target roles ─────────────────────────────────────────
    document.getElementById("cp-roles").innerHTML = (data.recommended_roles||[]).map(r =>
      `<div style="padding:9px 0;border-bottom:1px solid var(--border);font-size:.84rem;color:var(--text2);display:flex;align-items:center;gap:8px"><span style="color:var(--gold)">→</span>${esc(r)}</div>`
    ).join("");

    // ─── Job Board Section ────────────────────────────────────
    const keywords = data.job_search_keywords || [goal];
    const companies = data.top_companies || [];
    const primaryKw = keywords[0] || goal;

    // Platform search links
    const platforms = [
      { name:"LinkedIn",  icon:"💼", url:`https://www.linkedin.com/jobs/search/?keywords=${encodeURIComponent(primaryKw)}&f_TPR=r604800` },
      { name:"Naukri",    icon:"🏢", url:`https://www.naukri.com/${primaryKw.toLowerCase().replace(/\s+/g,'-')}-jobs` },
      { name:"Indeed",    icon:"🔍", url:`https://in.indeed.com/jobs?q=${encodeURIComponent(primaryKw)}` },
      { name:"Glassdoor", icon:"🌐", url:`https://www.glassdoor.co.in/Job/jobs.htm?suggestCount=0&suggestChosen=false&clickSource=searchBtn&typedKeyword=${encodeURIComponent(primaryKw)}&sc.keyword=${encodeURIComponent(primaryKw)}` },
      { name:"Internshala", icon:"🎓", url:`https://internshala.com/jobs/keyword/${encodeURIComponent(primaryKw)}` },
    ];

    document.getElementById("cp-platform-links").innerHTML = platforms.map(p =>
      `<a class="job-plt-btn" href="${p.url}" target="_blank" rel="noopener">${p.icon} ${p.name}</a>`
    ).join("");

    // Job cards — mix of role + top companies
    const jobEntries = [];
    (data.recommended_roles || [goal]).slice(0,3).forEach(role => {
      (companies.length ? companies.slice(0,2) : ["Top Companies"]).forEach(company => {
        jobEntries.push({ role, company });
      });
    });

    document.getElementById("cp-job-cards").innerHTML = jobEntries.slice(0,6).map(({ role, company }) => {
      const kw = encodeURIComponent(role);
      const companyKw = encodeURIComponent(company + " " + role);
      return `
        <div class="job-card">
          <div class="job-card-role">${esc(role)}</div>
          <div class="job-card-company">${esc(company)}</div>
          <div class="job-card-tags">
            ${keywords.slice(0,3).map(k=>`<span class="pill pill-muted" style="font-size:.66rem">${esc(k)}</span>`).join("")}
          </div>
          <div class="job-card-links">
            <a class="job-search-btn" href="https://www.linkedin.com/jobs/search/?keywords=${companyKw}" target="_blank" rel="noopener">💼 LinkedIn</a>
            <a class="job-search-btn" href="https://www.naukri.com/jobs-in-india?q=${kw}" target="_blank" rel="noopener">🏢 Naukri</a>
            <a class="job-search-btn" href="https://in.indeed.com/jobs?q=${companyKw}" target="_blank" rel="noopener">🔍 Indeed</a>
          </div>
        </div>`;
    }).join("");

    btn.disabled=false; btn.textContent="Generate My Roadmap";
    toast("Roadmap with resources & jobs generated!");
  } catch(e) {
    console.error(e); toast("Server error — check uvicorn", "err");
    btn.disabled=false; btn.textContent="Generate My Roadmap";
  }
}

/* ═══════════════════════════════════════════════════════
   SCREENSHOT — captures webcam frame + saves to server
   Black screen fix: wait for video readyState + use
   requestVideoFrameCallback or short delay before drawing.
═══════════════════════════════════════════════════════ */
async function takeScreenshot(sid) {
  if (!user) return;
  try {
    const video = document.getElementById("camera");
    if (!video) return;

    // Wait until video has actual frame data
    await new Promise((resolve) => {
      if (video.readyState >= 2 && video.videoWidth > 0) { resolve(); return; }
      const onReady = () => { video.removeEventListener("canplay", onReady); resolve(); };
      video.addEventListener("canplay", onReady);
      setTimeout(resolve, 2000); // fallback timeout
    });

    if (!video.videoWidth || !video.videoHeight) {
      console.warn("Screenshot: video has no dimensions, skipping");
      return;
    }

    const canvas = document.createElement("canvas");
    canvas.width  = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    // Verify canvas is not blank (check a center pixel)
    const pixel = ctx.getImageData(canvas.width >> 1, canvas.height >> 1, 1, 1).data;
    if (pixel[0] === 0 && pixel[1] === 0 && pixel[2] === 0 && pixel[3] === 255) {
      // Possibly a black frame — try once more after short delay
      await new Promise(r => setTimeout(r, 300));
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    }

    const blob = await new Promise(res => canvas.toBlob(res, "image/png"));
    if (!blob || blob.size < 1000) { console.warn("Screenshot: blank blob, skipping"); return; }

    const fd = new FormData();
    fd.append("user_id",    user.user_id);
    fd.append("session_id", sid || sessionId);
    fd.append("file_type",  "screenshot");
    fd.append("token",      getToken());
    fd.append("file",       blob, "screenshot.png");
    await fetch("/api/save-recording", { method: "POST", body: fd });
    console.log("Screenshot saved.");
  } catch(e) { console.warn("Screenshot failed:", e); }
}

/* ── Video recording — runs for the FULL SESSION ────── */
// ✅ FIX: videoChunks accumulates data for the ENTIRE interview
// startVideoRecording() is called ONCE in startCamera() and never restarted
let videoRecorder = null, videoChunks = [];

function startVideoRecording() {
  if (!camStream || (videoRecorder && videoRecorder.state !== "inactive")) return;
  videoChunks = [];
  try {
    // Video-only stream (audio answers are saved separately per question)
    const mime = MediaRecorder.isTypeSupported("video/webm;codecs=vp9")
      ? "video/webm;codecs=vp9"
      : MediaRecorder.isTypeSupported("video/webm")
      ? "video/webm"
      : "video/mp4";
    videoRecorder = new MediaRecorder(camStream, { mimeType: mime });
    // Collect chunks every 2s — all questions recorded continuously
    videoRecorder.ondataavailable = e => { if (e.data.size > 0) videoChunks.push(e.data); };
    videoRecorder.start(2000);
    console.log("[Video] Full-session recording — mime:", mime);
  } catch(e) { console.warn("[Video] Recording unavailable:", e); }
}

async function stopVideoRecording(sid) {
  if (!videoRecorder || videoRecorder.state === "inactive") return;
  return new Promise(resolve => {
    videoRecorder.onstop = async () => {
      if (!user || videoChunks.length === 0) { resolve(); return; }
      try {
        const blob = new Blob(videoChunks, { type: "video/webm" });
        if (blob.size < 1000) { resolve(); return; } // skip empty recordings
        const fd   = new FormData();
        fd.append("user_id",    user.user_id);
        fd.append("session_id", sid || sessionId);
        fd.append("file_type",  "video");
        fd.append("token",      getToken());
        fd.append("file",       blob, "interview.webm");
        await fetch("/api/save-recording", { method: "POST", body: fd });
        toast("Interview video saved to your account.");
      } catch(e) { console.warn("Video save failed:", e); }
      videoChunks = [];
      resolve();
    };
    videoRecorder.stop();
  });
}

/* ── startCamera — also begins video recording ─────── */
async function startCamera() {
  try {
    camStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
    document.getElementById("camera").srcObject = camStream;
    camOn = true;
    // Video recording starts without audio initially;
    // audio track is added when mic recording begins (see startRec)
    startVideoRecording(null);
  } catch(e) { console.warn("Camera unavailable:", e); }
}
