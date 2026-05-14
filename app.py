import os
import re
import secrets
import sqlite3
from datetime import date
from datetime import datetime
from datetime import timedelta
from functools import wraps

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from hmac import compare_digest
from werkzeug.security import check_password_hash, generate_password_hash

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

DATABASE = "aamupainot.db"
SQL_FILE = "database.sql"
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{3,30}$")
MIN_PASSWORD_LENGTH = 4
MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCK_TIME = timedelta(minutes=5)
login_attempts = {}


def get_db_connection():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def get_sql(command_name):
    with open(SQL_FILE, encoding="utf-8") as sql_file:
        commands = sql_file.read().split("-- name: ")

    for command in commands:
        if command.startswith(command_name):
            return command.replace(command_name, "", 1).strip()

    raise ValueError(f"SQL-komentoa ei loytynyt: {command_name}")


def init_db():
    connection = get_db_connection()
    connection.execute(get_sql("create_users"))
    connection.execute(get_sql("create_weight_entries"))
    try:
        connection.execute(get_sql("add_user_id_to_weight_entries"))
    except sqlite3.OperationalError:
        pass
    connection.execute(get_sql("create_weight_entries_user_date_index"))
    connection.commit()
    connection.close()


def login_required(route_function):
    @wraps(route_function)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))

        return route_function(*args, **kwargs)

    return wrapper


def is_login_locked(username):
    attempts = login_attempts.get(username)

    if not attempts:
        return False

    locked_until = attempts.get("locked_until")

    if locked_until and locked_until > datetime.now():
        return True

    if locked_until:
        login_attempts.pop(username, None)

    return False


def record_failed_login(username):
    attempts = login_attempts.setdefault(username, {"count": 0, "locked_until": None})
    attempts["count"] += 1

    if attempts["count"] >= MAX_LOGIN_ATTEMPTS:
        attempts["locked_until"] = datetime.now() + LOGIN_LOCK_TIME


def clear_failed_logins(username):
    login_attempts.pop(username, None)


def format_date(date_text):
    return date.fromisoformat(date_text).strftime("%d/%m/%Y")


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


@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    if request.method == "POST":
        date_text = request.form["date"]
        weight_text = request.form["weight"]

        try:
            date.fromisoformat(date_text)
            weight = float(weight_text)
        except ValueError:
            flash("Tarkista päivämäärä ja paino.")
            return redirect(url_for("index"))

        if weight <= 0 or weight > 500:
            flash("Painon pitää olla välillä 0-500 kg.")
            return redirect(url_for("index"))

        connection = get_db_connection()
        connection.execute(
            get_sql("insert_weight_entry"),
            (session["user_id"], date_text, weight),
        )
        connection.commit()
        connection.close()

        return redirect(url_for("index"))

    connection = get_db_connection()
    weights = connection.execute(
        get_sql("select_weight_entries_for_user"),
        (session["user_id"],),
    ).fetchall()
    connection.close()

    chart_data = [
        {"date": item["date"], "weight": item["weight"]}
        for item in reversed(weights)
    ]
    latest_weight = chart_data[-1]["weight"] if chart_data else None
    latest_date = format_date(chart_data[-1]["date"]) if chart_data else None
    first_weight = chart_data[0]["weight"] if chart_data else None
    total_change = None
    display_weights = [
        {
            "date": format_date(item["date"]),
            "weight": item["weight"],
        }
        for item in weights
    ]

    if latest_weight is not None and first_weight is not None:
        total_change = round(latest_weight - first_weight, 1)

    return render_template(
        "index.html",
        weights=display_weights,
        chart_data=chart_data,
        latest_date=latest_date,
        latest_weight=latest_weight,
        total_change=total_change,
        weight_count=len(chart_data),
        username=session["username"],
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        password_confirm = request.form["password_confirm"]

        if not USERNAME_PATTERN.fullmatch(username):
            flash("Käyttäjänimessä saa olla 3-30 kirjainta, numeroa tai alaviivaa.")
            return redirect(url_for("register"))

        if len(password) < MIN_PASSWORD_LENGTH:
            flash(f"Salasanan pitää olla vähintään {MIN_PASSWORD_LENGTH} merkkiä pitkä.")
            return redirect(url_for("register"))

        if password != password_confirm:
            flash("Salasanat eivät täsmää.")
            return redirect(url_for("register"))

        password_hash = generate_password_hash(password)

        connection = get_db_connection()
        existing_user = connection.execute(
            get_sql("select_user_by_username"),
            (username,),
        ).fetchone()

        if existing_user:
            connection.close()
            flash("Käyttäjänimi on jo käytössä.")
            return redirect(url_for("register"))

        connection.execute(get_sql("insert_user"), (username, password_hash))
        connection.commit()
        connection.close()

        flash("Tunnus luotu. Voit nyt kirjautua sisään.")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        if is_login_locked(username):
            flash("Liian monta epäonnistunutta kirjautumisyritystä. Yritä hetken päästä uudelleen.")
            return redirect(url_for("login"))

        connection = get_db_connection()
        user = connection.execute(
            get_sql("select_user_by_username"),
            (username,),
        ).fetchone()
        connection.close()

        if user and check_password_hash(user["password_hash"], password):
            clear_failed_logins(username)
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("index"))

        record_failed_login(username)
        flash("Käyttäjänimi tai salasana on väärin.")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


init_db()

if __name__ == "__main__":
    app.run(debug=APP_ENV == "development")
