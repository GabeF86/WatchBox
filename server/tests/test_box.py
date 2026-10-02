from datetime import timezone

from fastapi.testclient import TestClient

from watchbox import db
from watchbox.app import create_app
from watchbox.box import ascii, build_box_payload, local_label
from watchbox.config import Settings
from watchbox.db import Watch

UTC = timezone.utc
NOW = "2026-10-02T14:00:00+00:00"


def watch(id, slot, **kw):
    return Watch(id=id, brand=kw.pop("brand", "Rolex"), model=kw.pop("model", "Submariner Date"),
                 reference=kw.pop("reference", "116610LN"), slot=slot, nickname=kw.pop("nickname", None), **kw)


def val(**kw):
    base = dict(estimate_usd=11720.4, confidence="high", n_ebay=30, ebay_median=11550.0, ebay_p10=10490.4,
                ebay_p90=12793.0, n_c24=38, c24_median=12656.0, backtest_n=30, backtest_mdape=0.0372,
                as_of="2026-10-02T13:14:00+00:00")
    return base | kw


def test_local_label_and_ascii():
    assert local_label("2026-10-02T13:14:00+00:00", UTC) == "Oct 2, 1:14 PM"
    assert local_label("2026-10-02T00:05:00+00:00", UTC) == "Oct 2, 12:05 AM"
    assert local_label(None, UTC) == ""
    assert ascii("Glashütte Original") == "Glashutte Original"


def test_always_eight_slots_with_empty_ones_null():
    p = build_box_payload([watch(1, 4)], {1: val()}, NOW, tz=UTC)
    assert [s["slot"] for s in p["slots"]] == list(range(1, 9))
    assert p["slots"][3]["watch"]["name"] == "Submariner Date"
    assert all(p["slots"][i]["watch"] is None for i in (0, 1, 2, 4, 5, 6, 7))
    assert p["generated_at"] == NOW


def test_valuation_fields_are_whole_dollars_with_labels():
    w = build_box_payload([watch(1, 4, nickname="Sub")], {1: val()}, NOW, tz=UTC)["slots"][3]["watch"]
    assert (w["name"], w["model"], w["estimate_usd"], w["confidence"]) == ("Sub", "Submariner Date", 11720, "high")
    assert w["ebay"] == {"n": 30, "median": 11550, "p10": 10490, "p90": 12793}
    assert w["chrono24"] == {"n": 38, "median": 12656}
    assert w["accuracy"] == {"n": 30, "mdape": 0.0372}
    assert w["as_of_label"] == "Oct 2, 1:14 PM"
    assert w["details"] == "Full set, Excellent"
    assert w["estimated_reference"] is False


def test_v0_price_fallback_and_no_price():
    old = watch(1, 1, price_usd=12412.6, fetched_at="2026-10-01T09:00:00+00:00")
    p = build_box_payload([old, watch(2, 2)], {}, NOW, tz=UTC)
    a, b = p["slots"][0]["watch"], p["slots"][1]["watch"]
    assert a["estimate_usd"] == 12413 and a["confidence"] is None
    assert a["ebay"] == {"n": 0, "median": None, "p10": None, "p90": None}
    assert a["accuracy"] == {"n": 0, "mdape": None} and a["as_of_label"] == "Oct 1, 9:00 AM"
    assert b["estimate_usd"] is None
    assert (p["total_usd"], p["priced"]) == (12413, 1)


def test_unslotted_watches_count_toward_the_total_and_are_ascii():
    gs = watch(1, None, brand="Glashütte Original", model="Sixties", reference="2-39-47-01-01-04",
               price_reference="2-39-47-06-02-04", box_papers="watch_only", condition="very_good")
    p = build_box_payload([gs], {1: val(estimate_usd=6820.0, confidence="medium")}, NOW, tz=UTC)
    u = p["unslotted"][0]
    assert u["brand"] == "Glashutte Original" and u["estimated_reference"] is True
    assert u["details"] == "Watch only, Very good"
    assert (p["total_usd"], p["priced"]) == (6820, 1)
    assert all(s["watch"] is None for s in p["slots"])


def test_updated_label_is_the_newest_data():
    vals = {1: val(as_of="2026-10-01T09:00:00+00:00"), 2: val(as_of="2026-10-02T13:14:00+00:00")}
    p = build_box_payload([watch(1, 1), watch(2, 2)], vals, NOW, tz=UTC)
    assert p["updated_label"] == "Oct 2, 1:14 PM"
    assert build_box_payload([], {}, NOW, tz=UTC)["updated_label"] == ""


def test_api_box_endpoint(tmp_path):
    path = str(tmp_path / "t.db")
    conn = db.connect(path)
    db.add_watch(conn, "Rolex", "Submariner Date", "116610LN", 4, None)
    conn.close()
    settings = Settings(ebay_client_id="", ebay_client_secret="", refresh_hours=24, db_path=path)
    with TestClient(create_app(settings, None, run_scheduler=False)) as c:
        body = c.get("/api/box").json()
    assert len(body["slots"]) == 8 and body["slots"][3]["watch"]["reference"] == "116610LN"
