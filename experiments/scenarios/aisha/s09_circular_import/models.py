from auth import hash_password   # circular: auth imports User from models


class User:
    def __init__(self, email: str, password: str):
        self.email = email
        self.password_hash = hash_password(password)
        self.is_active = True

    def __repr__(self):
        return f"<User {self.email}>"
