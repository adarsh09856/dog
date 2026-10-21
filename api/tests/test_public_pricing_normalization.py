from api.routes.billing_sovereign import _public_plan_prices


def test_public_plan_prices_convert_inr_paise_to_rupees_and_usd():
    assert _public_plan_prices(249900, "INR") == (2499, 30)


def test_public_plan_prices_convert_usd_cents_to_usd_and_rupees():
    assert _public_plan_prices(2999, "USD") == (2489, 30)


def test_public_plan_prices_treat_unknown_currency_as_inr():
    assert _public_plan_prices(149900, "unknown") == (1499, 18)
