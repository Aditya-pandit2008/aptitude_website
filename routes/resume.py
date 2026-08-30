import io
import os
import zipfile

from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.utils import secure_filename

from models import db, User, ResumeAnalysis
from services import ai_service
from utils.response import success, error

resume_bp = Blueprint("resume", __name__)

ALLOWED_EXTENSIONS = {
    "txt", "md", "csv", "json", "rtf",
    "pdf", "doc", "docx",
    "png", "jpg", "jpeg", "bmp", "gif", "webp"
}


def _decode_text_bytes(raw: bytes, fallback_name: str = "resume") -> str:
    for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def _extract_text_from_pdf(file_obj) -> str:
    try:
        import PyPDF2
        reader = PyPDF2.PdfReader(file_obj)
        text_parts = []
        for page in reader.pages:
            text = page.extract_text() or ""
            if text:
                text_parts.append(text)
        return "\n".join(text_parts).strip()
    except Exception:
        pass

    try:
        from pypdf import PdfReader
        reader = PdfReader(file_obj)
        text_parts = []
        for page in reader.pages:
            text = page.extract_text() or ""
            if text:
                text_parts.append(text)
        return "\n".join(text_parts).strip()
    except Exception:
        pass

    try:
        import fitz
        doc = fitz.open(stream=file_obj.read(), filetype="pdf")
        text_parts = []
        for page in doc:
            text = page.get_text("text") or ""
            if text:
                text_parts.append(text)
        return "\n".join(text_parts).strip()
    except Exception:
        return ""


def _extract_text_from_docx(file_obj) -> str:
    try:
        import docx
        doc = docx.Document(file_obj)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n".join(paragraphs).strip()
    except Exception:
        pass

    try:
        file_obj.seek(0)
        with zipfile.ZipFile(file_obj) as zf:
            if "word/document.xml" in zf.namelist():
                xml = zf.read("word/document.xml")
                import re
                text = re.sub(r"<.*?>", "\n", xml.decode("utf-8", errors="ignore"))
                return "\n".join(line.strip() for line in text.splitlines() if line.strip())
    except Exception:
        pass
    return ""


def _extract_text_from_image(file_obj, filename: str) -> str:
    try:
        import pytesseract
        from PIL import Image
        file_obj.seek(0)
        image = Image.open(io.BytesIO(file_obj.read()))
        image = image.convert("RGB")
        text = pytesseract.image_to_string(image)
        if text and text.strip():
            return text.strip()
    except Exception:
        pass

    return f"Uploaded resume file: {filename}. OCR is unavailable in this environment, so please paste the text manually or install Tesseract OCR for automatic extraction."


def _extract_uploaded_resume_text(file_storage) -> str:
    if file_storage is None:
        return ""

    filename = secure_filename(file_storage.filename or "resume")
    ext = (filename.rsplit(".", 1)[-1] or "").lower()
    if ext not in ALLOWED_EXTENSIONS:
        return ""

    file_storage.seek(0)
    raw = file_storage.read()
    if not raw:
        return ""

    if ext in {"txt", "md", "csv", "json", "rtf"}:
        return _decode_text_bytes(raw, filename).strip()

    if ext == "pdf":
        file_obj = io.BytesIO(raw)
        return _extract_text_from_pdf(file_obj)

    if ext in {"doc", "docx"}:
        file_obj = io.BytesIO(raw)
        return _extract_text_from_docx(file_obj)

    if ext in {"png", "jpg", "jpeg", "bmp", "gif", "webp"}:
        file_obj = io.BytesIO(raw)
        return _extract_text_from_image(file_obj, filename)

    return _decode_text_bytes(raw, filename).strip()


@resume_bp.route("/analyze", methods=["POST"])
@jwt_required()
def analyze_resume():
    """Analyze a resume text or uploaded resume file for ATS suitability."""
    user_id = int(get_jwt_identity())

    uploaded_file = request.files.get("resume_file")
    resume_text = ""
    job_description = ""

    if uploaded_file and uploaded_file.filename:
        resume_text = _extract_uploaded_resume_text(uploaded_file) or ""
        job_description = (request.form.get("job_description") or "").strip()
    else:
        data = request.get_json(silent=True) or {}
        resume_text = (data.get("resume_text") or "").strip()
        job_description = (data.get("job_description") or "").strip()

    if not resume_text:
        return error("resume_text or a valid resume file is required.", 422)

    try:
        analysis = ai_service.analyze_resume_ats(resume_text, job_description)
        ats_score = analysis["ats_score"]
        feedback = analysis["feedback"]
        improvements = analysis["improvements"]
        skills_detected = analysis["skills_detected"]
        skills_gap = analysis["skills_gap"]

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
