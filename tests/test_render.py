"""Tests for the card renderer. Run: python -m pytest tests -q"""
import datetime
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import render_cards as rc  # noqa: E402

PROFILE = json.loads((ROOT / "data" / "profile.json").read_text(encoding="utf-8"))


def days(n=371, end=datetime.date(2026, 11, 20), counts=None):
    counts = counts or {}
    out = []
    for i in range(n):
        d = end - datetime.timedelta(days=n - 1 - i)
        out.append({"date": d.isoformat(), "count": counts.get(d.isoformat(), 0)})
    return out


def contrib(**kw):
    base = {"login": "x", "public_repos": 5, "total": 0, "days": days()}
    base.update(kw)
    return base


def all_cards(animated=True, data=None, profile=None):
    return rc.render_all(profile or PROFILE, data or contrib(), animated=animated)


def test_renders_expected_files():
    cards = all_cards()
    assert set(cards) == {"hero.svg", "notchland.svg", "minimath.svg", "driveparty.svg", "activity.svg"}


def test_every_card_is_wellformed_svg():
    for name, svg in all_cards().items():
        root = ET.fromstring(svg)
        assert root.tag == "{http://www.w3.org/2000/svg}svg", name
        assert root.get("viewBox"), name


def test_cards_are_safe_inside_an_img_tag():
    # GitHub shows README images in an <img>: no scripts, no outside requests.
    for name, svg in all_cards().items():
        assert "<script" not in svg, name
        assert "<foreignObject" not in svg, name
        outside = re.findall(r'(?:href|src)="(https?://[^"]+)"', svg) + re.findall(r"url\((https?://[^)]+)\)", svg)
        assert outside == [], name


def test_fonts_are_embedded_and_small():
    for name, svg in all_cards().items():
        assert svg.count("data:font/woff;base64,") == 2, name
        assert len(svg.encode("utf-8")) < 80_000, name


def test_static_mode_has_no_animation():
    for name, svg in all_cards(animated=False).items():
        assert "@keyframes" not in svg, name
        assert "animation" not in svg, name


def test_animated_mode_respects_reduced_motion():
    for name, svg in all_cards().items():
        assert "@keyframes" in svg, name
        assert "prefers-reduced-motion" in svg, name


def test_output_is_deterministic():
    assert all_cards() == all_cards()


def test_text_is_escaped():
    profile = json.loads(json.dumps(PROFILE))
    profile["products"][0]["name"] = "A & B <x>"
    svg = all_cards(profile=profile)["notchland.svg"]
    ET.fromstring(svg)
    assert "A &amp; B &lt;x&gt;" in svg


def test_activity_numbers_come_from_data():
    counts = {"2026-11-02": 1, "2026-03-19": 2, "2026-03-13": 1}
    svg = all_cards(data=contrib(total=4, public_repos=7, days=days(counts=counts)))["activity.svg"]
    assert ">4</text>" in svg  # total
    assert ">3</text>" in svg  # active days
    assert ">7</text>" in svg  # public repos


def test_activity_draws_53_weeks_of_cells():
    svg = all_cards()["activity.svg"]
    cells = re.findall(r'class="c l\d"', svg)
    assert 365 <= len(cells) <= 371


def test_busiest_day_gets_top_level_and_empty_day_gets_zero():
    counts = {"2026-11-02": 8, "2026-11-03": 1}
    svg = all_cards(data=contrib(total=9, days=days(counts=counts)))["activity.svg"]
    assert svg.count('class="c l4"') == 1
    assert svg.count('class="c l1"') == 1
    assert svg.count('class="c l0"') >= 360


def test_missing_or_empty_data_still_renders():
    for data in ({}, {"days": []}, {"days": None, "total": None, "public_repos": None}):
        svg = rc.render_all(PROFILE, data, animated=True)["activity.svg"]
        ET.fromstring(svg)
        assert ">0</text>" in svg


def test_load_contributions_survives_missing_and_broken_file(tmp_path):
    assert rc.load_json(tmp_path / "nope.json", default={}) == {}
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert rc.load_json(bad, default={}) == {}
