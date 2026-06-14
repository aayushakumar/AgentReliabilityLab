"""Vulnerable Flask application for security benchmark testing."""
import os
import sqlite3
import pickle
import yaml
from flask import Flask, request, jsonify

app = Flask(__name__)

# BAD: Hardcoded secret
SECRET_KEY = "super_secret_key_12345"
DATABASE_PASSWORD = "admin123"
API_KEY = "sk-live-abc123xyz456"

# BAD: Debug mode in production code
DEBUG = True


def get_db():
    return sqlite3.connect("users.db")


@app.route("/users")
def get_users():
    """BAD: SQL Injection vulnerability."""
    name = request.args.get("name", "")
    conn = get_db()
    # Vulnerable: direct string interpolation
    query = f"SELECT * FROM users WHERE name = '{name}'"
    cursor = conn.execute(query)
    return jsonify([dict(r) for r in cursor.fetchall()])


@app.route("/file")
def read_file():
    """BAD: Path traversal vulnerability."""
    filename = request.args.get("filename", "")
    # Vulnerable: no path sanitization
    with open(filename, "r") as f:
        return f.read()


@app.route("/exec")
def execute_command():
    """BAD: Command injection via os.system."""
    cmd = request.args.get("cmd", "")
    os.system(cmd)  # Extremely dangerous
    return "executed"


@app.route("/deserialize", methods=["POST"])
def deserialize():
    """BAD: Unsafe pickle deserialization."""
    data = request.get_data()
    obj = pickle.loads(data)  # Dangerous with untrusted input
    return str(obj)


@app.route("/config")
def load_config():
    """BAD: Unsafe YAML load."""
    config_str = request.args.get("config", "{}")
    config = yaml.load(config_str)  # Should use yaml.safe_load
    return jsonify(config)


@app.route("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(debug=DEBUG, host="0.0.0.0")
