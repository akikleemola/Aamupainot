import sqlite3
from functools import wraps

from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = "vaihda-tama-salainen-avain"

DATABASE = "aamupainot.db"
SQL_FILE = "database.sql"


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
    connection.commit()
    connection.close()


def login_required(route_function):
    @wraps(route_function)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))

        return route_function(*args, **kwargs)

    return wrapper


@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    if request.method == "POST":
        date = request.form["date"]
        weight = request.form["weight"]

        connection = get_db_connection()
        connection.execute(
            get_sql("insert_weight_entry"),
            (session["user_id"], date, weight),
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

    return render_template(
        "index.html",
        weights=weights,
        chart_data=chart_data,
        username=session["username"],
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        password_confirm = request.form["password_confirm"]

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
        username = request.form["username"]
        password = request.form["password"]

        connection = get_db_connection()
        user = connection.execute(
            get_sql("select_user_by_username"),
            (username,),
        ).fetchone()
        connection.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("index"))

        flash("Käyttäjänimi tai salasana on väärin.")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


init_db()

if __name__ == "__main__":
    app.run(debug=True)
