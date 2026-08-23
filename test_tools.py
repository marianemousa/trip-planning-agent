"""
Unit tests for the three mock tool functions.

Tests call functions directly — no API key or network required.

Coverage:
  - Valid input returns a well-formed dict matching the expected schema
  - Missing a required argument raises TypeError (Python enforces the signature)
  - Invalid argument values are handled predictably without silent data corruption
"""

import pytest

from agent import _validate_arguments
from tools import convert_currency, get_travel_time, get_weather


# ── Constants ─────────────────────────────────────────────────────────────────

WEATHER_KEYS = {"location", "date", "condition", "temperature_c", "humidity_pct", "wind_kph"}
VALID_CONDITIONS = {"sunny", "partly cloudy", "overcast", "rainy", "stormy"}

TRAVEL_KEYS = {"origin", "destination", "mode", "duration_minutes", "distance_km"}
VALID_MODES = {"driving", "walking", "transit"}

CURRENCY_KEYS = {"amount", "from_currency", "to_currency", "converted_amount", "exchange_rate", "note"}


# ── get_weather ───────────────────────────────────────────────────────────────

class TestGetWeather:

    # Valid input ──────────────────────────────────────────────────────────────

    def test_returns_all_expected_keys(self):
        assert set(get_weather("London", "2025-09-01").keys()) == WEATHER_KEYS

    def test_location_passed_through(self):
        assert get_weather("Tokyo", "2025-12-25")["location"] == "Tokyo"

    def test_date_passed_through(self):
        assert get_weather("Tokyo", "2025-12-25")["date"] == "2025-12-25"

    def test_condition_is_valid_value(self):
        assert get_weather("Paris", "tomorrow")["condition"] in VALID_CONDITIONS

    def test_temperature_within_mock_range(self):
        temp = get_weather("Sydney", "today")["temperature_c"]
        assert 12 <= temp <= 38

    def test_humidity_within_mock_range(self):
        humidity = get_weather("Berlin", "today")["humidity_pct"]
        assert 30 <= humidity <= 95

    def test_wind_within_mock_range(self):
        wind = get_weather("Chicago", "today")["wind_kph"]
        assert 5 <= wind <= 55

    def test_relative_date_accepted(self):
        result = get_weather("Rome", "tomorrow")
        assert result["date"] == "tomorrow"
        assert set(result.keys()) == WEATHER_KEYS

    # Missing required args ────────────────────────────────────────────────────

    def test_missing_location_raises(self):
        with pytest.raises(TypeError):
            get_weather(date="2025-09-01")  # type: ignore[call-arg]

    def test_missing_date_raises(self):
        with pytest.raises(TypeError):
            get_weather(location="London")  # type: ignore[call-arg]

    def test_no_args_raises(self):
        with pytest.raises(TypeError):
            get_weather()  # type: ignore[call-arg]

    # Invalid argument values ──────────────────────────────────────────────────

    def test_invalid_date_string_echoed_back(self):
        """Mock does not validate date format; caller gets back what they passed."""
        result = get_weather("London", "not-a-real-date")
        assert result["date"] == "not-a-real-date"
        assert set(result.keys()) == WEATHER_KEYS

    def test_empty_location_echoed_back(self):
        """Mock does not validate location; empty string is echoed."""
        result = get_weather("", "2025-09-01")
        assert result["location"] == ""
        assert set(result.keys()) == WEATHER_KEYS


# ── get_travel_time ───────────────────────────────────────────────────────────

class TestGetTravelTime:

    # Valid input ──────────────────────────────────────────────────────────────

    def test_returns_all_expected_keys(self):
        assert set(get_travel_time("Berlin", "Munich").keys()) == TRAVEL_KEYS

    def test_origin_passed_through(self):
        assert get_travel_time("Paris", "Lyon")["origin"] == "Paris"

    def test_destination_passed_through(self):
        assert get_travel_time("Paris", "Lyon")["destination"] == "Lyon"

    def test_default_mode_is_driving(self):
        assert get_travel_time("A", "B")["mode"] == "driving"

    @pytest.mark.parametrize("mode", ["driving", "walking", "transit"])
    def test_explicit_mode_echoed(self, mode):
        assert get_travel_time("A", "B", mode=mode)["mode"] == mode

    @pytest.mark.parametrize("mode", ["driving", "walking", "transit"])
    def test_duration_is_at_least_five_minutes(self, mode):
        result = get_travel_time("X", "Y", mode=mode)
        assert result["duration_minutes"] >= 5

    def test_distance_is_positive(self):
        assert get_travel_time("X", "Y")["distance_km"] > 0

    def test_values_are_numeric(self):
        result = get_travel_time("X", "Y")
        assert isinstance(result["duration_minutes"], int)
        assert isinstance(result["distance_km"], float)

    # Missing required args ────────────────────────────────────────────────────

    def test_missing_origin_raises(self):
        with pytest.raises(TypeError):
            get_travel_time(destination="Munich")  # type: ignore[call-arg]

    def test_missing_destination_raises(self):
        with pytest.raises(TypeError):
            get_travel_time(origin="Berlin")  # type: ignore[call-arg]

    def test_no_args_raises(self):
        with pytest.raises(TypeError):
            get_travel_time()  # type: ignore[call-arg]

    # Invalid argument values ──────────────────────────────────────────────────

    def test_unknown_mode_falls_back_without_crashing(self):
        """Unknown modes use the driving base (45 min); no exception is raised."""
        result = get_travel_time("A", "B", mode="teleport")
        assert result["mode"] == "teleport"
        assert result["duration_minutes"] >= 5

    def test_unknown_mode_echoed_in_output(self):
        result = get_travel_time("A", "B", mode="supersonic")
        assert result["mode"] == "supersonic"


# ── convert_currency ──────────────────────────────────────────────────────────

class TestConvertCurrency:

    # Valid input ──────────────────────────────────────────────────────────────

    def test_returns_all_expected_keys(self):
        assert set(convert_currency(100, "USD", "EUR").keys()) == CURRENCY_KEYS

    def test_amount_echoed_back(self):
        assert convert_currency(250.0, "USD", "JPY")["amount"] == 250.0

    def test_currencies_uppercased(self):
        result = convert_currency(100, "usd", "eur")
        assert result["from_currency"] == "USD"
        assert result["to_currency"] == "EUR"

    def test_same_currency_returns_same_amount(self):
        result = convert_currency(100, "USD", "USD")
        assert result["converted_amount"] == 100.0
        assert result["exchange_rate"] == pytest.approx(1.0)

    def test_usd_to_eur_known_rate(self):
        result = convert_currency(100, "USD", "EUR")
        assert result["converted_amount"] == pytest.approx(92.0)
        assert result["exchange_rate"] == pytest.approx(0.92)

    def test_usd_to_jpy_known_rate(self):
        result = convert_currency(1, "USD", "JPY")
        assert result["converted_amount"] == pytest.approx(149.5)

    def test_zero_amount_returns_zero(self):
        assert convert_currency(0, "USD", "EUR")["converted_amount"] == 0.0

    def test_fractional_amount(self):
        result = convert_currency(1.50, "EUR", "USD")
        assert isinstance(result["converted_amount"], float)
        assert result["converted_amount"] > 0

    def test_note_field_is_string(self):
        result = convert_currency(100, "USD", "EUR")
        assert isinstance(result["note"], str)
        assert len(result["note"]) > 0

    def test_converted_amount_is_float(self):
        result = convert_currency(100, "USD", "GBP")
        assert isinstance(result["converted_amount"], float)

    def test_exchange_rate_is_positive(self):
        result = convert_currency(100, "USD", "EUR")
        assert result["exchange_rate"] > 0

    # Missing required args ────────────────────────────────────────────────────

    def test_missing_amount_raises(self):
        with pytest.raises(TypeError):
            convert_currency(from_currency="USD", to_currency="EUR")  # type: ignore[call-arg]

    def test_missing_from_currency_raises(self):
        with pytest.raises(TypeError):
            convert_currency(100, to_currency="EUR")  # type: ignore[call-arg]

    def test_missing_to_currency_raises(self):
        with pytest.raises(TypeError):
            convert_currency(100, "USD")  # type: ignore[call-arg]

    def test_no_args_raises(self):
        with pytest.raises(TypeError):
            convert_currency()  # type: ignore[call-arg]

    # Invalid argument values ──────────────────────────────────────────────────

    def test_unknown_from_currency_falls_back_to_rate_one(self):
        """Unrecognised currency codes silently use rate 1.0 (USD-equivalent).
        This means the caller gets a number back, not an error.
        The routing layer is responsible for rejecting invalid codes before calling."""
        result = convert_currency(100, "FAKE", "USD")
        assert result["from_currency"] == "FAKE"
        # FAKE=1.0, USD=1.0 → 100/1.0*1.0 = 100
        assert result["converted_amount"] == pytest.approx(100.0)

    def test_unknown_to_currency_falls_back_to_rate_one(self):
        result = convert_currency(100, "USD", "MARS")
        assert result["to_currency"] == "MARS"
        assert result["converted_amount"] == pytest.approx(100.0)

    def test_both_unknown_currencies_still_returns_amount(self):
        """Two unknown currencies cancel out (both rate=1.0), amount unchanged."""
        result = convert_currency(42.0, "FOO", "BAR")
        assert result["converted_amount"] == pytest.approx(42.0)
        assert result["exchange_rate"] == pytest.approx(1.0)


# ── _validate_arguments ───────────────────────────────────────────────────────

class TestValidateArguments:

    # Valid inputs — should always return (True, None) ─────────────────────────

    def test_weather_valid(self):
        assert _validate_arguments("get_weather", {"location": "London", "date": "2025-09-01"}) == (True, None)

    def test_travel_valid_with_mode(self):
        args = {"origin": "Berlin", "destination": "Munich", "mode": "driving"}
        assert _validate_arguments("get_travel_time", args) == (True, None)

    def test_travel_valid_without_mode(self):
        args = {"origin": "Berlin", "destination": "Munich"}
        assert _validate_arguments("get_travel_time", args) == (True, None)

    def test_currency_valid_int_amount(self):
        args = {"amount": 250, "from_currency": "USD", "to_currency": "JPY"}
        valid, _ = _validate_arguments("convert_currency", args)
        assert valid is True

    def test_currency_coerces_int_to_float(self):
        args = {"amount": 100, "from_currency": "USD", "to_currency": "EUR"}
        _validate_arguments("convert_currency", args)
        assert isinstance(args["amount"], float)
        assert args["amount"] == 100.0

    def test_currency_float_amount_unchanged(self):
        args = {"amount": 99.5, "from_currency": "USD", "to_currency": "EUR"}
        _validate_arguments("convert_currency", args)
        assert args["amount"] == 99.5

    def test_unknown_tool_passes(self):
        """No spec for unknown tools — validator returns valid rather than crashing."""
        assert _validate_arguments("no_such_tool", {"x": 1}) == (True, None)

    # Missing required args — should return (False, non-empty question) ─────────

    def test_weather_missing_location(self):
        valid, q = _validate_arguments("get_weather", {"date": "tomorrow"})
        assert valid is False
        assert q and "location" in q

    def test_weather_missing_date(self):
        valid, q = _validate_arguments("get_weather", {"location": "Paris"})
        assert valid is False
        assert q and "date" in q

    def test_weather_empty_location(self):
        valid, q = _validate_arguments("get_weather", {"location": "", "date": "today"})
        assert valid is False
        assert q is not None

    def test_weather_blank_location(self):
        valid, q = _validate_arguments("get_weather", {"location": "   ", "date": "today"})
        assert valid is False
        assert q is not None

    def test_travel_missing_origin(self):
        valid, q = _validate_arguments("get_travel_time", {"destination": "Munich"})
        assert valid is False
        assert q and "origin" in q

    def test_travel_missing_destination(self):
        valid, q = _validate_arguments("get_travel_time", {"origin": "Berlin"})
        assert valid is False
        assert q and "destination" in q

    def test_currency_missing_amount(self):
        valid, q = _validate_arguments("convert_currency", {"from_currency": "USD", "to_currency": "EUR"})
        assert valid is False
        assert q and "amount" in q

    def test_currency_missing_from_currency(self):
        valid, q = _validate_arguments("convert_currency", {"amount": 100.0, "to_currency": "EUR"})
        assert valid is False
        assert q and "from currency" in q

    def test_currency_missing_to_currency(self):
        valid, q = _validate_arguments("convert_currency", {"amount": 100.0, "from_currency": "USD"})
        assert valid is False
        assert q and "to currency" in q

    # Wrong types — should return (False, non-empty question) ──────────────────

    def test_currency_string_amount(self):
        args = {"amount": "one hundred", "from_currency": "USD", "to_currency": "EUR"}
        valid, q = _validate_arguments("convert_currency", args)
        assert valid is False
        assert q and "amount" in q

    def test_currency_bool_amount_rejected(self):
        args = {"amount": True, "from_currency": "USD", "to_currency": "EUR"}
        valid, q = _validate_arguments("convert_currency", args)
        assert valid is False
        assert q and "amount" in q

    def test_weather_numeric_location(self):
        args = {"location": 42, "date": "today"}
        valid, q = _validate_arguments("get_weather", args)
        assert valid is False
        assert q is not None

    def test_travel_list_origin(self):
        args = {"origin": ["Berlin"], "destination": "Munich"}
        valid, q = _validate_arguments("get_travel_time", args)
        assert valid is False
        assert q is not None

    # Optional arg absent is fine — no clarification triggered ─────────────────

    def test_travel_optional_mode_absent_is_valid(self):
        valid, q = _validate_arguments("get_travel_time", {"origin": "A", "destination": "B"})
        assert valid is True
        assert q is None
