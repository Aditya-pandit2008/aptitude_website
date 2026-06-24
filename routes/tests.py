"""
routes/tests.py
Aptitude test engine blueprint.

Endpoints:
    POST /api/v1/tests/submit       – submit answers and receive evaluation
    GET  /api/v1/tests/history      – list the user's past test attempts
    GET  /api/v1/tests/<id>         – get full details of a single attempt
    GET  /api/v1/tests/<id>/answers – per-question breakdown of an attempt
"""

from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from models import db, User, TestAttempt, TestAnswer
from services.evaluation import evaluate_test
from services.leaderboard_service import update_leaderboard
from utils.auth_utils import get_current_user
from utils.validators import validate_test_submission
from utils.response import success, error, paginated

tests_bp = Blueprint("tests", __name__)


@tests_bp.route("/submit", methods=["POST"])
@jwt_required()
def submit_test():
    """
    Submit a completed test for evaluation.
    """
    data = request.get_json(silent=True) or {}
    errors = validate_test_submission(data)
    if errors:
        return error("Validation failed.", 422, details=errors)

    user = get_current_user()
    if not user:
        return error("User not found.", 404)

    result = evaluate_test(
        user=user,
        answers_payload=data["answers"],
        time_taken=data.get("time_taken", 0),
        category_id=data.get("category_id"),
    )

    # Refresh leaderboard asynchronously-like (same request, lightweight)
    update_leaderboard(user.id)

    # Invalidate dashboard category breakdown cache
    from routes.dashboard import invalidate_breakdown_cache
    invalidate_breakdown_cache(user.id)

    return success({
        "message": "Test submitted successfully.",
        "result": result,
    }, 201)


@tests_bp.route("/history", methods=["GET"])
@jwt_required()
def get_history():
    """
    Return paginated test history for the current user.
    """
    user_id  = get_jwt_identity()
    page     = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 10, type=int), 50)

    p = (
        TestAttempt.query
        .filter_by(user_id=user_id)
        .order_by(TestAttempt.completed_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    return paginated(
        items=[a.to_dict() for a in p.items],
        total=p.total,
        page=p.page,
        pages=p.pages,
        per_page=per_page,
    )


@tests_bp.route("/<int:attempt_id>", methods=["GET"])
@jwt_required()
def get_attempt(attempt_id):
    """
    Return the summary of a specific test attempt.
    """
    user_id = get_jwt_identity()
    attempt = TestAttempt.query.filter_by(id=attempt_id, user_id=user_id).first_or_404()
    return success({"attempt": attempt.to_dict()}, 200)


@tests_bp.route("/<int:attempt_id>/answers", methods=["GET"])
@jwt_required()
def get_attempt_answers(attempt_id):
    """
    Return per-question breakdown for a specific attempt.
    """
    user_id = get_jwt_identity()
    attempt = TestAttempt.query.filter_by(id=attempt_id, user_id=user_id).first_or_404()

    answers = TestAnswer.query.filter_by(attempt_id=attempt_id).all()
    return success({
        "attempt_id": attempt_id,
        "summary": attempt.to_dict(),
        "answers": [a.to_dict() for a in answers],
    }, 200)
@tests_bp.route("/export/csv", methods=["GET"])
@jwt_required()
def export_csv():
    """Export test history to a CSV file."""
    import io
    import csv
    from flask import Response

    user_id = get_jwt_identity()
    attempts = TestAttempt.query.filter_by(user_id=user_id).order_by(TestAttempt.completed_at.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)

    # Write header
    writer.writerow([
        "Attempt ID", "Category", "Difficulty", "Total Questions",
        "Correct Answers", "Accuracy (%)", "Time Taken (s)", "XP Earned", "Completed At"
    ])

    # Write data rows
    for a in attempts:
        cat_name = a.category.name if a.category else "Mixed"
        writer.writerow([
            a.id, cat_name, a.difficulty_level, a.total_questions,
            a.correct_answers, round(a.accuracy, 2), a.time_taken, a.xp_earned,
            a.completed_at.isoformat() if a.completed_at else ""
        ])

    response = Response(output.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=test_history.csv"
    return response


@tests_bp.route("/export/pdf", methods=["GET"])
@jwt_required()
def export_pdf():
    """Export progress report to a PDF file."""
    import io
    from flask import Response
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors

    user_id = get_jwt_identity()
    user = db.session.get(User, int(user_id))
    attempts = TestAttempt.query.filter_by(user_id=user_id).order_by(TestAttempt.completed_at.desc()).all()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=24,
        leading=28,
        textColor=colors.HexColor('#1A365D'),
        spaceAfter=15
    )

    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=12,
        leading=16,
        textColor=colors.HexColor('#4A5568'),
        spaceAfter=25
    )

    h2_style = ParagraphStyle(
        'H2Style',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=16,
        leading=20,
        textColor=colors.HexColor('#2B6CB0'),
        spaceBefore=15,
        spaceAfter=10
    )

    elements = []

    # Header Info
    username_str = user.username if user else "Student"
    xp_str = str(user.total_xp) if user else "0"
    streak_str = str(user.daily_streak) if user else "0"
    skill_str = f"{round((user.current_skill_level or 0.5) * 100)}%" if user else "50%"

    elements.append(Paragraph("Placement Preparation Platform", title_style))
    elements.append(Paragraph(f"Progress Report for: <b>{username_str}</b>", subtitle_style))

    # Stats Overview Table
    summary_data = [
        ["Total XP", "Daily Streak", "Skill Level", "Tests Attempted"],
        [xp_str, f"{streak_str} days", skill_str, str(len(attempts))]
    ]
    summary_table = Table(summary_data, colWidths=[120, 120, 120, 120])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#E2E8F0')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.HexColor('#2D3748')),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 10),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BACKGROUND', (0,1), (-1,1), colors.HexColor('#F7FAFC')),
        ('TEXTCOLOR', (0,1), (-1,1), colors.HexColor('#1A202C')),
        ('FONTNAME', (0,1), (-1,1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,1), (-1,1), 14),
        ('GRID', (0,0), (-1,-1), 1, colors.HexColor('#CBD5E0')),
    ]))

    elements.append(summary_table)
    elements.append(Spacer(1, 20))

    # Test History List
    elements.append(Paragraph("Recent Test Attempts", h2_style))

    history_data = [[
        "ID", "Category", "Difficulty", "Score / Qs", "Accuracy", "XP", "Date"
    ]]

    for a in attempts[:15]:
        cat_name = a.category.name if a.category else "Mixed"
        date_str = a.completed_at.strftime("%Y-%m-%d") if a.completed_at else ""
        history_data.append([
            str(a.id),
            cat_name,
            a.difficulty_level.capitalize() if a.difficulty_level else "Medium",
            f"{a.correct_answers} / {a.total_questions}",
            f"{round(a.accuracy, 1)}%",
            str(a.xp_earned),
            date_str
        ])

    history_table = Table(history_data, colWidths=[30, 150, 70, 100, 60, 40, 80])
    history_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2B6CB0')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 9),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F7FAFC')]),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
    ]))

    elements.append(history_table)

    # Build Document
    doc.build(elements)

    buffer.seek(0)
    response = Response(buffer.getvalue(), mimetype="application/pdf")
    response.headers["Content-Disposition"] = "attachment; filename=progress_report.pdf"
    return response
