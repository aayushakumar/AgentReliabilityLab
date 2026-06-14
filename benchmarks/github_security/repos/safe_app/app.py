"""Safe Flask application — properly secured version for benchmark comparison."""
import os
import sqlite3
import secrets
from functools import wraps
from flask import Flask, request, jsonify, abort

app = Flask(__name__)

# GOOD: Secret from environment variable
SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_urlsafe(32)
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"


def get_db():
    return sqlite3.connect(os.environ.get("DB_PATH", "users.db"))


@app.route("/users")
def get_users():
    """GOOD: Parameterized query prevents SQL injection."""
    name = request.args.get("name", "")
    conn = get_db()
    cursor = conn.execute("SELECT id, name, email FROM users WHERE name = ?", (name,))
    return jsonify([dict(zip(["id", "name", "email"], r)) for r in cursor.fetchall()])


@app.route("/file")
def read_file():
    """GOOD: Path validation prevents traversal."""
    filename = request.args.get("filename", "")
    # Sanitize: only allow files in the safe uploads directory
    safe_dir = os.path.realpath("./uploads")
    requested = os.path.realpath(os.path.join(safe_dir, filename))
    if not requested.startswith(safe_dir):
        abort(403, "Access denied")
    if not os.path.isfile(requested):
        abort(404)
    with open(requested, "r") as f:
        return f.read()


@app.route("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(debug=DEBUG, host="127.0.0.1")
