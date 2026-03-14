import csv
from datetime import datetime


def load_transactions(filepath):
    transactions = []
    with open(filepath, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            transactions.append(row)
    return transactions


def summarise_by_category(transactions):
    totals = {}
    for tx in transactions:
        # BUG: some rows have "category" as empty string or the column is
        # named "tx_category" in newer export files — causes KeyError
        category = tx["category"]
        amount = float(tx["amount"])
        if category in totals:
            totals[category] += amount
        else:
            totals[category] = amount
    return totals


def find_large_transactions(transactions, threshold=500):
    return [tx for tx in transactions if float(tx["amount"]) > threshold]


def main():
    txs = load_transactions("transactions.csv")
    print(f"Loaded {len(txs)} transactions")

    summary = summarise_by_category(txs)
    print("\nSummary by category:")
    for cat, total in sorted(summary.items(), key=lambda x: -x[1]):
        print(f"  {cat}: £{total:.2f}")

    large = find_large_transactions(txs)
    print(f"\nLarge transactions (>£500): {len(large)}")


if __name__ == "__main__":
    main()
