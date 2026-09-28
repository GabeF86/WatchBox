from datetime import datetime, timezone

from watchbox.db import Watch
from watchbox.display import build_screens, fit, format_price, time_ago


def w(id, model, slot=None, price=None, nickname=None):
    return Watch(id=id, brand="Rolex", model=model, reference="X", slot=slot, nickname=nickname, price_usd=price)


def test_format_price_whole_dollars_with_commas():
    assert format_price(13400.4) == "$13,400"
    assert format_price(999_999) == "$999,999"


def test_format_price_switches_to_millions_when_too_long():
    assert format_price(1_234_567) == "$1.2M"
    assert format_price(999_999.6) == "$1.0M"


def test_fit_truncates_to_16_ascii_chars():
    assert fit("1 Royal Oak Offshore Chronograph") == "1 Royal Oak Offs"
    assert fit("Café Racer") == "Caf Racer"


def test_fit_leaves_exactly_16_chars_unchanged():
    text = "1234567890123456"
    assert len(text) == 16
    assert fit(text) == text


def test_empty_collection():
    assert build_screens([]) == [{"line1": "No watches yet", "line2": "Add on the app"}]


def test_total_first_then_slots_in_order_unslotted_last():
    watches = [
        w(1, "Tank Must", slot=None, price=2600),
        w(2, "Speedmaster", slot=2, price=6150),
        w(3, "Submariner", slot=1, price=13400),
        w(4, "Nautilus", slot=3),
    ]
    assert build_screens(watches) == [
        {"line1": "TOTAL 3 watches", "line2": "$22,150"},
        {"line1": "1 Submariner", "line2": "$13,400"},
        {"line1": "2 Speedmaster", "line2": "$6,150"},
        {"line1": "3 Nautilus", "line2": "no price yet"},
        {"line1": "Tank Must", "line2": "$2,600"},
    ]


def test_nickname_wins_and_total_is_singular():
    assert build_screens([w(1, "Submariner", slot=5, price=100, nickname="Dad's Sub")]) == [
        {"line1": "TOTAL 1 watch", "line2": "$100"},
        {"line1": "5 Dad's Sub", "line2": "$100"},
    ]


def test_time_ago():
    now = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)
    assert time_ago(None, now) == "never"
    assert time_ago("2026-09-27T11:59:30+00:00", now) == "just now"
    assert time_ago("2026-09-27T11:15:00+00:00", now) == "45 min ago"
    assert time_ago("2026-09-27T06:00:00+00:00", now) == "6 h ago"
    assert time_ago("2026-09-24T12:00:00+00:00", now) == "3 d ago"


def test_time_ago_treats_naive_timestamp_as_utc():
    now = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)
    assert time_ago("2026-09-27T11:15:00", now) == "45 min ago"
