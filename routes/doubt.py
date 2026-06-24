from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from services import ai_service
from utils.response import success, error

doubt_bp = Blueprint("doubt", __name__)


@doubt_bp.route("/solve", methods=["POST"])
@jwt_required()
def solve_doubt():
    """Solve an aptitude or coding doubt."""
    data = request.get_json(silent=True) or {}
    
    context = (data.get("context") or "General Placement Prep").strip()
    question = (data.get("question") or "").strip()
    doubt = (data.get("doubt") or "").strip()
    
    if not doubt:
        return error("doubt is required.", 422)
        
    try:
        solution = ai_service.solve_user_doubt(context, question, doubt)
        return success({
            "solution": solution
        }, 200)
    except Exception as exc:
        return error(f"Failed to solve doubt: {str(exc)}", 500)
