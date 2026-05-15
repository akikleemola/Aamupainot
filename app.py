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
MIN_WEIGHT = 20
MAX_WEIGHT = 250
MAX_NOTE_LENGTH = 200
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
    try:
        connection.execute(get_sql("add_target_weight_to_users"))
    except sqlite3.OperationalError:
        pass
    connection.execute(get_sql("create_weight_entries"))
    try:
        connection.execute(get_sql("add_user_id_to_weight_entries"))
    except sqlite3.OperationalError:
        pass
    try:
        connection.execute(get_sql("add_note_to_weight_entries"))
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


def parse_date_input(date_text):
    date_text = date_text.strip()

    for date_format in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_text, date_format).date().isoformat()
        except ValueError:
            pass

    raise ValueError


def validate_weight_entry(date_text, weight_text):
    try:
        date_text = parse_date_input(date_text)
        weight = float(weight_text)
    except ValueError:
        return None, None, "Tarkista päivämäärä muodossa pp/kk/vvvv ja paino."

    if weight < MIN_WEIGHT or weight > MAX_WEIGHT:
        return None, None, f"Painon pitää olla välillä {MIN_WEIGHT}-{MAX_WEIGHT} kg."

    return date_text, weight, None


def validate_note(note_text):
    note = note_text.strip()

    if len(note) > MAX_NOTE_LENGTH:
        return None, f"Muistiinpano saa olla enintään {MAX_NOTE_LENGTH} merkkiä pitkä."

    return note, None


def validate_target_weight(weight_text):
    weight_text = weight_text.strip()

    if not weight_text:
        return None, None

    try:
        weight = float(weight_text)
    except ValueError:
        return None, "Tarkista tavoitepaino."

    if weight < MIN_WEIGHT or weight > MAX_WEIGHT:
        return None, f"Tavoitepainon pitää olla välillä {MIN_WEIGHT}-{MAX_WEIGHT} kg."

    return weight, None


def build_display_weights(weights):
    oldest_first = list(reversed(weights))
    previous_weights = {}

    for index, item in enumerate(oldest_first):
        if index == 0:
            previous_weights[item["id"]] = None
        else:
            previous_weights[item["id"]] = oldest_first[index - 1]["weight"]

    display_weights = []

    for item in weights:
        previous_weight = previous_weights[item["id"]]
        change = None

        if previous_weight is not None:
            change = round(item["weight"] - previous_weight, 1)

        if change is None:
            change_status = "neutral"
        elif change > 0:
            change_status = "up"
        elif change < 0:
            change_status = "down"
        else:
            change_status = "same"

        display_weights.append(
            {
                "id": item["id"],
                "date": format_date(item["date"]),
                "date_value": item["date"],
                "weight": item["weight"],
                "note": item["note"],
                "change": change,
                "change_status": change_status,
            }
        )

    return display_weights


def get_redirect_target():
    redirect_target = request.form.get("redirect_target", "index")

    if redirect_target not in ("index", "history"):
        return "index"

    return redirect_target


def get_redirect_url():
    redirect_target = get_redirect_target()

    if redirect_target == "history":
        history_range = request.form.get("history_range", "all")

        if history_range in ("14", "30"):
            return url_for("history", range=history_range)

    return url_for(redirect_target)


def date_already_has_weight(connection, user_id, date_text, entry_id=None):
    if entry_id is None:
        existing_entry = connection.execute(
            get_sql("select_weight_entry_for_user_date"),
            (user_id, date_text),
        ).fetchone()
    else:
        existing_entry = connection.execute(
            get_sql("select_other_weight_entry_for_user_date"),
            (user_id, date_text, entry_id),
        ).fetchone()

    return existing_entry is not None


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
        note_text = request.form.get("note", "")
        date_text, weight, error = validate_weight_entry(date_text, weight_text)

        if error:
            flash(error)
            return redirect(url_for("index"))

        note, error = validate_note(note_text)

        if error:
            flash(error)
            return redirect(url_for("index"))

        connection = get_db_connection()
        if date_already_has_weight(connection, session["user_id"], date_text):
            connection.close()
            flash("Tälle päivälle on jo painomerkintä.")
            return redirect(url_for("index"))

        connection.execute(
            get_sql("insert_weight_entry"),
            (session["user_id"], date_text, weight, note),
        )
        connection.commit()
        connection.close()

        return redirect(url_for("index"))

    connection = get_db_connection()
    weights = connection.execute(
        get_sql("select_weight_entries_for_user"),
        (session["user_id"],),
    ).fetchall()
    user_settings = connection.execute(
        get_sql("select_user_settings"),
        (session["user_id"],),
    ).fetchone()
    connection.close()

    if user_settings is None:
        session.clear()
        return redirect(url_for("login"))

    chart_data = [
        {"date": item["date"], "weight": item["weight"]}
        for item in reversed(weights)
    ]
    latest_weight = chart_data[-1]["weight"] if chart_data else None
    latest_date = format_date(chart_data[-1]["date"]) if chart_data else None
    first_weight = chart_data[0]["weight"] if chart_data else None
    previous_weight = chart_data[-2]["weight"] if len(chart_data) >= 2 else None
    previous_change = None
    recent_average = None
    recent_average_count = min(len(chart_data), 7)
    target_weight = user_settings["target_weight"]
    target_difference = None
    target_status = None
    total_change = None
    display_weights = build_display_weights(weights)
    latest_display_weights = display_weights[:5]

    if latest_weight is not None and first_weight is not None:
        total_change = round(latest_weight - first_weight, 1)

    if latest_weight is not None and previous_weight is not None:
        previous_change = round(latest_weight - previous_weight, 1)

    if chart_data:
        recent_weights = [item["weight"] for item in chart_data[-7:]]
        recent_average = round(sum(recent_weights) / len(recent_weights), 1)

    if target_weight is not None and latest_weight is not None:
        target_difference = round(abs(latest_weight - target_weight), 1)

        if latest_weight > target_weight:
            target_status = "above"
        elif latest_weight < target_weight:
            target_status = "below"
        else:
            target_status = "reached"

    return render_template(
        "index.html",
        weights=latest_display_weights,
        chart_data=chart_data,
        latest_date=latest_date,
        latest_weight=latest_weight,
        previous_change=previous_change,
        recent_average=recent_average,
        recent_average_count=recent_average_count,
        target_difference=target_difference,
        target_status=target_status,
        target_weight=target_weight,
        total_change=total_change,
        username=session["username"],
    )


@app.route("/history")
@login_required
def history():
    active_range = request.args.get("range", "all")

    if active_range not in ("all", "14", "30"):
        active_range = "all"

    connection = get_db_connection()
    weights = connection.execute(
        get_sql("select_weight_entries_for_user"),
        (session["user_id"],),
    ).fetchall()
    connection.close()

    display_weights = build_display_weights(weights)

    if active_range != "all":
        cutoff_date = date.today() - timedelta(days=int(active_range) - 1)
        display_weights = [
            item for item in display_weights
            if date.fromisoformat(item["date_value"]) >= cutoff_date
        ]

    return render_template(
        "history.html",
        active_range=active_range,
        weights=display_weights,
        username=session["username"],
    )


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        action = request.form.get("action")

        if action == "target_weight":
            target_weight_text = request.form.get("target_weight", "")
            target_weight, error = validate_target_weight(target_weight_text)

            if error:
                flash(error)
                return redirect(url_for("settings"))

            connection = get_db_connection()
            connection.execute(
                get_sql("update_user_settings"),
                (target_weight, session["user_id"]),
            )
            connection.commit()
            connection.close()

            flash("Tavoitepaino tallennettu.")
            return redirect(url_for("settings"))

        if action == "username":
            username = request.form.get("username", "").strip()

            if not USERNAME_PATTERN.fullmatch(username):
                flash("Käyttäjänimessä saa olla 3-30 kirjainta, numeroa tai alaviivaa.")
                return redirect(url_for("settings"))

            if username == session["username"]:
                flash("Käyttäjänimi on jo käytössäsi.")
                return redirect(url_for("settings"))

            connection = get_db_connection()
            existing_user = connection.execute(
                get_sql("select_user_by_username"),
                (username,),
            ).fetchone()

            if existing_user:
                connection.close()
                flash("Käyttäjänimi on jo käytössä.")
                return redirect(url_for("settings"))

            connection.execute(
                get_sql("update_username"),
                (username, session["user_id"]),
            )
            connection.commit()
            connection.close()

            session["username"] = username
            flash("Käyttäjänimi päivitetty.")
            return redirect(url_for("settings"))

        if action == "password":
            current_password = request.form.get("current_password", "")
            new_password = request.form.get("new_password", "")
            new_password_confirm = request.form.get("new_password_confirm", "")

            connection = get_db_connection()
            user = connection.execute(
                get_sql("select_user_by_id"),
                (session["user_id"],),
            ).fetchone()

            if not user:
                connection.close()
                session.clear()
                return redirect(url_for("login"))

            if not check_password_hash(user["password_hash"], current_password):
                connection.close()
                flash("Nykyinen salasana on väärin.")
                return redirect(url_for("settings"))

            if len(new_password) < MIN_PASSWORD_LENGTH:
                connection.close()
                flash(f"Uuden salasanan pitää olla vähintään {MIN_PASSWORD_LENGTH} merkkiä pitkä.")
                return redirect(url_for("settings"))

            if new_password != new_password_confirm:
                connection.close()
                flash("Uudet salasanat eivät täsmää.")
                return redirect(url_for("settings"))

            password_hash = generate_password_hash(new_password)
            connection.execute(
                get_sql("update_password"),
                (password_hash, session["user_id"]),
            )
            connection.commit()
            connection.close()

            flash("Salasana päivitetty.")
            return redirect(url_for("settings"))

        flash("Asetuksia ei voitu tallentaa.")
        return redirect(url_for("settings"))

    connection = get_db_connection()
    user_settings = connection.execute(
        get_sql("select_user_settings"),
        (session["user_id"],),
    ).fetchone()
    connection.close()

    if user_settings is None:
        session.clear()
        return redirect(url_for("login"))

    return render_template(
        "settings.html",
        target_weight=user_settings["target_weight"],
        username=user_settings["username"],
    )


@app.route("/weights/<int:entry_id>/edit", methods=["POST"])
@login_required
def edit_weight(entry_id):
    redirect_url = get_redirect_url()
    date_text = request.form["date"]
    weight_text = request.form["weight"]
    note_text = request.form.get("note", "")
    date_text, weight, error = validate_weight_entry(date_text, weight_text)

    if error:
        flash(error)
        return redirect(redirect_url)

    note, error = validate_note(note_text)

    if error:
        flash(error)
        return redirect(redirect_url)

    connection = get_db_connection()
    if date_already_has_weight(connection, session["user_id"], date_text, entry_id):
        connection.close()
        flash("Tälle päivälle on jo painomerkintä.")
        return redirect(redirect_url)

    connection.execute(
        get_sql("update_weight_entry"),
        (date_text, weight, note, entry_id, session["user_id"]),
    )
    connection.commit()
    connection.close()

    flash("Merkintä päivitetty.")
    return redirect(redirect_url)


@app.route("/weights/<int:entry_id>/delete", methods=["POST"])
@login_required
def delete_weight(entry_id):
    redirect_url = get_redirect_url()
    connection = get_db_connection()
    connection.execute(
        get_sql("delete_weight_entry"),
        (entry_id, session["user_id"]),
    )
    connection.commit()
    connection.close()

    flash("Merkintä poistettu.")
    return redirect(redirect_url)


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
