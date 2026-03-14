#!/usr/bin/env python3
"""
Creates a git repository with a realistic merge conflict.
Run before session: python setup.py --target /path/to/workspace/data/
"""
import argparse
import os
import shutil
import subprocess
from pathlib import Path


def run(cmd, cwd):
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)


def create_conflicted_repo(target_dir: Path):
    repo = target_dir / "payment_service"
    if repo.exists():
        shutil.rmtree(repo)
    repo.mkdir(parents=True)

    run(["git", "init"], repo)
    run(["git", "config", "user.email", "aisha@example.com"], repo)
    run(["git", "config", "user.name", "Aisha"], repo)

    # Initial commit on main
    payment = repo / "payment.py"
    payment.write_text('''\
def process_payment(amount, currency="GBP"):
    """Process a payment and return a transaction ID."""
    if amount <= 0:
        raise ValueError("Amount must be positive")
    # TODO: integrate with Stripe
    return f"txn_{amount}_{currency}"


def get_supported_currencies():
    return ["GBP", "USD"]
''')
    run(["git", "add", "."], repo)
    run(["git", "commit", "-m", "Add initial payment module"], repo)

    # Feature branch: add EUR support + change return format
    run(["git", "checkout", "-b", "feature/eur-support"], repo)
    payment.write_text('''\
def process_payment(amount, currency="GBP"):
    """Process a payment and return a transaction dict."""
    if amount <= 0:
        raise ValueError("Amount must be positive")
    # Integrated with Stripe sandbox
    transaction_id = f"txn_{amount}_{currency}"
    return {"id": transaction_id, "amount": amount, "currency": currency, "status": "pending"}


def get_supported_currencies():
    return ["GBP", "USD", "EUR"]
''')
    run(["git", "add", "."], repo)
    run(["git", "commit", "-m", "Add EUR support and structured return value"], repo)

    # Back to main: colleague added validation
    run(["git", "checkout", "main"], repo)
    payment.write_text('''\
SUPPORTED_CURRENCIES = ["GBP", "USD"]


def process_payment(amount, currency="GBP"):
    """Process a payment and return a transaction ID."""
    if amount <= 0:
        raise ValueError("Amount must be positive")
    if currency not in SUPPORTED_CURRENCIES:
        raise ValueError(f"Unsupported currency: {currency}")
    # TODO: integrate with Stripe
    return f"txn_{amount}_{currency}"


def get_supported_currencies():
    return SUPPORTED_CURRENCIES
''')
    run(["git", "add", "."], repo)
    run(["git", "commit", "-m", "Add currency validation"], repo)

    # Merge feature branch — produces conflict in process_payment
    result = subprocess.run(
        ["git", "merge", "feature/eur-support"],
        cwd=repo, capture_output=True, text=True
    )
    # Conflict is expected — repo is now in conflicted state

    print(f"Repo created at: {repo}")
    print("Git status:")
    subprocess.run(["git", "status"], cwd=repo)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True, help="Target workspace data directory")
    args = parser.parse_args()
    create_conflicted_repo(Path(args.target))


if __name__ == "__main__":
    main()
