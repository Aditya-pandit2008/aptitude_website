"""
app.py
Flask application factory.

Usage:
    flask --app app run                        # development
    gunicorn "app:create_app()"                # production
    FLASK_ENV=production flask --app app run   # env override
"""

import os
import time
from flask import Flask, abort, jsonify, render_template, send_from_directory
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from extensions import limiter
from config import config_map
from models import db


def create_app(env: str = None) -> Flask:
    """
    Create and configure the Flask application.

    Args:
        env: Configuration environment ('development' | 'testing' | 'production').
             Falls back to FLASK_ENV env variable, then 'default'.

    Returns:
        Configured Flask application instance.
    """
    backend_dir  = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.join(backend_dir, "template")
    static_dir   = os.path.join(backend_dir, "static")
    images_dir   = os.path.join(backend_dir, "images")

    app = Flask(
        __name__,
        template_folder=template_dir,
        static_folder=static_dir,
        static_url_path="/static",
    )

    # ── Load configuration ────────────────────────────────────────────────────
    env = env or os.getenv("FLASK_ENV", "default")
    cfg_cls = config_map.get(env, config_map["default"])
    # ProductionConfig.__init__ raises RuntimeError if default secrets are used
    cfg_obj = cfg_cls() if env == "production" else cfg_cls
    app.config.from_object(cfg_obj)

    # ── Extensions ────────────────────────────────────────────────────────────
    db.init_app(app)
    from flask_migrate import Migrate
    Migrate(app, db)

    jwt = JWTManager(app)
    _configure_jwt(app, jwt)

    allowed_origins = os.getenv("CORS_ORIGINS", "http://localhost:5000").split(",")
    CORS(app, resources={r"/api/*": {"origins": allowed_origins}},
         supports_credentials=True)

    limiter.init_app(app)

    # ── Structured logging ────────────────────────────────────────────────────
    from utils.logging_config import configure_logging
    configure_logging(app)

    # ── Blueprints ────────────────────────────────────────────────────────────
    _register_blueprints(app)

    # ── Database initialisation ───────────────────────────────────────────────
    with app.app_context():
        try:
            db.create_all()
            _seed_categories(app)
        except Exception as exc:  # noqa: BLE001
            app.logger.error("Database initialisation failed: %s", exc)

    # ── Global error handlers ─────────────────────────────────────────────────
    _register_error_handlers(app)

    # ── CLI commands ──────────────────────────────────────────────────────────
    _register_cli(app)

    return app


# ─────────────────────────────────────────────────────────────────────────────
# JWT configuration
# ─────────────────────────────────────────────────────────────────────────────

def _configure_jwt(app: Flask, jwt: JWTManager):
    """Wire the JWT token-in-blocklist callback and custom error messages."""
    from models import TokenBlocklist

    @jwt.token_in_blocklist_loader
    def check_if_token_revoked(jwt_header, jwt_payload):
        """Return True if the token's jti is in the blocklist (i.e. revoked)."""
        jti = jwt_payload.get("jti")
        return db.session.query(
            TokenBlocklist.query.filter_by(jti=jti).exists()
        ).scalar()

    @jwt.revoked_token_loader
    def revoked_token_callback(jwt_header, jwt_payload):
        return jsonify({
            "success": False,
            "error": "Token has been revoked. Please log in again.",
        }), 401

    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        return jsonify({
            "success": False,
            "error": "Token has expired. Please log in again.",
        }), 401

    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        return jsonify({
            "success": False,
            "error": "Invalid token. Please log in.",
        }), 401

    @jwt.unauthorized_loader
    def missing_token_callback(error):
        return jsonify({
            "success": False,
            "error": "Authorization token is missing.",
        }), 401


# ─────────────────────────────────────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────────────────────────────────────

def _register_blueprints(app: Flask):
    """Import and register all route blueprints."""
    from routes.auth        import auth_bp
    from routes.questions   import questions_bp
    from routes.tests       import tests_bp
    from routes.dashboard   import dashboard_bp
    from routes.leaderboard import leaderboard_bp
    from routes.bookmarks   import bookmarks_bp
    from routes.ai          import ai_bp
    from routes.admin       import admin_bp
    from routes.profile     import profile_bp

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
        return jsonify({"success": False, "error": "Bad Request", "message": str(e)}), 400

    @app.errorhandler(401)
    def unauthorized(e):
        return jsonify({"success": False, "error": "Unauthorized", "message": str(e)}), 401

    @app.errorhandler(403)
    def forbidden(e):
        return jsonify({"success": False, "error": "Forbidden", "message": str(e)}), 403

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"success": False, "error": "Not Found", "message": str(e)}), 404

    @app.errorhandler(422)
    def unprocessable(e):
        return jsonify({"success": False, "error": "Unprocessable Entity", "message": str(e)}), 422

    @app.errorhandler(429)
    def rate_limit_exceeded(e):
        return jsonify({
            "success": False,
            "error": "Too Many Requests",
            "message": "Rate limit exceeded. Please slow down.",
        }), 429

    @app.errorhandler(500)
    def internal_error(e):
        db.session.rollback()
        app.logger.exception("Unhandled 500 error: %s", e)
        return jsonify({"success": False, "error": "Internal Server Error"}), 500

    # ── Page routes ───────────────────────────────────────────────────────────

    @app.route("/health")
    def health():
        """
        Health-check endpoint.
        Verifies DB connectivity with a lightweight SELECT 1.
        """
        db_ok     = False
        db_latency = None
        try:
            t0 = time.perf_counter()
            db.session.execute(db.text("SELECT 1"))
            db_latency = round((time.perf_counter() - t0) * 1000, 2)
            db_ok = True
        except Exception as exc:  # noqa: BLE001
            app.logger.warning("Health check DB ping failed: %s", exc)

        status = 200 if db_ok else 503
        return jsonify({
            "status":      "ok" if db_ok else "degraded",
            "env":         os.getenv("FLASK_ENV", "default"),
            "db_ok":       db_ok,
            "db_latency_ms": db_latency,
        }), status

    @app.route("/")
    def home():
        return render_template("home.html")

    @app.route("/images/<path:filename>")
    def images(filename):
        return send_from_directory(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "images"),
            filename,
        )

    @app.route("/template/<path:page>")
    def template_page(page):
        if not page.endswith(".html"):
            abort(404)
        page_path = os.path.join(app.template_folder, page)
        if not os.path.isfile(page_path):
            abort(404)
        return render_template(page)

    @app.route("/<page>")
    def clean_page(page):
        template_name = f"{page}.html"
        page_path = os.path.join(app.template_folder, template_name)
        if not os.path.isfile(page_path):
            abort(404)
        return render_template(template_name)


def _register_cli(app: Flask):
    """Register Flask CLI commands."""
    import click

    @app.cli.command("make-admin")
    @click.argument("email")
    def make_admin(email):
        """Promote a user to admin. Usage: flask --app app make-admin EMAIL"""
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

    @app.cli.command("prune-blocklist")
    def prune_blocklist():
        """Remove expired tokens from the blocklist (run as a periodic job)."""
        from datetime import timedelta
        from models import TokenBlocklist
        cutoff = db.func.now() - timedelta(hours=1)
        deleted = TokenBlocklist.query.filter(TokenBlocklist.created_at < cutoff).delete()
        db.session.commit()
        click.echo(f"Pruned {deleted} expired tokens from blocklist.")


# ── Entry point ───────────────────────────────────────────────────────────────

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
