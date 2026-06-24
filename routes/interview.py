from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from models import db, User, MockInterview
from services import ai_service
from utils.response import success, error

interview_bp = Blueprint("interview", __name__)


@interview_bp.route("/start", methods=["POST"])
@jwt_required()
def start_interview():
    """Start a new mock interview session and generate questions."""
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    
    role = data.get("role", "Software Engineer").strip()
    interview_type = data.get("interview_type", "technical").strip().lower()
    difficulty = data.get("difficulty", "medium").strip().lower()
    
    if interview_type not in ["technical", "hr"]:
        interview_type = "technical"
        
    if difficulty not in ["easy", "medium", "hard"]:
        difficulty = "medium"

    try:
        # Generate 5 questions via Groq AI
        questions = ai_service.generate_mock_interview_questions(role, interview_type, difficulty)
        if not questions or len(questions) == 0:
            return error("Could not generate interview questions.", 502)
            
        interview = MockInterview(
            user_id=user_id,
            role=role,
            interview_type=interview_type,
            difficulty=difficulty,
            status="pending"
        )
        interview.questions = questions
        interview.answers = []
        
        db.session.add(interview)
        db.session.commit()
        
        return success({
            "message": "Mock interview session started.",
            "interview_id": interview.id,
            "total_questions": len(questions),
            "first_question": questions[0],
            "current_question_index": 0
        }, 201)
        
    except Exception as exc:
        db.session.rollback()
        return error(f"Failed to start mock interview: {str(exc)}", 500)


@interview_bp.route("/submit-answer", methods=["POST"])
@jwt_required()
def submit_answer():
    """Submit an answer to the current question and get next or final score."""
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    
    interview_id = data.get("interview_id")
    question_index = data.get("question_index")
    answer = (data.get("answer") or "").strip()
    
    if not interview_id or question_index is None:
        return error("interview_id and question_index are required.", 422)
        
    interview = MockInterview.query.filter_by(id=interview_id, user_id=user_id).first_or_404()
    
    if interview.status == "completed":
        return error("This interview session has already been completed.", 400)
        
    questions = interview.questions
    answers = interview.answers
    
    if question_index < 0 or question_index >= len(questions):
        return error("Invalid question index.", 400)
        
    # Pad answers array if needed or update the item
    while len(answers) <= question_index:
        answers.append("")
    answers[question_index] = answer
    interview.answers = answers
    
    db.session.add(interview)
    db.session.flush()
    
    # Check if last question
    if question_index == len(questions) - 1:
        # Complete session and evaluate using AI
        eval_result = ai_service.evaluate_mock_interview(
            role=interview.role,
            interview_type=interview.interview_type,
            questions=questions,
            answers=answers
        )
        
        score = eval_result["score"]
        feedback = eval_result["feedback"]
        
        # Grant XP based on performance: baseline 30 XP + performance bonus (up to 50 XP)
        xp_earned = 30 + int(score * 0.5)
        
        interview.score = score
        interview.feedback = feedback
        interview.status = "completed"
        db.session.add(interview)
        
        # Credit user
        user = db.session.get(User, user_id)
        if user:
            user.total_xp += xp_earned
            db.session.add(user)
            
        db.session.commit()
        
        return success({
            "message": "Mock interview completed and evaluated.",
            "completed": True,
            "score": score,
            "feedback": feedback,
            "xp_earned": xp_earned
        }, 200)
    else:
        # Return next question
        next_idx = question_index + 1
        db.session.commit()
        return success({
            "completed": False,
            "next_question_index": next_idx,
            "next_question": questions[next_idx]
        }, 200)


@interview_bp.route("/history", methods=["GET"])
@jwt_required()
def get_history():
    """Get the user's past mock interview sessions."""
    user_id = int(get_jwt_identity())
    sessions = (
        MockInterview.query.filter_by(user_id=user_id)
        .order_by(MockInterview.created_at.desc())
        .all()
    )
    return success({
        "interviews": [s.to_dict() for s in sessions],
        "count": len(sessions)
    }, 200)
