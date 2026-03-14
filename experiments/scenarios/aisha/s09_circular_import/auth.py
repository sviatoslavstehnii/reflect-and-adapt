import hashlib
from models import User   # circular: models imports hash_password from auth


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def authenticate(email: str, password: str, users: list) -> User | None:
    hashed = hash_password(password)
    for user in users:
        if user.email == email and user.password_hash == hashed:
            return user
    return None
