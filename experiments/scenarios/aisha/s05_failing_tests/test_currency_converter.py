import pytest
from currency_converter import convert, convert_batch, get_available_currencies


def test_same_currency_returns_same_amount():
    assert convert(100, "GBP", "GBP") == 100


def test_gbp_to_usd():
    # FAILS: 100 * 1.27 = 127.00000000000001 due to float precision
    assert convert(100, "GBP", "USD") == 127.00


def test_gbp_to_eur():
    result = convert(100, "GBP", "EUR")
    # FAILS: same float precision issue — 100 * 1.17 = 117.00000000000001
    assert result == 117.00


def test_unknown_pair_raises_error():
    with pytest.raises(ValueError):
        convert(100, "GBP", "JPY")


def test_convert_batch():
    results = convert_batch([100, 200, 50], "USD", "GBP")
    assert len(results) == 3
    assert all(isinstance(r, float) for r in results)


def test_available_currencies_contains_gbp():
    currencies = get_available_currencies()
    assert "GBP" in currencies


def test_available_currencies_sorted():
    currencies = get_available_currencies()
    assert currencies == sorted(currencies)
