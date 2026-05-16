import os
import secrets

from flask import Flask, abort, render_template, request, session
from hmac import compare_digest

from db import init_db
from users import register_user_routes
from weights import register_weight_routes

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
APP_ENV = os.environ.get("APP_ENV", "development")

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=APP_ENV == "production",
)

if app.secret_key == "dev-secret-key-change-me":
    print("VAROITUS: SECRET_KEY ei ole asetettu. Käytössä on vain kehitykseen sopiva oletusavain.")


def get_csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)

    return session["csrf_token"]


@app.context_processor
def add_csrf_token_to_templates():
    return {"csrf_token": get_csrf_token}


@app.before_request
def protect_against_csrf():
    if request.method != "POST":
        return

    session_token = session.get("csrf_token")
    form_token = request.form.get("csrf_token")

    if not session_token or not form_token or not compare_digest(session_token, form_token):
        abort(400)


@app.after_request
def add_security_headers(response):
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self'; "
        "img-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'none'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


@app.errorhandler(400)
def bad_request(error):
    return render_template(
        "error.html",
        error_code=400,
        error_title="Pyyntöä ei voitu käsitellä",
        error_message="Palaa takaisin ja yritä uudelleen.",
    ), 400


@app.errorhandler(404)
def page_not_found(error):
    return render_template(
        "error.html",
        error_code=404,
        error_title="Sivua ei löytynyt",
        error_message="Tarkista osoite tai palaa sovellukseen.",
    ), 404


@app.errorhandler(500)
def internal_server_error(error):
    return render_template(
        "error.html",
        error_code=500,
        error_title="Jokin meni pieleen",
        error_message="Yritä hetken päästä uudelleen.",
    ), 500


register_weight_routes(app)
register_user_routes(app)
init_db()

if __name__ == "__main__":
    app.run(debug=APP_ENV == "development")
