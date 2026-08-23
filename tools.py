"""Mock implementations of the three available tools."""

import random


def get_weather(location: str, date: str) -> dict:
    conditions = ["sunny", "partly cloudy", "overcast", "rainy", "stormy"]
    return {
        "location": location,
        "date": date,
        "condition": random.choice(conditions),
        "temperature_c": random.randint(12, 38),
        "humidity_pct": random.randint(30, 95),
        "wind_kph": random.randint(5, 55),
    }


def get_travel_time(origin: str, destination: str, mode: str = "driving") -> dict:
    base_minutes = {"driving": 45, "walking": 120, "transit": 70}
    minutes = base_minutes.get(mode, 45) + random.randint(-15, 30)
    return {
        "origin": origin,
        "destination": destination,
        "mode": mode,
        "duration_minutes": max(5, minutes),
        "distance_km": round(minutes * random.uniform(0.6, 1.1), 1),
    }


def convert_currency(amount: float, from_currency: str, to_currency: str) -> dict:
    # Mock rates relative to USD
    rates = {
        "USD": 1.000, "EUR": 0.920, "GBP": 0.790,
        "JPY": 149.5, "CAD": 1.360, "AUD": 1.530, "CHF": 0.900,
        "INR": 83.1, "BRL": 4.970, "MXN": 17.15,
    }
    from_rate = rates.get(from_currency.upper(), 1.0)
    to_rate = rates.get(to_currency.upper(), 1.0)
    converted = amount / from_rate * to_rate
    return {
        "amount": amount,
        "from_currency": from_currency.upper(),
        "to_currency": to_currency.upper(),
        "converted_amount": round(converted, 2),
        "exchange_rate": round(to_rate / from_rate, 6),
        "note": "Mock rate — not a live quote",
    }


TOOL_REGISTRY = {
    "get_weather": get_weather,
    "get_travel_time": get_travel_time,
    "convert_currency": convert_currency,
}
