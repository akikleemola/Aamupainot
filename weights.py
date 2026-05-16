from datetime import date
from datetime import datetime
from datetime import timedelta

from flask import flash, redirect, render_template, request, session, url_for

from db import get_db_connection, get_sql
from users import login_required


MIN_WEIGHT = 20
MAX_WEIGHT = 250
MAX_NOTE_LENGTH = 200


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


def register_weight_routes(app):
    @app.route("/", methods=["GET", "POST"])
    @login_required
    def index():
        if request.method == "POST":
            date_text = request.form["date"]
            weight_text = request.form["weight"]
            note_text = request.form.get("note", "")
            date_text, weight, error = validate_weight_entry(date_text, weight_text)

            if error:
                flash(error, "error")
                return redirect(url_for("index"))

            note, error = validate_note(note_text)

            if error:
                flash(error, "error")
                return redirect(url_for("index"))

            connection = get_db_connection()
            if date_already_has_weight(connection, session["user_id"], date_text):
                connection.close()
                flash("Tälle päivälle on jo painomerkintä.", "error")
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
        chart_line_type = user_settings["chart_line_type"]
        show_target_line = user_settings["show_target_line"] == 1
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
            chart_line_type=chart_line_type,
            show_target_line=show_target_line,
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

    @app.route("/weights/<int:entry_id>/edit", methods=["POST"])
    @login_required
    def edit_weight(entry_id):
        redirect_url = get_redirect_url()
        date_text = request.form["date"]
        weight_text = request.form["weight"]
        note_text = request.form.get("note", "")
        date_text, weight, error = validate_weight_entry(date_text, weight_text)

        if error:
            flash(error, "error")
            return redirect(redirect_url)

        note, error = validate_note(note_text)

        if error:
            flash(error, "error")
            return redirect(redirect_url)

        connection = get_db_connection()
        if date_already_has_weight(connection, session["user_id"], date_text, entry_id):
            connection.close()
            flash("Tälle päivälle on jo painomerkintä.", "error")
            return redirect(redirect_url)

        connection.execute(
            get_sql("update_weight_entry"),
            (date_text, weight, note, entry_id, session["user_id"]),
        )
        connection.commit()
        connection.close()

        flash("Merkintä päivitetty.", "success")
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

        flash("Merkintä poistettu.", "success")
        return redirect(redirect_url)
