import sqlite3


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
    try:
        connection.execute(get_sql("add_target_weight_to_users"))
    except sqlite3.OperationalError:
        pass
    try:
        connection.execute(get_sql("add_chart_line_type_to_users"))
    except sqlite3.OperationalError:
        pass
    try:
        connection.execute(get_sql("add_show_target_line_to_users"))
    except sqlite3.OperationalError:
        pass
    try:
        connection.execute(get_sql("add_weight_precision_to_users"))
    except sqlite3.OperationalError:
        pass
    connection.execute(get_sql("normalize_weight_precision"))
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
