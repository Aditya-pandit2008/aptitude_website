"""
services/ai_service.py
Groq AI integration service — uses the official Groq SDK.

Fix applied (2026-06-11):
    Replaced raw urllib HTTP calls with the official `groq` Python SDK.
    Raw urllib requests were blocked by Cloudflare (error 403 / code 1010)
    because they lacked the proper headers and TLS fingerprint that the
    SDK sets automatically.  Added retry-with-exponential-backoff so
    transient rate-limit or network errors recover automatically.

Provides:
    - explain_question             : step-by-step explanation of an aptitude question
    - generate_similar_questions   : generate N questions similar to a given one
    - generate_aptitude_questions  : adaptive questions based on difficulty/level
    - generate_study_plan          : personalised weekly study plan
    - generate_interview_questions : role-specific mock interview questions
"""

import json
import re
import time

from flask import current_app
from groq import Groq, APIStatusError, APIConnectionError, RateLimitError
from cachetools import TTLCache

# Caching instances
_explain_cache = None
_study_plan_cache = None

def _get_explain_cache():
    global _explain_cache
    if _explain_cache is None:
        ttl = current_app.config.get("AI_CACHE_TTL", 3600)
        maxsize = current_app.config.get("AI_CACHE_MAXSIZE", 256)
        _explain_cache = TTLCache(maxsize=maxsize, ttl=ttl)
    return _explain_cache

def _get_study_plan_cache():
    global _study_plan_cache
    if _study_plan_cache is None:
        ttl = current_app.config.get("AI_CACHE_TTL", 3600)
        maxsize = current_app.config.get("AI_CACHE_MAXSIZE", 256)
        _study_plan_cache = TTLCache(maxsize=maxsize, ttl=ttl)
    return _study_plan_cache


def _clean_input(text: str, max_chars: int = 500) -> str:
    """Clamp length and remove prompt injection patterns from user strings."""
    if not isinstance(text, str):
        return ""
    text = text[:max_chars]
    text = re.sub(r'system\s*:', '', text, flags=re.IGNORECASE)
    text = re.sub(r'ignore\s+previous', '', text, flags=re.IGNORECASE)
    text = text.replace('\n', ' ').replace('"""', '')
    return text.strip()


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_client() -> Groq:
    """Instantiate and return a Groq client using the configured API key."""
    api_key = current_app.config.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY is not configured.")
    return Groq(api_key=api_key)


def _chat(messages: list[dict], max_tokens: int = 1024,
          temperature: float = 0.7, retries: int = 3) -> str:
    """
    Call the Groq chat-completion endpoint via the official SDK and return
    the assistant reply. Retries on rate-limit and transient network errors.
    If the primary model fails with status error (e.g. 404), retries using the fallback model.
    """
    client = _get_client()
    model  = current_app.config.get("GROQ_MODEL", "llama-3.1-8b-instant")
    fallback_model = current_app.config.get("GROQ_FALLBACK_MODEL", "llama3-8b-8192")

    last_exc = None
    for current_model in [model, fallback_model]:
        if not current_model:
            continue
        for attempt in range(retries):
            try:
                response = client.chat.completions.create(
                    model=current_model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                return response.choices[0].message.content.strip()

            except RateLimitError as exc:
                wait = 2 ** attempt
                current_app.logger.warning(
                    "Groq rate-limited on model %s (attempt %d/%d). Retrying in %ds…",
                    current_model, attempt + 1, retries, wait,
                )
                last_exc = exc
                time.sleep(wait)

            except APIConnectionError as exc:
                wait = 2 ** attempt
                current_app.logger.warning(
                    "Groq connection error on model %s (attempt %d/%d): %s. Retrying in %ds…",
                    current_model, attempt + 1, retries, exc, wait,
                )
                last_exc = exc
                time.sleep(wait)

            except APIStatusError as exc:
                if current_model == model and fallback_model:
                    current_app.logger.warning(
                        "Groq primary model %s failed with status %d: %s. Trying fallback model %s.",
                        model, exc.status_code, exc.message, fallback_model
                    )
                    last_exc = exc
                    break
                else:
                    raise RuntimeError(
                        f"Groq API error {exc.status_code}: {exc.message}"
                    ) from exc
        else:
            if current_model == fallback_model:
                raise RuntimeError(f"Groq API failed after {retries} retries: {last_exc}") from last_exc


def _strip_json_fences(raw: str) -> str:
    """Remove markdown code fences that Groq sometimes wraps around JSON."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


def _salvage_json_array(raw: str) -> str | None:
    """
    Repair a JSON array that was cut off mid-object (e.g. the model hit its
    max_tokens limit before finishing). Trims back to the last fully-closed
    '}' and re-closes the array, so partial responses still yield whatever
    complete questions were generated instead of failing entirely.
    """
    last_close = raw.rfind("}")
    if last_close == -1:
        return None
    candidate = raw[: last_close + 1].rstrip().rstrip(",")
    if not candidate.startswith("["):
        candidate = "[" + candidate
    return candidate + "]"


# ─────────────────────────────────────────────────────────────────────────────
# Level-aware prompt helpers
# ─────────────────────────────────────────────────────────────────────────────

LEVEL_DESCRIPTIONS = {
    "easy":   "beginner — avoid algebra-heavy or multi-step problems; use simple numbers and direct logic",
    "medium": "intermediate — moderate complexity with 2-3 step reasoning or standard formulas",
    "hard":   "advanced — complex multi-step problems, tricky edge cases, high accuracy required",
}

def _difficulty_context(difficulty: str) -> str:
    return LEVEL_DESCRIPTIONS.get(difficulty.lower(), LEVEL_DESCRIPTIONS["medium"])


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def explain_question(question_text: str, options: list, correct_index: int,
                     category: str = "") -> str:
    """
    Generate a clear, step-by-step explanation for a given MCQ.
    """
    clean_text = _clean_input(question_text, max_chars=1000)
    clean_options = [_clean_input(str(opt), max_chars=200) for opt in options]
    clean_cat = _clean_input(category, max_chars=100)

    cache_key = (clean_text, tuple(clean_options), correct_index, clean_cat)
    cache = _get_explain_cache()
    if cache_key in cache:
        current_app.logger.info("Serving explain_question response from cache.")
        return cache[cache_key]

    correct_answer = clean_options[correct_index] if clean_options and correct_index < len(clean_options) else "N/A"
    options_str    = "\n".join(f"  {chr(65+i)}) {opt}" for i, opt in enumerate(clean_options))

    prompt = f"""You are an expert aptitude tutor. Explain the following {clean_cat} question clearly.

Question: {clean_text}

Options:
{options_str}

Correct Answer: {chr(65 + correct_index)}) {correct_answer}

Provide:
1. A brief concept introduction (2-3 sentences)
2. Step-by-step solution with calculations
3. Why the other options are incorrect
4. A memory tip or shortcut if applicable

Keep the explanation concise and student-friendly."""

    result = _chat([{"role": "user", "content": prompt}], max_tokens=800)
    cache[cache_key] = result
    return result


def generate_similar_questions(question_text: str, category: str,
                                difficulty: str, count: int = 3) -> list[dict]:
    """
    Generate 'count' MCQ questions similar to the provided one.
    """
    clean_text = _clean_input(question_text, max_chars=1000)
    clean_cat = _clean_input(category, max_chars=100)
    clean_diff = _clean_input(difficulty, max_chars=20)

    count   = min(count, 5)
    context = _difficulty_context(clean_diff)

    prompt = f"""Generate {count} multiple-choice aptitude questions similar to the one below.
Category: {clean_cat} | Difficulty: {clean_diff} ({context})

Reference question: {clean_text}

Return ONLY a valid JSON array (no markdown, no extra text) in this exact format:
[
  {{
    "text": "question text here",
    "options": ["Option A", "Option B", "Option C", "Option D"],
    "correct_option": 0,
    "explanation": "brief explanation"
  }}
]"""

    raw = _strip_json_fences(_chat([{"role": "user", "content": prompt}], max_tokens=1200))

    try:
        questions = json.loads(raw)
        if not isinstance(questions, list):
            raise ValueError("Expected a JSON array")
        return questions[:count]
    except (json.JSONDecodeError, ValueError) as exc:
        current_app.logger.warning("Groq returned malformed JSON: %s", exc)
        return []


def generate_aptitude_questions(category: str, difficulty: str,
                                 count: int = 10) -> list[dict]:
    """
    Generate fresh aptitude MCQs for a selected category and difficulty.
    """
    clean_cat = _clean_input(category or "Mixed Aptitude", max_chars=100)
    clean_diff = _clean_input(difficulty or "medium", max_chars=20).lower()

    count      = min(max(int(count or 10), 1), 15)
    context    = _difficulty_context(clean_diff)

    prompt = f"""Generate {count} placement aptitude multiple-choice questions for a student preparing for campus placements.

Topic: {clean_cat}
Difficulty Level: {clean_diff} — {context}

Rules:
- All questions must be directly relevant to the topic "{clean_cat}".
- Match difficulty strictly: {context}.
- Each question must have exactly 4 options labeled internally (not in the text).
- correct_option must be a 0-based integer (0, 1, 2, or 3).
- Explanations must be short, clear, and show the key step.
- Do NOT repeat questions or use trivial/obvious answers.
- For "easy": use simple direct problems a first-year student can solve in 30 seconds.
- For "medium": use problems requiring 2-3 steps or standard formulas.
- For "hard": use tricky multi-step problems with close/deceptive options.

Return ONLY a valid JSON array. No markdown fences. No extra text before or after.
Format:
[
  {{
    "text": "question text",
    "options": ["Option A", "Option B", "Option C", "Option D"],
    "correct_option": 0,
    "explanation": "brief step-by-step solution",
    "difficulty": "{clean_diff}",
    "category_name": "{clean_cat}"
  }}
]"""

    # Each question (text + 4 options + explanation + JSON overhead) needs
    # roughly 300-400 tokens. A fixed budget was too small for higher counts,
    # truncating the JSON mid-string and causing "Unterminated string" parse
    # errors. Scale with count instead, capped near the model's output limit.
    token_budget = min(400 * count + 500, 7800)
    raw = _strip_json_fences(
        _chat([{"role": "user", "content": prompt}], max_tokens=token_budget, temperature=0.75)
    )

    try:
        questions = json.loads(raw)
    except json.JSONDecodeError as exc:
        current_app.logger.warning(
            "Groq aptitude questions parse error: %s — attempting salvage", exc
        )
        salvaged = _salvage_json_array(raw)
        try:
            questions = json.loads(salvaged) if salvaged else None
        except json.JSONDecodeError:
            questions = None
        if questions is None:
            return []

    try:
        if not isinstance(questions, list):
            raise ValueError("Expected a JSON array")

        cleaned = []
        for item in questions[:count]:
            options = item.get("options", [])
            correct = item.get("correct_option")
            if not item.get("text") or not isinstance(options, list) or len(options) != 4:
                continue
            try:
                correct = int(correct)
            except (TypeError, ValueError):
                continue
            if correct < 0 or correct > 3:
                continue
            cleaned.append({
                "id":             f"ai-{len(cleaned) + 1}",
                "text":           item["text"].strip(),
                "options":        [str(o).strip() for o in options],
                "correct_option": correct,
                "explanation":    item.get("explanation", "").strip(),
                "difficulty":     item.get("difficulty", clean_diff),
                "category_name":  item.get("category_name", clean_cat),
                "source":         "groq",
            })
        return cleaned

    except (json.JSONDecodeError, ValueError) as exc:
        current_app.logger.warning("Groq aptitude questions parse error: %s", exc)
        return []


def generate_study_plan(weak_topics: list[str], strong_topics: list[str],
                         days: int = 7) -> str:
    """
    Generate a personalised study plan based on performance data.
    """
    clean_weak = [_clean_input(t, max_chars=80) for t in weak_topics]
    clean_strong = [_clean_input(t, max_chars=80) for t in strong_topics]

    cache_key = (tuple(clean_weak), tuple(clean_strong), days)
    cache = _get_study_plan_cache()
    if cache_key in cache:
        current_app.logger.info("Serving generate_study_plan response from cache.")
        return cache[cache_key]

    weak_str   = ", ".join(clean_weak)   if clean_weak   else "None identified yet"
    strong_str = ", ".join(clean_strong) if clean_strong else "None identified yet"

    prompt = f"""Create a structured {days}-day placement preparation study plan for a student.

Performance profile:
- Weak topics (needs focus): {weak_str}
- Strong topics (maintain):  {strong_str}

Requirements:
- Day-by-day schedule with specific activities
- Allocate more time to weak topics
- Include practice test suggestions
- Add daily revision tips
- Keep it realistic (2-4 hours/day)
- Use markdown headers and bullet points for clarity"""

    result = _chat([{"role": "user", "content": prompt}], max_tokens=1200)
    cache[cache_key] = result
    return result


def generate_interview_questions(role: str, company_type: str = "product",
                                  count: int = 10) -> list[dict]:
    """
    Generate mock interview questions for a given role.
    """
    clean_role = _clean_input(role, max_chars=80)
    clean_company = _clean_input(company_type, max_chars=20)

    count  = min(count, 20)
    prompt = f"""Generate {count} realistic interview questions for a {clean_role} position at a {clean_company} company.

Include a mix of: technical, problem-solving, HR/behavioural, and aptitude questions.

Return ONLY a valid JSON array (no markdown fences) in this exact format:
[
  {{
    "question":   "question text",
    "category":   "Technical | Behavioural | Aptitude | HR",
    "difficulty": "easy | medium | hard",
    "tips":       "answering tip in one sentence"
  }}
]"""

    raw = _strip_json_fences(_chat([{"role": "user", "content": prompt}], max_tokens=1500))

    try:
        questions = json.loads(raw)
        if not isinstance(questions, list):
            raise ValueError("Expected a JSON array")
        return questions[:count]
    except (json.JSONDecodeError, ValueError) as exc:
        current_app.logger.warning("Groq interview questions parse error: %s", exc)
        return []
