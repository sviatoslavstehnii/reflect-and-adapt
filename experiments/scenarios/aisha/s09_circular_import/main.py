from models import User
from auth import authenticate

users = [
    User("aisha@example.com", "secret123"),
    User("admin@teamflow.io", "admin456"),
]

result = authenticate("aisha@example.com", "secret123", users)
print(f"Authenticated: {result}")
