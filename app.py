import os
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
import psycopg2.extras

app = Flask(__name__)
CORS(app)

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    return conn


def init_db():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id          TEXT PRIMARY KEY,
                    title       TEXT NOT NULL,
                    type        TEXT NOT NULL,
                    subject     TEXT NOT NULL,
                    date        TEXT NOT NULL,
                    "createdAt" BIGINT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ideas (
                    id          TEXT PRIMARY KEY,
                    title       TEXT NOT NULL,
                    "desc"      TEXT NOT NULL DEFAULT '',
                    status      TEXT NOT NULL DEFAULT 'idea',
                    priority    TEXT NOT NULL DEFAULT 'medium',
                    tags        TEXT NOT NULL DEFAULT '',
                    "createdAt" BIGINT NOT NULL
                )
            """)
        conn.commit()


def row_to_dict(row, cursor):
    cols = [desc[0] for desc in cursor.description]
    d = dict(zip(cols, row))
    # Return tags as a list so the frontend doesn't need to parse
    if "tags" in d and isinstance(d["tags"], str):
        d["tags"] = [t.strip() for t in d["tags"].split(",") if t.strip()]
    return d


# ═══════════════════════════════════════════
#  TASKS
# ═══════════════════════════════════════════

@app.route("/api/tasks", methods=["GET"])
def get_tasks():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM tasks ORDER BY date ASC')
            rows = cur.fetchall()
            return jsonify([row_to_dict(r, cur) for r in rows])


@app.route("/api/tasks", methods=["POST"])
def add_task():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    for key in ["title", "type", "subject", "date"]:
        if key not in data:
            return jsonify({"error": f"Missing field: {key}"}), 400

    new_task = {
        "id": datetime.now().strftime("%Y%m%d%H%M%S") + str(abs(hash(data["title"])))[:6],
        "title": data["title"],
        "type": data["type"],
        "subject": data["subject"],
        "date": data["date"],
        "createdAt": int(datetime.now().timestamp() * 1000),
    }
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'INSERT INTO tasks (id, title, type, subject, date, "createdAt") '
                    'VALUES (%(id)s, %(title)s, %(type)s, %(subject)s, %(date)s, %(createdAt)s)',
                    new_task,
                )
            conn.commit()
        return jsonify(new_task), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/tasks/<task_id>", methods=["PUT"])
def update_task(task_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    fields = {k: data[k] for k in ["title", "type", "subject", "date"] if k in data}
    if not fields:
        return jsonify({"error": "No valid fields to update"}), 400
    set_clause = ", ".join(f"{k} = %({k})s" for k in fields)
    fields["task_id"] = task_id
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE tasks SET {set_clause} WHERE id = %(task_id)s", fields)
                if cur.rowcount == 0:
                    return jsonify({"error": "Task not found"}), 404
                cur.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))
                updated = row_to_dict(cur.fetchone(), cur)
            conn.commit()
        return jsonify(updated), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/tasks/<task_id>", methods=["DELETE"])
def delete_task(task_id):
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM tasks WHERE id = %s", (task_id,))
                if cur.rowcount == 0:
                    return jsonify({"error": "Task not found"}), 404
            conn.commit()
        return jsonify({"deleted": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ═══════════════════════════════════════════
#  IDEAS
# ═══════════════════════════════════════════

def _tags_to_str(raw):
    """Accept list or comma-string from the request, return a clean comma-string for storage."""
    if isinstance(raw, list):
        return ", ".join(t.strip() for t in raw if t.strip())
    return str(raw).strip()


@app.route("/api/ideas", methods=["GET"])
def get_ideas():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM ideas ORDER BY "createdAt" DESC')
            rows = cur.fetchall()
            return jsonify([row_to_dict(r, cur) for r in rows])


@app.route("/api/ideas", methods=["POST"])
def add_idea():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    if not data.get("title", "").strip():
        return jsonify({"error": "Missing field: title"}), 400

    new_idea = {
        "id": datetime.now().strftime("%Y%m%d%H%M%S") + str(abs(hash(data["title"])))[:6],
        "title":    data["title"].strip(),
        "desc":     data.get("desc", "").strip(),
        "status":   data.get("status", "idea"),
        "priority": data.get("priority", "medium"),
        "tags":     _tags_to_str(data.get("tags", [])),
        "createdAt": int(datetime.now().timestamp() * 1000),
    }
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'INSERT INTO ideas (id, title, "desc", status, priority, tags, "createdAt") '
                    'VALUES (%(id)s, %(title)s, %(desc)s, %(status)s, %(priority)s, %(tags)s, %(createdAt)s)',
                    new_idea,
                )
            conn.commit()
        # Return tags as list to match frontend expectation
        response = {**new_idea, "tags": [t.strip() for t in new_idea["tags"].split(",") if t.strip()]}
        return jsonify(response), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/ideas/<idea_id>", methods=["PUT"])
def update_idea(idea_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    allowed = ["title", "desc", "status", "priority", "tags"]
    fields = {}
    for k in allowed:
        if k in data:
            fields[k] = _tags_to_str(data[k]) if k == "tags" else data[k]

    if not fields:
        return jsonify({"error": "No valid fields to update"}), 400

    # "desc" is reserved in PostgreSQL — quote it in the SET clause
    RESERVED = {"desc"}
    set_clause = ", ".join(f'"{k}" = %({k})s' if k in RESERVED else f"{k} = %({k})s" for k in fields)
    fields["idea_id"] = idea_id
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE ideas SET {set_clause} WHERE id = %(idea_id)s", fields)
                if cur.rowcount == 0:
                    return jsonify({"error": "Idea not found"}), 404
                cur.execute("SELECT * FROM ideas WHERE id = %s", (idea_id,))
                updated = row_to_dict(cur.fetchone(), cur)
            conn.commit()
        return jsonify(updated), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/ideas/<idea_id>", methods=["DELETE"])
def delete_idea(idea_id):
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM ideas WHERE id = %s", (idea_id,))
                if cur.rowcount == 0:
                    return jsonify({"error": "Idea not found"}), 404
            conn.commit()
        return jsonify({"deleted": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ═══════════════════════════════════════════
#  HEALTH
# ═══════════════════════════════════════════

@app.route("/")
def status():
    return jsonify({"status": "ok"}), 200


init_db()  # creates both tables on startup

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True)