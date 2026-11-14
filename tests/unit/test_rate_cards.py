"""Unit tests for versioned rate cards."""

from app.core.rate_cards import RateCardCatalog, RateCardEntry


def test_default_rate_catalog():
    catalog = RateCardCatalog(version="2026-11-01")
    rate = catalog.get_rate("mock-cheap")
    assert rate is not None
    assert rate.input_rate_per_million == 0.15
    assert rate.output_rate_per_million == 0.60
    assert rate.currency == "USD"
    assert rate.version == "2026-11-01"


def test_custom_rate_registration():
    catalog = RateCardCatalog(version="test-v1")
    custom_entry = RateCardEntry(
        rate_card_id="rc_custom_test",
        model_alias="custom-model",
        provider="custom-prov",
        input_rate_per_million=1.00,
        output_rate_per_million=2.00,
        currency="USD",
    )
    catalog.register_rate(custom_entry)
    rate = catalog.get_rate("custom-model")
    assert rate is not None
    assert rate.rate_card_id == "rc_custom_test"
