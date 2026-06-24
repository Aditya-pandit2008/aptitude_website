from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from models import db, User, ResumeAnalysis
from services import ai_service
from utils.response import success, error

resume_bp = Blueprint("resume", __name__)


@resume_bp.route("/analyze", methods=["POST"])
@jwt_required()
def analyze_resume():
    """Analyze a resume text copy-pasted by the student."""
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    
    resume_text = (data.get("resume_text") or "").strip()
    job_description = (data.get("job_description") or "").strip()
    
    if not resume_text:
        return error("resume_text is required.", 422)

    try:
        # Call Groq AI analyzer
        analysis = ai_service.analyze_resume_ats(resume_text, job_description)
        
        ats_score = analysis["ats_score"]
        feedback = analysis["feedback"]
        improvements = analysis["improvements"]
        skills_detected = analysis["skills_detected"]
        skills_gap = analysis["skills_gap"]
        
        # Save record
        record = ResumeAnalysis(
            user_id=user_id,
            resume_text=resume_text,
            job_description=job_description,
            ats_score=ats_score,
            feedback=feedback
        )
        record.improvements = improvements
        record.skills_detected = skills_detected
        record.skills_gap = skills_gap
        
        db.session.add(record)
        
        # Reward 15 XP for parsing a resume
        user = db.session.get(User, user_id)
        if user:
            user.total_xp += 15
            db.session.add(user)
            
        db.session.commit()
        
        return success({
            "message": "Resume analyzed successfully.",
            "analysis": record.to_dict(),
            "xp_earned": 15
        }, 201)
        
    except Exception as exc:
        db.session.rollback()
        return error(f"Failed to analyze resume: {str(exc)}", 500)


@resume_bp.route("/history", methods=["GET"])
@jwt_required()
def get_history():
    """Fetch user's past resume analysis runs."""
    user_id = int(get_jwt_identity())
    analyses = (
        ResumeAnalysis.query.filter_by(user_id=user_id)
        .order_by(ResumeAnalysis.created_at.desc())
        .all()
    )
    return success({
        "analyses": [a.to_dict() for a in analyses],
        "count": len(analyses)
    }, 200)
