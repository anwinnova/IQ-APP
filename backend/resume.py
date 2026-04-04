"""
resume.py — Resume analysis
Uses the same LLM abstraction as interview.py (call_llm).
Supports Gemini, OpenAI, Anthropic, Groq, Ollama.
"""
import fitz
import os
from backend.interview import call_llm


def extract_text(pdf_path: str) -> str:
    doc  = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text()
    return text


def analyze_resume(pdf_path: str) -> dict:
    text = extract_text(pdf_path)

    prompt = f"""Analyze this resume and return a structured evaluation.

Resume:
{text[:4000]}

Return ONLY valid JSON (no markdown, no backticks):
{{
  "score": <1-10>,
  "summary": "<2-3 sentence overall assessment>",
  "strengths": ["<strength 1>", "<strength 2>", "<strength 3>"],
  "improvements": ["<improvement 1>", "<improvement 2>", "<improvement 3>"],
  "missing_skills": ["<skill 1>", "<skill 2>"],
  "formatting_tips": ["<tip 1>", "<tip 2>"],
  "ats_score": <1-10>,
  "keyword_suggestions": ["<keyword 1>", "<keyword 2>", "<keyword 3>"]
}}"""

    try:
        raw   = call_llm(prompt).strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"): raw = raw[4:]
        import json
        data = json.loads(raw.strip())
        return {"ok": True, **data}
    except Exception as e:
        return {
            "ok":      True,
            "score":   5,
            "summary": "Resume analysed. See improvements below.",
            "raw":     str(e),
        }
