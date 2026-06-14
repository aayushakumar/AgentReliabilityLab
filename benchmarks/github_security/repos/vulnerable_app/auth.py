"""Authentication utilities with security vulnerabilities."""
import hashlib
import hmac
import os
import requests


# BAD: Hardcoded JWT secret
JWT_SECRET = "my_jwt_secret_key"


def hash_password(password: str) -> str:
    """BAD: Using MD5 for password hashing."""
    return hashlib.md5(password.encode()).hexdigest()


def verify_token(token: str) -> bool:
    """BAD: TLS verification disabled."""
    resp = requests.get(
        "https://auth.example.com/verify",
        headers={"Authorization": f"Bearer {token}"},
        verify=False,  # BAD: disabling TLS verification
    )
    return resp.status_code == 200


def get_user_data(user_id: str):
    """BAD: SQL injection in user lookup."""
    import sqlite3
    conn = sqlite3.connect("app.db")
    # Directly interpolating user input
    query = "SELECT * FROM users WHERE id = " + user_id
    return conn.execute(query).fetchone()
