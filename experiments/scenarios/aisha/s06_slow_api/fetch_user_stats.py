import requests
import json
import time

BASE_URL = "https://api.internal.teamflow.io/v1"
API_KEY = "sk-internal-xxxx"


def fetch_user_stats(user_id: int) -> dict:
    """Fetch activity stats for a single user."""
    response = requests.get(
        f"{BASE_URL}/users/{user_id}/stats",
        headers={"Authorization": f"Bearer {API_KEY}"},
        timeout=10
    )
    response.raise_for_status()
    return response.json()


def build_report(user_ids: list) -> list:
    """Fetch stats for all users — called sequentially, one by one."""
    results = []
    for uid in user_ids:
        stats = fetch_user_stats(uid)   # waits for each request before starting next
        results.append({"user_id": uid, **stats})
    return results


if __name__ == "__main__":
    user_ids = list(range(1001, 1051))  # 50 users
    start = time.time()
    print(f"Fetching stats for {len(user_ids)} users...")
    report = build_report(user_ids)
    elapsed = time.time() - start
    print(f"Done in {elapsed:.1f}s")
    with open("report.json", "w") as f:
        json.dump(report, f, indent=2)
