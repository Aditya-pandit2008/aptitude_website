"""
app.py
Flask application factory.

Usage:
    flask --app app run                        # development
    gunicorn "app:create_app()"                # production
    FLASK_ENV=production flask --app app run   # env override
"""

import os
from flask import Flask, abort, jsonify, render_template, send_from_directory
from flask_jwt_extended import JWTManager
from flask_cors import CORS

from config import config_map
from models import db


def create_app(env: str = None) -> Flask:
    """
    Create and configure the Flask application.

    Args:
        env: Configuration environment name ('development' | 'testing' | 'production').
             Falls back to FLASK_ENV env variable, then 'default'.

    Returns:
        Configured Flask application instance.
    """
    # template/static/images live INSIDE backend/ on purpose: Vercel bundles
    # the entrypoint's own directory, not arbitrary sibling folders from the
    # repo root, so these must travel alongside app.py to be deployed at all.
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.join(backend_dir, "template")
    static_dir = os.path.join(backend_dir, "static")
    images_dir = os.path.join(backend_dir, "images")


    app = Flask(
        __name__,
        template_folder=template_dir,
        static_folder=static_dir,
        static_url_path="/static",
    )
    

    # ── Load configuration ────────────────────────────────────────────────────
    env = env or os.getenv("FLASK_ENV", "default")
    app.config.from_object(config_map.get(env, config_map["default"]))

    # ── Extensions ────────────────────────────────────────────────────────────
    db.init_app(app)
    JWTManager(app)
    allowed_origins = os.getenv("CORS_ORIGINS", "*").split(",")
    CORS(app, resources={r"/api/*": {"origins": allowed_origins}})

    # ── Blueprints ────────────────────────────────────────────────────────────
    _register_blueprints(app)

    # ── Database initialisation ───────────────────────────────────────────────
    with app.app_context():
        try:
            db.create_all()
            _seed_categories(app)
        except Exception as exc:  # noqa: BLE001
            # Don't let a DB hiccup take down the whole serverless function —
            # log it and let individual routes fail gracefully instead.
            app.logger.error("Database initialisation failed: %s", exc)

    # ── Global error handlers ─────────────────────────────────────────────────
    _register_error_handlers(app)

    # ── CLI: make-admin ──────────────────────────────────────────────────────
    import click

    @app.cli.command("make-admin")
    @click.argument("email")
    def make_admin(email):
        """Promote a user to admin role.  Usage: flask --app app make-admin EMAIL"""
        from models import User
        user = User.query.filter_by(email=email.strip().lower()).first()
        if not user:
            click.echo(f"No user found: {email}", err=True)
            return
        user.role = "admin"
        db.session.commit()
        click.echo(f"OK – {user.username} ({user.email}) is now admin.")

    @app.cli.command("list-users")
    def list_users():
        """List all registered users."""
        from models import User
        for u in User.query.order_by(User.created_at).all():
            click.echo(f"  [{u.role:8}]  {u.username:20}  {u.email}")

        # ── Health-check route ────────────────────────────────────────────────────
    @app.route("/health")
    def health():
        return jsonify({"status": "ok", "env": env}), 200

    @app.route("/")
    def home():
        return render_template("home.html")

    @app.route("/images/<path:filename>")
    def images(filename):
        return send_from_directory(images_dir, filename)

    @app.route("/template/<path:page>")
    def template_page(page):
        if not page.endswith(".html"):
            abort(404)

        page_path = os.path.join(template_dir, page)
        if not os.path.isfile(page_path):
            abort(404)

        return render_template(page)

    @app.route("/<page>")
    def clean_page(page):
        template_name = f"{page}.html"
        page_path = os.path.join(template_dir, template_name)
        if not os.path.isfile(page_path):
            abort(404)

        return render_template(template_name)

    return app


# ─────────────────────────────────────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────────────────────────────────────

def _register_blueprints(app: Flask):
    """Import and register all route blueprints."""
    from routes.auth import auth_bp
    from routes.questions import questions_bp
    from routes.tests import tests_bp
    from routes.dashboard import dashboard_bp
    from routes.leaderboard import leaderboard_bp
    from routes.bookmarks import bookmarks_bp
    from routes.ai import ai_bp
    from routes.admin import admin_bp
    from routes.profile import profile_bp

    prefix = "/api/v1"
    app.register_blueprint(auth_bp,        url_prefix=f"{prefix}/auth")
    app.register_blueprint(questions_bp,   url_prefix=f"{prefix}/questions")
    app.register_blueprint(tests_bp,       url_prefix=f"{prefix}/tests")
    app.register_blueprint(dashboard_bp,   url_prefix=f"{prefix}/dashboard")
    app.register_blueprint(leaderboard_bp, url_prefix=f"{prefix}/leaderboard")
    app.register_blueprint(bookmarks_bp,   url_prefix=f"{prefix}/bookmarks")
    app.register_blueprint(ai_bp,          url_prefix=f"{prefix}/ai")
    app.register_blueprint(admin_bp,       url_prefix=f"{prefix}/admin")
    app.register_blueprint(profile_bp,     url_prefix=f"{prefix}/profile")


def _seed_categories(app: Flask):
    """Insert default categories if the table is empty."""
    from models import Category

    if Category.query.count() > 0:
        return

    defaults = [
        {"name": "Quantitative Aptitude",  "description": "Number theory, arithmetic, algebra", "icon": "🔢"},
        {"name": "Logical Reasoning",      "description": "Patterns, sequences, deductions",    "icon": "🧠"},
        {"name": "Verbal Ability",         "description": "Grammar, vocabulary, comprehension", "icon": "📖"},
        {"name": "Data Interpretation",    "description": "Charts, graphs, tables",             "icon": "📊"},
        {"name": "Technical - DSA",        "description": "Arrays, trees, graphs, algorithms",  "icon": "💻"},
        {"name": "Technical - DBMS",       "description": "SQL, normalisation, transactions",   "icon": "🗄️"},
        {"name": "Technical - OS",         "description": "Processes, memory, scheduling",      "icon": "⚙️"},
        {"name": "Technical - Networks",   "description": "TCP/IP, HTTP, DNS, OSI model",       "icon": "🌐"},
        {"name": "HR & Behavioural",       "description": "Soft skills and situational Qs",     "icon": "🤝"},
    ]

    for item in defaults:
        db.session.add(Category(**item))

    try:
        db.session.commit()
        app.logger.info("Seeded %d default categories.", len(defaults))
    except Exception as exc:
            db.session.rollback()
            app.logger.warning("Category seed failed: %s", exc)



def _register_error_handlers(app: Flask):
    """Register global JSON error responses."""

    @app.errorhandler(400)
    def bad_request(e):
        return jsonify({"error": "Bad Request", "message": str(e)}), 400

    @app.errorhandler(401)
    def unauthorized(e):
        return jsonify({"error": "Unauthorized", "message": str(e)}), 401

    @app.errorhandler(403)
    def forbidden(e):
        return jsonify({"error": "Forbidden", "message": str(e)}), 403

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Not Found", "message": str(e)}), 404

    @app.errorhandler(422)
    def unprocessable(e):
        return jsonify({"error": "Unprocessable Entity", "message": str(e)}), 422

    @app.errorhandler(500)
    def internal_error(e):
        db.session.rollback()
        return jsonify({"error": "Internal Server Error", "message": str(e)}), 500


# ── Entry point ───────────────────────────────────────────────────────────────

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
