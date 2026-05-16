import re
from datetime import datetime
from datetime import timedelta
from functools import wraps

from flask import flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from db import get_db_connection, get_sql


USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{3,30}$")
MIN_PASSWORD_LENGTH = 4
MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCK_TIME = timedelta(minutes=5)
MIN_WEIGHT = 20
MAX_WEIGHT = 250
login_attempts = {}


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


def get_current_user():
    connection = get_db_connection()
    user = connection.execute(
        get_sql("select_user_by_id"),
        (session["user_id"],),
    ).fetchone()
    connection.close()

    return user


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


def validate_chart_settings(line_type, show_target_line):
    if line_type not in ("exact", "smoothed"):
        return None, None, "Valitse painoviivan tyyppi."

    return line_type, 1 if show_target_line == "1" else 0, None


def register_user_routes(app):
    @app.route("/settings", methods=["GET", "POST"])
    @login_required
    def settings():
        if request.method == "POST":
            action = request.form.get("action")

            if action == "target_weight":
                target_weight_text = request.form.get("target_weight", "")
                target_weight, error = validate_target_weight(target_weight_text)

                if error:
                    flash(error, "error")
                    return redirect(url_for("settings"))

                connection = get_db_connection()
                connection.execute(
                    get_sql("update_user_settings"),
                    (target_weight, session["user_id"]),
                )
                connection.commit()
                connection.close()

                flash("Tavoitepaino tallennettu.", "success")
                return redirect(url_for("settings"))

            if action == "chart_settings":
                line_type = request.form.get("chart_line_type", "exact")
                show_target_line = request.form.get("show_target_line", "0")
                line_type, show_target_line, error = validate_chart_settings(line_type, show_target_line)

                if error:
                    flash(error, "error")
                    return redirect(url_for("settings"))

                connection = get_db_connection()
                connection.execute(
                    get_sql("update_chart_settings"),
                    (line_type, show_target_line, session["user_id"]),
                )
                connection.commit()
                connection.close()

                flash("Kaavion asetukset tallennettu.", "success")
                return redirect(url_for("settings"))

            if action == "username":
                username = request.form.get("username", "").strip()

                if not USERNAME_PATTERN.fullmatch(username):
                    flash("Käyttäjänimessä saa olla 3-30 kirjainta, numeroa tai alaviivaa.", "error")
                    return redirect(url_for("settings"))

                if username == session["username"]:
                    flash("Käyttäjänimi on jo käytössäsi.", "info")
                    return redirect(url_for("settings"))

                connection = get_db_connection()
                existing_user = connection.execute(
                    get_sql("select_user_by_username"),
                    (username,),
                ).fetchone()

                if existing_user:
                    connection.close()
                    flash("Käyttäjänimi on jo käytössä.", "error")
                    return redirect(url_for("settings"))

                connection.execute(
                    get_sql("update_username"),
                    (username, session["user_id"]),
                )
                connection.commit()
                connection.close()

                session["username"] = username
                flash("Käyttäjänimi päivitetty.", "success")
                return redirect(url_for("settings"))

            if action == "password":
                current_password = request.form.get("current_password", "")
                new_password = request.form.get("new_password", "")
                new_password_confirm = request.form.get("new_password_confirm", "")

                user = get_current_user()
                if not user:
                    session.clear()
                    return redirect(url_for("login"))

                if not check_password_hash(user["password_hash"], current_password):
                    flash("Nykyinen salasana on väärin.", "error")
                    return redirect(url_for("settings"))

                if len(new_password) < MIN_PASSWORD_LENGTH:
                    flash(f"Uuden salasanan pitää olla vähintään {MIN_PASSWORD_LENGTH} merkkiä pitkä.", "error")
                    return redirect(url_for("settings"))

                if new_password != new_password_confirm:
                    flash("Uudet salasanat eivät täsmää.", "error")
                    return redirect(url_for("settings"))

                password_hash = generate_password_hash(new_password)
                connection = get_db_connection()
                connection.execute(
                    get_sql("update_password"),
                    (password_hash, session["user_id"]),
                )
                connection.commit()
                connection.close()

                flash("Salasana päivitetty.", "success")
                return redirect(url_for("settings"))

            flash("Asetuksia ei voitu tallentaa.", "error")
            return redirect(url_for("settings"))

        user = get_current_user()
        if not user:
            session.clear()
            return redirect(url_for("login"))

        return render_template(
            "settings.html",
            chart_line_type=user["chart_line_type"],
            show_target_line=user["show_target_line"],
            target_weight=user["target_weight"],
            username=user["username"],
        )

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            username = request.form["username"].strip()
            password = request.form["password"]
            password_confirm = request.form["password_confirm"]

            if not USERNAME_PATTERN.fullmatch(username):
                flash("Käyttäjänimessä saa olla 3-30 kirjainta, numeroa tai alaviivaa.", "error")
                return redirect(url_for("register"))

            if len(password) < MIN_PASSWORD_LENGTH:
                flash(f"Salasanan pitää olla vähintään {MIN_PASSWORD_LENGTH} merkkiä pitkä.", "error")
                return redirect(url_for("register"))

            if password != password_confirm:
                flash("Salasanat eivät täsmää.", "error")
                return redirect(url_for("register"))

            password_hash = generate_password_hash(password)

            connection = get_db_connection()
            existing_user = connection.execute(
                get_sql("select_user_by_username"),
                (username,),
            ).fetchone()

            if existing_user:
                connection.close()
                flash("Käyttäjänimi on jo käytössä.", "error")
                return redirect(url_for("register"))

            connection.execute(get_sql("insert_user"), (username, password_hash))
            connection.commit()
            connection.close()

            flash("Tunnus luotu. Voit nyt kirjautua sisään.", "success")
            return redirect(url_for("login"))

        return render_template("register.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = request.form["username"].strip()
            password = request.form["password"]

            if is_login_locked(username):
                flash("Liian monta epäonnistunutta kirjautumisyritystä. Yritä hetken päästä uudelleen.", "error")
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
            flash("Käyttäjänimi tai salasana on väärin.", "error")

        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))
