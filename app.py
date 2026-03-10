import os
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
import psycopg2.extras

app = Flask(__name__)
CORS(app)  # Allow Netlify frontend to call this API

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    return conn


def init_db():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id        TEXT PRIMARY KEY,
                    title     TEXT NOT NULL,
                    type      TEXT NOT NULL,
                    subject   TEXT NOT NULL,
                    date      TEXT NOT NULL,
                    "createdAt" BIGINT NOT NULL
                )
            """)
        conn.commit()


def row_to_dict(row, cursor):
    cols = [desc[0] for desc in cursor.description]
    return dict(zip(cols, row))


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

    for key in ["title", "type","subject", "date"]:
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
                cur.execute(
                    f"UPDATE tasks SET {set_clause} WHERE id = %(task_id)s", fields
                )
                if cur.rowcount == 0:
                    return jsonify({"error": "Task not found"}), 404
                cur.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))
                row = cur.fetchone()
                updated = row_to_dict(row, cur)
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


@app.route("/")
def status():
    return jsonify({"status": "ok"}), 200


init_db()  # runs on startup whether gunicorn or direct

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True)