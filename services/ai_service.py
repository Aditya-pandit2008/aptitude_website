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
import uuid

from flask import current_app
from groq import Groq, APIStatusError, APIConnectionError, RateLimitError
from cachetools import TTLCache

# Caching instances
_explain_cache = None
_study_plan_cache = None

# ── Adaptive Difficulty Engine ────────────────────────────────────────────────
from collections import deque, defaultdict
from .translation_utils import _maybe_translate_input, _translate_output

# Store last 10 results per user (True for correct, False for incorrect)
_DIFFICULTY_HISTORY: defaultdict[str, deque] = defaultdict(lambda: deque(maxlen=10))

def _adjust_difficulty(user_id: str, base_level: str | None = None) -> str:
    """Return an adjusted difficulty based on recent performance.
    - base_level: optional explicit difficulty override.
    - If base_level is provided, use it as a starting point.
    - Otherwise infer from history: ↑ if >=8/10 correct, ↓ if <=4/10 correct.
    """
    # Normalise levels order
    levels = ["easy", "medium", "hard"]
    # Determine current level
    if base_level and base_level in levels:
        cur = base_level
    else:
        # Default to medium when no history
        cur = "medium"
        hist = list(_DIFFICULTY_HISTORY[user_id])
        if hist:
            correct = sum(hist)
            if correct >= 8:
                # try to go harder
                cur = levels[min(levels.index(cur) + 1, 2)]
            elif correct <= 4:
                # go easier
                cur = levels[max(levels.index(cur) - 1, 0)]
    # Update history with a placeholder (will be updated after answer)
    # Caller should record result via record_user_result()
    return cur

def _record_user_result(user_id: str, correct: bool) -> None:
    """Append a correctness flag to the user's difficulty history."""
    _DIFFICULTY_HISTORY[user_id].append(correct)


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


# Deprecated simple generate_similar_questions; use adaptive version below
def generate_similar_questions_deprecated(question_text: str, category: str, difficulty: str, count: int = 3) -> list[dict]:
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


def generate_similar_questions(question_text: str, category: str,
                                 difficulty: str, count: int = 3, user_id: str | None = None, language: str = "en") -> list[dict]:
    """Generate 'count' MCQ questions similar to the provided one.
    Supports adaptive difficulty and multilingual I/O.
    """
    # Translate inputs to English for the model
    kwargs, orig_lang = _maybe_translate_input(question_text=question_text, category=category, difficulty=difficulty, language=language)
    clean_text = _clean_input(kwargs["question_text"], max_chars=1000)
    clean_cat = _clean_input(kwargs["category"], max_chars=100)
    clean_diff = _clean_input(kwargs["difficulty"], max_chars=20)

    # Adaptive difficulty based on user history
    if user_id:
        clean_diff = _adjust_difficulty(user_id, clean_diff)

    count = min(count, 5)
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
        # Translate outputs back to original language
        return _translate_output(questions[:count], orig_lang)
    except (json.JSONDecodeError, ValueError) as exc:
        current_app.logger.warning("Groq returned malformed JSON: %s", exc)
        return []

def generate_aptitude_questions(category: str, difficulty: str, count: int = 10) -> list[dict]:
    """
    Generate fresh aptitude MCQs for a selected category and difficulty.
    """
    clean_cat = _clean_input(category or "Mixed Aptitude", max_chars=100)
    clean_diff = _clean_input(difficulty or "medium", max_chars=20).lower()

    count      = min(max(int(count or 10), 1), 30)
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


def evaluate_open_ended(question_text: str, student_answer: str) -> dict:
    """Evaluate an open-ended response using Groq."""
    prompt = f"""You are an expert examiner. Evaluate the student's answer to the following question.

Question: {question_text}
Student's Answer: {student_answer}

Provide:
1. "is_correct": boolean (true if the answer is conceptually correct, false otherwise)
2. "score": float from 0.0 to 1.0 (representing degree of correctness)
3. "feedback": a concise explanation of why the answer is correct/incorrect, pointing out any gaps or errors.

Return ONLY a valid JSON object with the keys "is_correct" (boolean), "score" (number), and "feedback" (string). No markdown, no extra text.
"""
    try:
        raw = _strip_json_fences(_chat([{"role": "user", "content": prompt}], max_tokens=500, temperature=0.2))
        res = json.loads(raw)
        return {
            "is_correct": bool(res.get("is_correct", False)),
            "score": float(res.get("score", 0.0)),
            "feedback": str(res.get("feedback", "No feedback provided."))
        }
    except Exception as exc:
        current_app.logger.warning("Error evaluating open-ended answer via Groq: %s", exc)
        return {
            "is_correct": False,
            "score": 0.0,
            "feedback": "AI evaluation failed due to a system error."
        }


def review_coding_challenge(question_text: str, submitted_code: str, language: str) -> dict:
    """Review code for complexity and quality."""
    prompt = f"""You are an expert code reviewer. Evaluate the following {language} code for a coding challenge.

Problem Description:
{question_text}

Submitted Code:
{submitted_code}

Provide:
1. "feedback": What is good, any issues, and an explanation of the time and space complexity of the code.
2. "optimization_tips": Any suggestions to make the code faster or more idiomatic.

Return ONLY a valid JSON object with the keys "feedback" (string) and "optimization_tips" (string). No markdown fences.
"""
    try:
        raw = _strip_json_fences(_chat([{"role": "user", "content": prompt}], max_tokens=800, temperature=0.2))
        res = json.loads(raw)
        return {
            "feedback": str(res.get("feedback", "No feedback provided.")),
            "optimization_tips": str(res.get("optimization_tips", ""))
        }
    except Exception as exc:
        current_app.logger.warning("Error reviewing coding challenge via Groq: %s", exc)
        return {
            "feedback": "AI evaluation failed due to a system error.",
            "optimization_tips": ""
        }


def generate_coding_challenge(category: str, difficulty: str, exclude_titles: list[str] = None) -> dict | None:
    clean_cat = _clean_input(category, max_chars=100)
    clean_diff = _clean_input(difficulty, max_chars=20).lower()
    import uuid
    # Generate a unique seed to vary the AI prompt and avoid duplicate generation
    seed = uuid.uuid4().hex
    prompt = f"""Generate a new coding challenge for a student preparing for software engineering interviews.
# Unique seed: {seed}

Topic: {clean_cat}
Difficulty Level: {clean_diff}

Rules:
- The challenge MUST be strictly relevant to the specified Topic ({clean_cat}).
  - If the topic is "Math", the coding problem MUST be mathematical in nature (e.g., prime numbers, GCD/LCM, Sieve of Eratosthenes, modular arithmetic, Fibonacci, combinatorics, counting primes, or numeric operations). Do NOT generate general array/sorting/graph problems unless they are secondary to a core mathematical task.
  - If the topic is "Strings", the problem MUST focus on string processing, pattern matching, substring manipulation, character frequency, or similar string-based tasks.
  - If the topic is "Data Structures", the problem MUST focus on utilizing, designing, or manipulating specific data structures (Stacks, Queues, Linked Lists, Trees, Graphs, Hash Tables, etc.).
  - If the topic is "Algorithms", the problem MUST test algorithmic patterns (e.g., Binary Search, Dynamic Programming, Greedy, Backtracking, Two Pointers).
- The problem must be clear, complete, and test algorithmic thinking.
- Provide 3 hidden test cases and 2 sample test cases.
- Test cases must be a list of dictionaries with "input" (string representation of inputs) and "expected_output" (string representation).
- Do not make the test case input format overly complicated. E.g. array of ints can be "1,2,3"
- Provide LeetCode-style pre-coded starter stubs for 5 languages in "template_code" (a JSON object, NOT a string).
  Each stub must be a complete class/function skeleton — body should be empty or contain just a return placeholder.
  Languages required: python, java, cpp, javascript, c.
  Use the actual problem's function name and appropriate types (not generic placeholders like Object or auto).

CRITICAL INSTRUCTION: Return EXACTLY ONE valid JSON object and nothing else. Do NOT include markdown, conversational text, or extra JSON blocks. Output must start with {{ and end with }} and be parseable by json.loads.

Format:
{{
  "title": "Two Sum",
  "text": "Full problem description...",
  "template_code": {{
    "python": "class Solution:\\n    def twoSum(self, nums: List[int], target: int) -> List[int]:\\n        pass",
    "java": "class Solution {{\\n    public int[] twoSum(int[] nums, int target) {{\\n        \\n    }}\\n}}",
    "cpp": "class Solution {{\\npublic:\\n    vector<int> twoSum(vector<int>& nums, int target) {{\\n        \\n    }}\\n}};",
    "javascript": "/**\\n * @param {{number[]}} nums\\n * @param {{number}} target\\n * @return {{number[]}}\\n */\\nvar twoSum = function(nums, target) {{\\n    \\n}};",
    "c": "/**\\n * Note: The returned array must be malloced, assume caller calls free().\\n */\\nint* twoSum(int* nums, int numsSize, int target, int* returnSize) {{\\n    \\n}}"
  }},
  "sample_test_cases": [{{"input": "1", "expected_output": "1"}}],
  "test_cases": [{{"input": "2", "expected_output": "2"}}]
}}
"""
    if exclude_titles:
        # Avoid passing hundreds of titles to avoid token bloat; just pass the last 50
        filtered_excludes = [t for t in exclude_titles if t]
        if filtered_excludes:
            exclude_str = ", ".join(f'"{t}"' for t in filtered_excludes[-50:])
            prompt += f"\n- CRITICAL DUPLICATE PREVENTION: Do NOT generate any coding challenges with the following titles: {exclude_str}. Design a completely different and unique problem statement."

    raw = _chat([{"role": "user", "content": prompt}], max_tokens=2000, temperature=0.7)

    # strict=False lets json.loads accept literal newlines/tabs inside strings,
    # which Groq sometimes emits for multi-line problem descriptions.
    def _try_parse(s: str):
        try:
            return json.loads(s, strict=False)
        except json.JSONDecodeError:
            return None

    # Extract the outermost {...} block and parse it
    start_idx = raw.find('{')
    end_idx   = raw.rfind('}')
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        candidate = raw[start_idx:end_idx + 1]
        parsed = _try_parse(candidate)
        if parsed and "title" in parsed and "template_code" in parsed:
            return parsed

    # Last resort: parse the whole raw string
    parsed = _try_parse(raw)
    if parsed and isinstance(parsed, dict) and "title" in parsed:
        return parsed

        # New fallback: use regex to find potential JSON objects and try each
    import re as _re
    for m in _re.finditer(r"\{.*?\}", raw, _re.DOTALL):
        cand = m.group(0)
        # Attempt to close truncated JSON if missing closing brace
        if cand.count('{') > cand.count('}'):
            cand = cand.rstrip() + '}'
        parsed = _try_parse(cand)
        if parsed and isinstance(parsed, dict) and "title" in parsed:
            return parsed

    # Additional salvage: truncate at common non-JSON markers and close brace
    trunc = raw.split('Result:')[0].strip()
    if not trunc.endswith('}'):
        trunc = trunc + '}'
    parsed = _try_parse(trunc)
    if parsed and isinstance(parsed, dict) and "title" in parsed:
        return parsed

    current_app.logger.warning(
        "Groq coding challenge parse error: no valid JSON found. Raw snippet: %s", raw[:300]
    )
    return None


def generate_mock_interview_questions(role: str, interview_type: str, difficulty: str) -> list[str]:
    """Generate 5 interview questions for mock interviews using Groq."""
    clean_role = _clean_input(role, max_chars=80)
    clean_type = _clean_input(interview_type, max_chars=20)
    clean_diff = _clean_input(difficulty, max_chars=20)
    
    prompt = f"""You are an expert technical recruiter conducting a {clean_type} mock interview for a {clean_role} position.
Generate exactly 5 relevant interview questions of {clean_diff} difficulty.
Return ONLY a valid JSON array of strings (no markdown, no extra conversational text) containing precisely the 5 questions.
Format:
[
  "Question 1 text...",
  "Question 2 text...",
  "Question 3 text...",
  "Question 4 text...",
  "Question 5 text..."
]"""

    try:
        raw = _strip_json_fences(_chat([{"role": "user", "content": prompt}], max_tokens=1000, temperature=0.7))
        questions = json.loads(raw)
        if isinstance(questions, list) and len(questions) > 0:
            return [str(q).strip() for q in questions]
    except Exception as exc:
        current_app.logger.warning("Error generating interview questions: %s", exc)
    
    # Fallback questions
    if clean_type.lower() == "hr":
        return [
            f"Tell me about yourself and your interest in the {clean_role} role.",
            "What are your greatest strengths and how do they apply to this job?",
            "Describe a time you faced a difficult challenge in a project and how you overcame it.",
            "Where do you see yourself in five years?",
            "Why should we hire you over other candidates?"
        ]
    else:
        return [
            f"What is the difference between OOP and procedural programming, and how does it relate to {clean_role}?",
            "Explain the time complexity of QuickSort versus MergeSort.",
            "What is a deadlock and how can it be prevented in an operating system?",
            "How do indexes work in databases, and what are their pros and cons?",
            "Describe a system architecture design pattern you've used recently."
        ]


def evaluate_mock_interview(role: str, interview_type: str, questions: list[str], answers: list[str]) -> dict:
    """Evaluate candidate responses to mock interview questions."""
    qa_list = []
    for q, a in zip(questions, answers):
        qa_list.append(f"Question: {q}\nAnswer: {a}\n")
    qa_pairs_str = "\n".join(qa_list)

    prompt = f"""You are an expert interviewer. Evaluate the candidate's answers for a {interview_type} mock interview for the role of {role}.

Questions and Answers:
{qa_pairs_str}

Provide:
1. "score": An integer score from 0 to 100 representing overall performance.
2. "feedback": Comprehensive constructive feedback containing:
   - Strengths in their answers
   - Weaknesses and gaps in understanding
   - Actionable recommendations and model answer advice for poorly answered questions.

Return ONLY a valid JSON object with keys "score" (integer) and "feedback" (string). Do not include markdown code blocks around the JSON."""

    try:
        raw = _strip_json_fences(_chat([{"role": "user", "content": prompt}], max_tokens=1200, temperature=0.3))
        res = json.loads(raw)
        return {
            "score": min(max(int(res.get("score", 0)), 0), 100),
            "feedback": str(res.get("feedback", "No feedback provided."))
        }
    except Exception as exc:
        current_app.logger.warning("Error evaluating mock interview: %s", exc)
        return {
            "score": 50,
            "feedback": "AI evaluation failed due to a system error. Standard feedback: Please make sure your answers are detailed, provide code examples where applicable, and address the specific question being asked."
        }


def analyze_resume_ats(resume_text: str, job_description: str) -> dict:
    """Analyze a resume text against a target job description for ATS suitability."""
    clean_resume = resume_text[:4000] # Cap length to avoid token limit issues
    clean_jd = (job_description or "Software Engineering / General IT Placement")[:2000]

    prompt = f"""You are an advanced Applicant Tracking System (ATS) optimizer and expert placement consultant.
Analyze the candidate's resume text against the target job description to determine keyword matching, formatting quality, and structural gaps.

Resume Text:
{clean_resume}

Target Job Description:
{clean_jd}

Provide:
1. "ats_score": An integer from 0 to 100 representing the match score.
2. "feedback": A concise paragraph summarizing overall layout, impact, and content strength.
3. "improvements": A list of 3-5 specific bullet points for improvement.
4. "skills_detected": A list of technical and soft skills identified.
5. "skills_gap": A list of key missing skills or qualifications that are highly relevant.

Return ONLY a valid JSON object with the exact keys: "ats_score" (integer), "feedback" (string), "improvements" (array of strings), "skills_detected" (array of strings), and "skills_gap" (array of strings). Do not wrap in markdown or explain the JSON."""

    try:
        raw = _strip_json_fences(_chat([{"role": "user", "content": prompt}], max_tokens=1200, temperature=0.2))
        res = json.loads(raw)
        return {
            "ats_score": min(max(int(res.get("ats_score", 0)), 0), 100),
            "feedback": str(res.get("feedback", "Could not complete layout summary.")),
            "improvements": list(res.get("improvements", [])),
            "skills_detected": list(res.get("skills_detected", [])),
            "skills_gap": list(res.get("skills_gap", []))
        }
    except Exception as exc:
        current_app.logger.warning("Error analyzing resume: %s", exc)
        return {
            "ats_score": 0,
            "feedback": "ATS resume parsing failed due to a system error. Please try again.",
            "improvements": ["Try copy-pasting your resume text cleanly.", "Ensure your contact info is easy to identify."],
            "skills_detected": [],
            "skills_gap": []
        }


def solve_user_doubt(context: str, question: str, doubt: str) -> str:
    """Solve an aptitude or programming doubt step-by-step."""
    prompt = f"""You are an elite campus placement AI Doubt Solver. Provide a clear, step-by-step, pedagogical explanation to resolve the student's doubt.

Context / Description:
{context}

Question or Code details:
{question}

Student's Doubt:
{doubt}

Ensure you:
1. Explain the underlying concept.
2. Work through the calculation or code logic step-by-step.
3. Keep it clear, concise, and professional.

Return your response in clean, professional markdown format."""

    try:
        return _chat([{"role": "user", "content": prompt}], max_tokens=1000, temperature=0.4)
    except Exception as exc:
        current_app.logger.warning("Error solving user doubt: %s", exc)
        return "I encountered an error trying to process your doubt. Please try rephrasing or check your network connection."