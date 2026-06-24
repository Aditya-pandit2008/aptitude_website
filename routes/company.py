import random
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required

from models import db, Question, Category
from utils.response import success, error

company_bp = Blueprint("company", __name__)

# Curated company profiles containing patterns and prep syllabus
COMPANY_PROFILES = {
    "tcs": {
        "name": "TCS (Tata Consultancy Services)",
        "description": "Recruits largely through TCS NQT (National Qualifier Test) for Ninja and Digital roles.",
        "rounds": "Online Test (Cognitive + Technical) -> Technical Interview -> HR Interview",
        "difficulty": "Medium",
        "test_pattern": "Cognitive (Quant + Verbal + Logic) and Technical (Coding + MCQs)",
        "syllabus": ["Quantitative Aptitude", "Logical Reasoning", "Verbal Ability", "Technical - DSA"],
        "color": "#1A365D",
        "xp_multiplier": 1.2,
        "sample_questions": [
            {"title": "Sum of prime divisors", "type": "coding", "desc": "Find the sum of all prime numbers dividing N."},
            {"title": "Logical deduction", "type": "aptitude", "desc": "All dogs are animals. Some animals are wild. Conclusions..."}
        ]
    },
    "infosys": {
        "name": "Infosys",
        "description": "Recruits via Infosys Certification / InfyTQ or HackWithInfy for System Engineer and Specialist Programmer roles.",
        "rounds": "Online Assessment (Cognitive + Technical) -> Interview (Technical + HR)",
        "difficulty": "Medium-Hard",
        "test_pattern": "Mathematical ability, Logical reasoning, Verbal ability, Pseudo-code and Puzzle solving.",
        "syllabus": ["Logical Reasoning", "Verbal Ability", "Quantitative Aptitude", "Technical - DSA"],
        "color": "#005ea2",
        "xp_multiplier": 1.3,
        "sample_questions": [
            {"title": "Pseudo-code analysis", "type": "aptitude", "desc": "What is the output of the loop if x=15 and y=4?"},
            {"title": "Array modification", "type": "coding", "desc": "Modify the array such that prime elements are sorted."}
        ]
    },
    "wipro": {
        "name": "Wipro",
        "description": "Recruits through Elite NTH (National Talent Hunt) and Turbo hiring channels.",
        "rounds": "Online Assessment (Aptitude + Written Communication + Coding) -> Business Interview",
        "difficulty": "Medium",
        "test_pattern": "Quantitative Aptitude, Logical Reasoning, Verbal Ability, Essay Writing (Automated evaluation), and 2 coding questions.",
        "syllabus": ["Quantitative Aptitude", "Verbal Ability", "Technical - DSA"],
        "color": "#5D2B90",
        "xp_multiplier": 1.15,
        "sample_questions": [
            {"title": "Letter Arrangement", "type": "aptitude", "desc": "In how many ways can letters of the word 'WIPRO' be arranged?"},
            {"title": "Matrix rotation", "type": "coding", "desc": "Rotate a square matrix by 90 degrees counter-clockwise."}
        ]
    },
    "accenture": {
        "name": "Accenture",
        "description": "Recruits Associate Software Engineer (ASE) and Advanced ASE roles through their national cognitive/technical assessment.",
        "rounds": "Cognitive + Technical assessment -> Coding Test -> Communication Test -> HR Interview",
        "difficulty": "Medium",
        "test_pattern": "Critical thinking, Problem solving, Technical MCQ (DBMS, OS, Cloud, Networks), Coding (2 questions), Communication assessment (speaking/listening).",
        "syllabus": ["Logical Reasoning", "Technical - Networks", "Technical - DBMS", "Technical - DSA"],
        "color": "#800080",
        "xp_multiplier": 1.25,
        "sample_questions": [
            {"title": "IP Addressing", "type": "aptitude", "desc": "Which layer of the OSI model determines IP address matching?"},
            {"title": "Subnet Mask calculation", "type": "aptitude", "desc": "For a subnet 192.168.1.0/26, how many hosts are usable?"}
        ]
    },
    "cognizant": {
        "name": "Cognizant",
        "description": "Hires for GenC and GenC Elevate positions with emphasis on data skills, databases, and application programming.",
        "rounds": "Skill assessment (Technical MCQs + Coding) -> Technical Interview -> HR/Behavioural Round",
        "difficulty": "Medium",
        "test_pattern": "Quantitative Aptitude, Logical Reasoning, Technical MCQs (SQL query results, Normalization, Database schema structure), and Coding.",
        "syllabus": ["Logical Reasoning", "Quantitative Aptitude", "Technical - DBMS"],
        "color": "#002d62",
        "xp_multiplier": 1.2,
        "sample_questions": [
            {"title": "SQL Subqueries", "type": "aptitude", "desc": "Write a query to find the second highest salary from employees table."},
            {"title": "3NF normalisation", "type": "aptitude", "desc": "Identify database schema normalization form for given functional dependencies."}
        ]
    },
    "capgemini": {
        "name": "Capgemini",
        "description": "Hires through national pool and on-campus events using their updated game-based aptitude testing process.",
        "rounds": "Pseudo-code assessment -> English communication -> Game-based aptitude -> Technical & HR Interview",
        "difficulty": "Medium",
        "test_pattern": "Pseudo-code comprehension, Verbal comprehension, Grid challenge, Deductive challenge, Motion challenge, and Technical interview.",
        "syllabus": ["Logical Reasoning", "Technical - OS", "Technical - DSA"],
        "color": "#0070ad",
        "xp_multiplier": 1.2,
        "sample_questions": [
            {"title": "Binary Tree search", "type": "coding", "desc": "Search an element in binary search tree."},
            {"title": "Thread scheduling", "type": "aptitude", "desc": "What is thread starvation in OS CPU scheduling algorithms?"}
        ]
    }
}


@company_bp.route("/details", methods=["GET"])
def get_company_details():
    """Retrieve detailed recruitment syllabus and pattern for companies."""
    return jsonify({"success": True, "companies": COMPANY_PROFILES}), 200


@company_bp.route("/practice-test", methods=["POST"])
@jwt_required()
def generate_practice_test():
    """Generate a custom aptitude practice test for the selected company."""
    data = request.get_json(silent=True) or {}
    company_key = str(data.get("company_name", "")).strip().lower()
    count = min(max(int(data.get("count", 10)), 5), 20)

    if company_key not in COMPANY_PROFILES:
        return error(f"Invalid company. Choose from: {list(COMPANY_PROFILES.keys())}", 400)

    profile = COMPANY_PROFILES[company_key]
    syllabus = profile["syllabus"]

    # Match syllabus names to Category models
    categories = Category.query.filter(Category.name.in_(syllabus)).all()
    cat_ids = [c.id for c in categories]

    if not cat_ids:
        # Fallback to any category
        categories = Category.query.limit(4).all()
        cat_ids = [c.id for c in categories]

    # Select random questions from these category IDs
    questions_pool = Question.query.filter(
        Question.category_id.in_(cat_ids),
        Question.is_active == True
    ).all()

    if not questions_pool:
        # Fallback to general active questions pool
        questions_pool = Question.query.filter_by(is_active=True).all()

    if not questions_pool:
        return success({"questions": [], "count": 0, "company": profile["name"]}, 200)

    selected = random.sample(questions_pool, min(len(questions_pool), count))
    
    return success({
        "questions": [q.to_dict(include_answer=False) for q in selected],
        "count": len(selected),
        "company_name": profile["name"],
        "syllabus": syllabus,
        "difficulty": profile["difficulty"]
    }, 200)
