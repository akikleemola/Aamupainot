-- name: create_users
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    target_weight REAL
);

-- name: add_target_weight_to_users
ALTER TABLE users
ADD COLUMN target_weight REAL;

-- name: create_weight_entries
CREATE TABLE IF NOT EXISTS weight_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    date TEXT NOT NULL,
    weight REAL NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (user_id) REFERENCES users (id)
);

-- name: add_user_id_to_weight_entries
ALTER TABLE weight_entries
ADD COLUMN user_id INTEGER REFERENCES users (id);

-- name: add_note_to_weight_entries
ALTER TABLE weight_entries
ADD COLUMN note TEXT NOT NULL DEFAULT '';

-- name: create_weight_entries_user_date_index
CREATE INDEX IF NOT EXISTS index_weight_entries_user_date
ON weight_entries (user_id, date DESC);

-- name: insert_user
INSERT INTO users (username, password_hash)
VALUES (?, ?);

-- name: select_user_by_username
SELECT id, username, password_hash, target_weight
FROM users
WHERE username = ?;

-- name: select_user_settings
SELECT username, target_weight
FROM users
WHERE id = ?;

-- name: update_user_settings
UPDATE users
SET target_weight = ?
WHERE id = ?;

-- name: update_username
UPDATE users
SET username = ?
WHERE id = ?;

-- name: insert_weight_entry
INSERT INTO weight_entries (user_id, date, weight, note)
VALUES (?, ?, ?, ?);

-- name: select_weight_entries_for_user
SELECT id, date, weight, note
FROM weight_entries
WHERE user_id = ?
ORDER BY date DESC;

-- name: select_weight_entry_for_user_date
SELECT id
FROM weight_entries
WHERE user_id = ? AND date = ?;

-- name: select_other_weight_entry_for_user_date
SELECT id
FROM weight_entries
WHERE user_id = ? AND date = ? AND id != ?;

-- name: update_weight_entry
UPDATE weight_entries
SET date = ?, weight = ?, note = ?
WHERE id = ? AND user_id = ?;

-- name: delete_weight_entry
DELETE FROM weight_entries
WHERE id = ? AND user_id = ?;
