RATES = {
    "GBP_USD": 1.27,
    "GBP_EUR": 1.17,
    "USD_GBP": 0.79,
    "USD_EUR": 0.92,
    "EUR_GBP": 0.85,
    "EUR_USD": 1.09,
}


def convert(amount: float, from_currency: str, to_currency: str) -> float:
    if from_currency == to_currency:
        return amount
    key = f"{from_currency}_{to_currency}"
    if key not in RATES:
        raise ValueError(f"No rate found for {from_currency} to {to_currency}")
    # BUG: should round to 2 decimal places but doesn't
    return amount * RATES[key]


def convert_batch(amounts: list, from_currency: str, to_currency: str) -> list:
    return [convert(a, from_currency, to_currency) for a in amounts]


def get_available_currencies() -> list:
    currencies = set()
    for key in RATES:
        a, b = key.split("_")
        currencies.add(a)
        currencies.add(b)
    return sorted(currencies)
