import json
import os
import re
import requests
from flask import Blueprint, request, jsonify, render_template
from flask_jwt_extended import jwt_required, get_jwt_identity

from extensions import limiter
from models import db, Question, CodeChallenge, CodingAttempt, Category
from services.ai_service import generate_coding_challenge, review_coding_challenge
from utils.response import success, error
from services.feature_helpers import create_quiz_session, submit_quiz_answer, finish_quiz_session
from services.leaderboard import record_score, get_top_scores

coding_bp = Blueprint("coding", __name__)

PISTON_API_URL = "https://emkc.org/api/v2/piston/execute"

# Map frontend language names to Piston API languages & versions
PISTON_LANGUAGES = {
    "python": {"language": "python", "version": "3.10.0"},
    "java": {"language": "java", "version": "15.0.2"},
    "cpp": {"language": "cpp", "version": "10.2.0"},
    "javascript": {"language": "javascript", "version": "16.3.0"},
    "ruby": {"language": "ruby", "version": "3.2.0"},
    "go": {"language": "go", "version": "1.20.0"},
    "csharp": {"language": "csharp", "version": "10.0.0"},
    "rust": {"language": "rust", "version": "1.68.0"},
    "kotlin": {"language": "kotlin", "version": "1.8.0"},
    "php": {"language": "php", "version": "8.2.0"},
    "swift": {"language": "swift", "version": "5.8.0"},
    "scala": {"language": "scala", "version": "3.2.2"},
    "typescript": {"language": "typescript", "version": "5.0.0"}
}
XP_BY_DIFFICULTY = {"easy": 30, "medium": 50, "hard": 80}


# ── Helper: infer topic from tags / title / text ──────────────────────────────

def _infer_topic(challenge, question):
    """Return a topic string for the challenge. Persists inferred tag if needed."""
    tags = question.tag_list
    for t in tags:
        if t not in ["groq-ai", "coding"]:
            return t

    title_lower = (challenge.title or "").lower()
    text_lower = (question.text or "").lower()

    topic_keywords = [
        ("Strings",             ["string", "char", "vowel", "palindrome", "anagram", "word"]),
        ("Math",                ["prime", "gcd", "lcm", "factor", "divisor", "modulo", "fibonacci", "math"]),
        ("Data Structures",     ["queue", "stack", "list", "tree", "graph", "heap", "map", "bst", "node", "array", "window"]),
        ("Greedy",              ["greedy", "optimal", "kruskal", "prim"]),
        ("Dynamic Programming", ["dp", "dynamic programming", "memo", "tabulation"]),
        ("Recursion",           ["recursion", "recursive", "backtrack", "backtracking"]),
        ("Sorting",             ["sort", "sorting", "merge sort", "quick sort", "bubble", "heap sort"]),
        ("Search",              ["search", "binary search", "linear search", "dfs", "bfs"]),
        ("Graphs",              ["graph", "dfs", "bfs", "topological", "shortest path"]),
        ("Bit Manipulation",    ["bit", "mask", "xor", "shift", "binary"]),
        ("Two Pointers",        ["two pointers", "sliding window"]),
    ]

    topic = "Algorithms"
    for name, words in topic_keywords:
        if any(w in title_lower or w in text_lower for w in words):
            topic = name
            break

    question.tags = f"groq-ai,coding,{topic}"
    db.session.add(question)
    return topic


# ── Page routes ───────────────────────────────────────────────────────────────

@coding_bp.route("/challenges-page")
def challenges_page():
    return render_template("coding-challenges.html")

@coding_bp.route("/editor-page")
def editor_page():
    return render_template("challenge-editor.html")


# ── API routes ────────────────────────────────────────────────────────────────

@coding_bp.route("/", methods=["GET"])
@jwt_required()
def list_challenges():
    """List all coding challenges with question details flattened for the UI."""
    rows = (
        db.session.query(CodeChallenge, Question)
        .join(Question, CodeChallenge.question_id == Question.id)
        .filter(Question.is_active == True, Question.question_type == "coding")
        .all()
    )
    results = []
    for challenge, question in rows:
        _infer_topic(challenge, question)
        results.append({
            "code_challenge": challenge.to_dict(),
            "difficulty": question.difficulty,
            "category_name": question.category.name if question.category else "",
            "text": question.text,
            "question": question.to_dict(),
        })
    db.session.commit()
    return success({"challenges": results}, 200)


@coding_bp.route("/<int:challenge_id>", methods=["GET"])
@jwt_required()
def get_challenge(challenge_id):
    """Get a specific coding challenge by CodeChallenge ID."""
    challenge = CodeChallenge.query.filter_by(id=challenge_id).first_or_404()
    question = challenge.question
    _infer_topic(challenge, question)
    db.session.commit()
    return success({"challenge": challenge.to_dict(), "question": question.to_dict()}, 200)


@coding_bp.route("/generate", methods=["POST"])
@jwt_required()
@limiter.limit("10 per hour")
def generate_challenge():
    """Generate a new coding challenge via AI."""
    data = request.get_json(silent=True) or {}
    category = data.get("category", "Data Structures")
    difficulty = data.get("difficulty", "medium")

    # Fetch existing challenge titles to avoid duplicates
    existing_titles = [c.title for c in CodeChallenge.query.all() if c.title]
    ai_data = generate_coding_challenge(category, difficulty, exclude_titles=existing_titles)
    if not ai_data:
        return error("Failed to generate coding challenge.", 502)

    # Resolve category
    db_cat_name = "Technical - DSA"
    if category.lower() == "math":
        db_cat_name = "Quantitative Aptitude"

    db_category = Category.query.filter(Category.name.ilike(f"%{db_cat_name}%")).first()
    if not db_category:
        db_category = Category.query.filter(Category.name.ilike(f"%{category}%")).first()
    if not db_category:
        db_category = Category.query.first()

    user_id = int(get_jwt_identity())

    question = Question(
        category_id=db_category.id,
        text=ai_data["text"],
        question_type="coding",
        difficulty=difficulty,
        tags=f"groq-ai,coding,{category}",
        created_by=user_id,
    )
    db.session.add(question)
    db.session.flush()

    challenge = CodeChallenge(
        question_id=question.id,
        title=ai_data.get("title", "Coding Challenge"),
        template_code=(
            json.dumps(ai_data["template_code"])
            if isinstance(ai_data.get("template_code"), dict)
            else ai_data.get("template_code", "")
        ),
    )
    challenge.test_cases = ai_data.get("test_cases", [])
    challenge.sample_cases = ai_data.get("sample_test_cases", [])

    db.session.add(challenge)
    db.session.commit()

    return success({
        "message": "Coding challenge generated.",
        "challenge": challenge.to_dict(),
        "question": question.to_dict()
    }, 201)


@coding_bp.route("/execute", methods=["POST"])
@jwt_required()
@limiter.limit("30 per hour")
def execute_code():
    """Execute arbitrary code against the Piston sandbox API."""
    data      = request.get_json(silent=True) or {}
    language  = data.get("language")
    user_code = data.get("code")

    if not language or language not in PISTON_LANGUAGES:
        return error("Invalid or unsupported language.", 400)
    if not user_code:
        return error("Code is required.", 400)

    payload = {
        "language": PISTON_LANGUAGES[language]["language"],
        "version":  PISTON_LANGUAGES[language]["version"],
        "files":    [{"content": user_code}],
    }

    try:
        res = requests.post(PISTON_API_URL, json=payload, timeout=10)
        res.raise_for_status()
        run_data  = res.json().get("run", {})
        stdout    = run_data.get("stdout", "")
        stderr    = run_data.get("stderr", "")
        exit_code = run_data.get("code", 0)

        return success({"output": stdout + stderr, "exit_code": exit_code}, 200)

    except requests.exceptions.RequestException as exc:
        return error(f"Failed to execute code: {str(exc)}", 502)


# ── Test-case driver builders ─────────────────────────────────────────────────

def _build_python_driver(user_code: str, test_cases: list) -> str:
    """
    Append a driver to the user's Python code that runs each test case.
    Prints 'PASS' or 'FAIL:<actual>' per case so results can be parsed line-by-line.
    """
    match   = re.search(r"def\s+(\w+)\s*\(", user_code)
    fn_name = match.group(1) if match else None
    if not fn_name:
        return user_code

    lines = [user_code, "\n\n# === AUTO DRIVER ==="]
    for tc in test_cases:
        raw_input = str(tc.get("input", "")).replace("\\", "\\\\").replace("'", "\\'")
        expected  = str(tc.get("expected_output", "")).strip()
        lines.append(
            f"try:\n"
            f"    _args = [{raw_input}]\n"
            f"    _result = str({fn_name}(*_args)).strip()\n"
            f"    _expected = '{expected}'\n"
            f"    print('PASS' if _result == _expected else f'FAIL:{{_result}}')\n"
            f"except Exception as _e:\n"
            f"    print(f'ERROR:{{_e}}')\n"
        )
    return "\n".join(lines)


def _build_javascript_driver(user_code: str, test_cases: list) -> str:
    """Append a driver to the user's JS code."""
    match = re.search(r"function\s+(\w+)\s*\(", user_code)
    fn_name = match.group(1) if match else "solve"

    lines = [user_code, "\n\n// === AUTO DRIVER ==="]
    for tc in test_cases:
        raw_input = str(tc.get("input", "")).strip()
        expected = str(tc.get("expected_output", "")).strip()
        lines.append(
            f"try {{\n"
            f"    let _res = String({fn_name}({raw_input})).trim();\n"
            f"    let _exp = '{expected}';\n"
            f"    console.log(_res === _exp ? 'PASS' : 'FAIL:' + _res);\n"
            f"}} catch (e) {{\n"
            f"    console.log('ERROR:' + e.message);\n"
            f"}}"
        )
    return "\n".join(lines)


def _build_cpp_driver(user_code: str, test_cases: list) -> str:
    """Append a driver main function to C++ code."""
    fn_name = "solve"
    match = re.search(r"\b(\w+)\s+(\w+)\s*\(", user_code)
    if match and match.group(2) != "main":
        fn_name = match.group(2)

    lines = [
        "#include <iostream>",
        "#include <string>",
        "#include <vector>",
        "#include <sstream>",
        "using namespace std;",
        "",
        "template<typename T>",
        "string to_str(const T& val) {",
        "    stringstream ss;",
        "    ss << val;",
        "    return ss.str();",
        "}",
        "",
        user_code,
        "\n\n// === AUTO DRIVER ==="
    ]

    main_lines = ["int main() {"]
    for tc in test_cases:
        raw_input = str(tc.get("input", "")).strip()
        expected = str(tc.get("expected_output", "")).strip()
        main_lines.append(
            f"    try {{\n"
            f"        auto result = {fn_name}({raw_input});\n"
            f"        if (to_str(result) == \"{expected}\") cout << \"PASS\\n\";\n"
            f"        else cout << \"FAIL:\" << to_str(result) << \"\\n\";\n"
            f"    }} catch (...) {{\n"
            f"        cout << \"ERROR\\n\";\n"
            f"    }}"
        )
    main_lines.append("    return 0;")
    main_lines.append("}")
    lines.append("\n".join(main_lines))
    return "\n".join(lines)


def _build_java_driver(user_code: str, test_cases: list) -> str:
    """Inject a main runner method inside the Java Solution class."""
    last_brace = user_code.rfind("}")
    if last_brace == -1:
        return user_code

    main_method = ["\n    public static void main(String[] args) {"]
    for tc in test_cases:
        raw_input = str(tc.get("input", "")).strip()
        expected = str(tc.get("expected_output", "")).strip()
        main_method.append(
            f"        try {{\n"
            f"            Solution solver = new Solution();\n"
            f"            String result = String.valueOf(solver.solve({raw_input})).trim();\n"
            f"            String expected = \"{expected}\";\n"
            f"            System.out.println(result.equals(expected) ? \"PASS\" : \"FAIL:\" + result);\n"
            f"        }} catch (Exception e) {{\n"
            f"            System.out.println(\"ERROR\");\n"
            f"        }}"
        )
    main_method.append("    }")
    main_method_str = "\n".join(main_method) + "\n}"
    return user_code[:last_brace] + main_method_str


def _run_against_test_cases(user_code: str, language: str, test_cases: list) -> dict:
    """
    Run user_code against all test_cases via Piston.
    Returns {passed, total, results: [{input, expected, actual, ok}]}.
    """
    if not test_cases:
        return {"passed": 0, "total": 0, "results": []}

    if language == "python":
        driver = _build_python_driver(user_code, test_cases)
    elif language == "javascript":
        driver = _build_javascript_driver(user_code, test_cases)
    elif language == "cpp":
        driver = _build_cpp_driver(user_code, test_cases)
    elif language == "java":
        driver = _build_java_driver(user_code, test_cases)
    else:
        driver = user_code

    payload = {
        "language": PISTON_LANGUAGES[language]["language"],
        "version":  PISTON_LANGUAGES[language]["version"],
        "files":    [{"content": driver}],
    }

    try:
        res = requests.post(PISTON_API_URL, json=payload, timeout=15)
        res.raise_for_status()
        run_data  = res.json().get("run", {})
        stdout    = run_data.get("stdout", "").strip()
        stderr    = run_data.get("stderr", "").strip()
        exit_code = run_data.get("code", 0)
    except requests.exceptions.RequestException:
        return {"passed": 0, "total": len(test_cases), "results": [], "error": "Piston unreachable"}

    # Parse per-line output
    out_lines = stdout.split("\n") if stdout else []
    results, passed = [], 0
    for i, tc in enumerate(test_cases):
        line = out_lines[i].strip() if i < len(out_lines) else "NO_OUTPUT"
        ok   = (line == "PASS")
        if ok:
            passed += 1
        actual = line.replace("FAIL:", "") if line.startswith("FAIL:") else line
        results.append({
            "input":    tc.get("input", ""),
            "expected": tc.get("expected_output", ""),
            "actual":   actual,
            "ok":       ok,
        })

    return {"passed": passed, "total": len(test_cases), "results": results}


@coding_bp.route("/<int:challenge_id>/submit", methods=["POST"])
@jwt_required()
@limiter.limit("20 per hour")
def submit_challenge(challenge_id):
    """Submit code for evaluation against hidden test cases."""
    data      = request.get_json(silent=True) or {}
    language  = data.get("language")
    user_code = data.get("code", "")

    if not language or language not in PISTON_LANGUAGES:
        return error("Invalid or unsupported language.", 400)
    if not user_code.strip():
        return error("Code is required.", 400)

    challenge  = CodeChallenge.query.filter_by(id=challenge_id).first_or_404()
    question   = challenge.question
    test_cases = challenge.test_cases

    # 1. Run against hidden test cases
    eval_result  = _run_against_test_cases(user_code, language, test_cases)
    passed_cases = eval_result["passed"]
    total_cases  = eval_result["total"]
    score        = round(passed_cases / total_cases, 2) if total_cases > 0 else 0.0
    status       = "passed" if passed_cases == total_cases else ("partial" if passed_cases > 0 else "failed")

    # 2. XP proportional to score and difficulty
    base_xp   = XP_BY_DIFFICULTY.get(question.difficulty, 50)
    xp_earned = int(base_xp * score)

    # 3. AI code review
    ai_eval = review_coding_challenge(question.text, user_code, language)
    feedback_text = (
        ai_eval.get("feedback", "") +
        "\n\nOptimization Tips:\n" +
        ai_eval.get("optimization_tips", "")
    )

    # 4. Save attempt
    user_id = int(get_jwt_identity())
    attempt = CodingAttempt(
        user_id=user_id,
        challenge_id=challenge.id,
        language=language,
        code=user_code,
        status=status,
        passed_cases=passed_cases,
        total_cases=total_cases,
        ai_feedback=feedback_text,
        score=score,
        xp_earned=xp_earned,
    )
    db.session.add(attempt)

    # 5. Credit XP
    from models import User
    user = db.session.get(User, user_id)
    if user:
        user.total_xp += xp_earned

    db.session.commit()

    return success({
        "message":      "Code submitted and evaluated.",
        "passed_cases": passed_cases,
        "total_cases":  total_cases,
        "score":        score,
        "status":       status,
        "xp_earned":    xp_earned,
        "test_results": eval_result.get("results", []),
        "attempt":      attempt.to_dict(),
    }, 201)
    @coding_bp.route("/<int:challenge_id>/hint", methods=["POST"])
    @jwt_required()
    @limiter.limit("20 per hour")
    def get_hint(challenge_id):
        """Return the next progressive hint for a coding challenge (max 3)."""
        import groq as groq_sdk
        from sqlalchemy import text

        MAX_HINTS = 3
        user_id = int(get_jwt_identity())

        challenge = CodeChallenge.query.filter_by(id=challenge_id).first_or_404()
        question  = challenge.question

        existing = db.session.execute(
            text("SELECT COUNT(*) FROM coding_hints WHERE user_id=:u AND challenge_id=:c"),
            {"u": user_id, "c": challenge_id}
        ).scalar()

        if existing >= MAX_HINTS:
            return error(f"You've used all {MAX_HINTS} hints for this challenge.", 400)

        hint_number = existing + 1

        hint_prompts = {
            1: f"Give a very brief conceptual hint (1-2 sentences, no code) for this coding problem:\n\n{question.text}\n\nPoint toward the right approach without revealing the solution.",
            2: f"Give a more specific hint with the key algorithm or data structure to use (still no full code) for:\n\n{question.text}\n\nThis is hint 2 of 3, be a bit more direct.",
            3: f"Give a detailed hint with pseudocode or a concrete example for:\n\n{question.text}\n\nThis is the final hint (3 of 3), you can show a partial implementation or step-by-step approach.",
        }

        try:
            client = groq_sdk.Groq(api_key=os.environ.get("GROQ_API_KEY"))
            response = client.chat.completions.create(
                model="llama3-8b-8192",
                messages=[
                    {"role": "system", "content": "You are a helpful coding tutor. Give concise, educational hints."},
                    {"role": "user", "content": hint_prompts[hint_number]}
                ],
                max_tokens=300,
                temperature=0.5,
            )
            hint_text = response.choices[0].message.content.strip()
        except Exception as exc:
            return error(f"Failed to generate hint: {str(exc)}", 502)

        db.session.execute(
            text("""
                INSERT INTO coding_hints (user_id, challenge_id, hint_number, hint_text)
                VALUES (:u, :c, :n, :t)
            """),
            {"u": user_id, "c": challenge_id, "n": hint_number, "t": hint_text}
        )
        db.session.commit()

        return success({
            "hint": hint_text,
            "hint_number": hint_number,
            "hints_remaining": MAX_HINTS - hint_number,
        }, 200)