#!/usr/bin/env python3
"""Draw the profile README cards as self-contained, animated SVG files.

    python scripts/render_cards.py            # animated cards -> cards/
    STATIC=1 python scripts/render_cards.py   # final frame only, for screenshots

GitHub shows README images inside <img>, where scripts and outside requests
are blocked. So every card carries its own CSS animations and its own fonts
(subset to the glyphs it uses and embedded as base64).

Text and colors live in data/profile.json. The activity card reads
data/contributions.json, which scripts/fetch_contributions.py writes.
"""
from __future__ import annotations

import base64
import datetime
import io
import json
import math
import os
from functools import lru_cache
from pathlib import Path
from xml.sax.saxutils import escape

from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
FONT_FILES = {
    "display": ROOT / "assets" / "fonts" / "SpaceGrotesk-Medium.ttf",
    "body": ROOT / "assets" / "fonts" / "Manrope-Medium.ttf",
}
FAMILY = {"display": "DBDisplay", "body": "DBBody"}
FALLBACK = "ui-sans-serif,system-ui,-apple-system,'Segoe UI',sans-serif"

KEYFRAMES = """
@keyframes rise{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:translateY(0)}}
@keyframes fade{from{opacity:0}to{opacity:1}}
@keyframes pop{from{opacity:0;transform:scale(.3)}to{opacity:1;transform:scale(1)}}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes bob{0%,100%{transform:translateY(0)}50%{transform:translateY(-7px)}}
@keyframes eq{0%,100%{transform:scaleY(.3)}50%{transform:scaleY(1)}}
@keyframes island{0%,10%{opacity:0;transform:scale(.42)}20%,80%{opacity:1;transform:scale(1)}90%,100%{opacity:0;transform:scale(.42)}}
@keyframes draw{0%,8%{stroke-dashoffset:100}62%,100%{stroke-dashoffset:0}}
@keyframes pulse{0%{opacity:.75;transform:scale(1)}70%,100%{opacity:0;transform:scale(2.8)}}
.rise{animation:rise .9s cubic-bezier(.2,.7,.2,1) both}
.fade{animation:fade .9s ease both}
.pop{animation:pop .7s cubic-bezier(.2,1.3,.4,1) both;transform-box:fill-box;transform-origin:center}
.spin{animation:spin 16s linear infinite;transform-box:fill-box;transform-origin:center}
.ring{animation:spin 48s linear infinite;transform-box:fill-box;transform-origin:center}
.bob{animation:bob 2.8s ease-in-out infinite}
.eq{animation:eq .9s ease-in-out infinite;transform-box:fill-box;transform-origin:center bottom}
.island{animation:island 7s cubic-bezier(.3,.9,.3,1) infinite;transform-box:fill-box;transform-origin:center top}
.draw{animation:draw 5s ease-in-out infinite}
.pulse{animation:pulse 2.4s ease-out infinite;transform-box:fill-box;transform-origin:center}
.col{animation:fade .5s ease both}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
"""


def n(value: float) -> str:
    """Short number for SVG attributes."""
    return f"{value:.2f}".rstrip("0").rstrip(".")


def load_json(path: Path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


# ---------------------------------------------------------------- fonts

@lru_cache(maxsize=None)
def _metrics(kind: str):
    font = TTFont(FONT_FILES[kind], recalcTimestamp=False)
    return font.getBestCmap(), font["hmtx"].metrics, font["head"].unitsPerEm


def text_width(kind: str, text: str, size: float, spacing: float = 0.0) -> float:
    cmap, hmtx, upm = _metrics(kind)
    units = sum(hmtx[cmap[ord(ch)]][0] if ord(ch) in cmap else upm * 0.5 for ch in text)
    return units * size / upm + spacing * len(text)


@lru_cache(maxsize=None)
def font_face(kind: str, chars: str) -> str:
    """@font-face rule holding only the glyphs in `chars`."""
    font = TTFont(FONT_FILES[kind], recalcTimestamp=False)
    options = subset.Options()
    options.layout_features = ["kern"]
    options.name_IDs = [1, 2]
    options.hinting = False
    options.notdef_outline = True
    subsetter = subset.Subsetter(options)
    subsetter.populate(text=chars)
    subsetter.subset(font)
    font.flavor = "woff"
    buffer = io.BytesIO()
    font.save(buffer)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return (
        f"@font-face{{font-family:'{FAMILY[kind]}';"
        f"src:url(data:font/woff;base64,{encoded}) format('woff')}}"
    )


# ---------------------------------------------------------------- card

class Card:
    def __init__(self, width: int, height: int, theme: dict, animated: bool, label: str):
        self.w, self.h, self.t, self.animated, self.label = width, height, theme, animated, label
        self.parts: list[str] = []
        self.chars = {"display": set(" "), "body": set(" ")}
        self.extra_css = ""

    def add(self, markup: str) -> None:
        self.parts.append(markup)

    def use(self, kind: str, text: str) -> str:
        """Record glyphs for the font subset and return XML-safe text."""
        self.chars[kind].update(text)
        return escape(text)

    def text(self, kind, x, y, text, size, fill, spacing=0.0, anchor=None, opacity=None) -> str:
        attrs = f'class="{kind[0]}" x="{n(x)}" y="{n(y)}" font-size="{n(size)}" fill="{fill}"'
        if spacing:
            attrs += f' letter-spacing="{n(spacing)}"'
        if anchor:
            attrs += f' text-anchor="{anchor}"'
        if opacity is not None:
            attrs += f' opacity="{n(opacity)}"'
        return f"<text {attrs}>{self.use(kind, text)}</text>"

    def g(self, inner: str, cls: str = "", delay: float | None = None) -> str:
        """Group that animates only when the card is animated."""
        if not self.animated or not cls:
            return f"<g>{inner}</g>"
        style = f' style="animation-delay:{n(delay)}s"' if delay else ""
        return f'<g class="{cls}"{style}>{inner}</g>'

    def at(self, x: float, y: float, inner: str) -> str:
        return f'<g transform="translate({n(x)} {n(y)})">{inner}</g>'

    def asterisk(self, cx, cy, r, width, spin=True) -> str:
        spokes = "".join(f'<path d="M{n(-r)} 0H{n(r)}" transform="rotate({a})"/>' for a in (0, 45, 90, 135))
        star = f'<g stroke="{self.t["accent"]}" stroke-width="{n(width)}" stroke-linecap="round">{spokes}</g>'
        return self.at(cx, cy, self.g(star, "spin") if spin else star)

    def arrow(self, x, y, size, color, width=1.6) -> str:
        s = n(size)
        return (
            f'<path transform="translate({n(x)} {n(y)})" d="M0 {s}L{s} 0M{n(size * .3)} 0H{s}V{n(size * .7)}" '
            f'fill="none" stroke="{color}" stroke-width="{n(width)}" stroke-linecap="round" stroke-linejoin="round"/>'
        )

    def svg(self) -> str:
        t = self.t
        faces = "".join(font_face(kind, "".join(sorted(self.chars[kind]))) for kind in ("display", "body"))
        css = (
            faces
            + f".d{{font-family:'{FAMILY['display']}',{FALLBACK}}}"
            + f".b{{font-family:'{FAMILY['body']}',{FALLBACK}}}"
            + "text{font-kerning:normal}"
        )
        if self.animated:
            css += KEYFRAMES.replace("\n", "") + self.extra_css
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" '
            f'width="{self.w}" height="{self.h}" role="img" aria-label="{escape(self.label, {chr(34): "&quot;"})}">'
            f"<style>{css}</style>"
            f'<defs><clipPath id="clip"><rect width="{self.w}" height="{self.h}" rx="{self.radius}"/></clipPath></defs>'
            + "".join(self.parts)
            + "</svg>\n"
        )

    radius = 26

    def shell(self, fill: str) -> None:
        self.add(
            f'<rect x=".5" y=".5" width="{self.w - 1}" height="{self.h - 1}" rx="{self.radius}" '
            f'fill="{fill}" stroke="{self.t["line"]}"/>'
        )


# ---------------------------------------------------------------- hero

def hero(profile: dict, animated: bool) -> str:
    t, h = profile["theme"], profile["hero"]
    c = Card(1200, 480, t, animated, f'{profile["brand"]} — {" ".join(h["lines"])}')
    c.shell(t["bg"])
    pad = 56

    grid = "".join(f'<path d="M{x} 0V480"/>' for x in range(96, 1200, 96))
    c.add(f'<g clip-path="url(#clip)" stroke="{t["line"]}" stroke-opacity=".38">{grid}</g>')

    # top row: wordmark on the left, site on the right
    brand_w = text_width("display", profile["brand"], 28, -1.2)
    top = c.text("display", pad, 76, profile["brand"], 28, t["text"], -1.2)
    top += c.asterisk(pad + brand_w + 13, 66, 8, 2.4)
    top += c.text("body", 1126, 74, profile["site_label"], 15, t["muted"], anchor="end")
    top += c.arrow(1134, 63, 10, t["muted"])
    c.add(c.g(top, "fade"))

    c.add(c.g(c.text("body", pad, 138, h["eyebrow"], 13, t["muted"], 3.2), "rise", 0.1))

    size, spacing = 92, -4.6
    for i, line in enumerate(h["lines"]):
        y = 250 + i * 90
        c.add(c.g(c.text("display", pad, y, line, size, t["text"], spacing), "rise", 0.2 + i * 0.15))
    last_w = text_width("display", h["lines"][-1], size, spacing)
    last_y = 250 + (len(h["lines"]) - 1) * 90
    c.add(c.g(c.asterisk(pad + last_w + 44, last_y - 34, 25, 6.5), "pop", 0.75))

    c.add(c.g(c.text("body", pad, 392, h["body"], 17, t["muted"]), "rise", 0.5))

    # round mark on the right
    cx, cy = 1012, 244
    mark = (
        c.g(
            f'<circle cx="{cx}" cy="{cy}" r="112" fill="none" stroke="{t["accent"]}" stroke-width="2" '
            f'stroke-dasharray="1.5 11.5" stroke-linecap="round"/>',
            "ring",
        )
        + f'<circle cx="{cx}" cy="{cy}" r="92" fill="{t["panel"]}" stroke="{t["line"]}"/>'
        + f'<text class="d" x="{cx}" y="{cy + 22}" font-size="68" letter-spacing="-3" text-anchor="middle" '
        f'fill="{t["text"]}">{c.use("display", h["mark"])}<tspan fill="{t["accent"]}">{c.use("display", ".")}</tspan></text>'
        + c.text("body", cx, 394, h["byline"], 13, t["muted"], anchor="middle")
    )
    c.add(c.g(mark, "fade", 0.45))

    # scrolling strip along the bottom
    c.add(f'<path d="M0 424.5H1200" stroke="{t["line"]}"/>')
    one, x = "", 0.0
    for item in h["marquee"]:
        one += c.text("body", x, 457, item, 15, t["text"], opacity=0.86)
        x += text_width("body", item, 15) + 22
        one += c.asterisk(x + 6, 452, 5.5, 1.7, spin=False)
        x += 12 + 22
    seq_w = x
    copies = math.ceil(1200 / seq_w) + 1
    strip = "".join(c.at(i * seq_w, 0, one) for i in range(copies))
    if animated:
        c.extra_css += (
            f"@keyframes slide{{to{{transform:translateX(-{n(seq_w)}px)}}}}"
            f".slide{{animation:slide {n(seq_w / 34)}s linear infinite}}"
        )
    c.add(f'<g clip-path="url(#clip)">{c.g(c.at(pad, 0, c.g(strip, "slide")), "fade", 0.9)}</g>')
    return c.svg()


# ---------------------------------------------------------------- products

def art_notch(c: Card) -> str:
    t = c.t
    out = f'<rect width="334" height="24" fill="{t["panel"]}"/>'
    out += "".join(f'<circle cx="{x}" cy="12" r="3" fill="{t["line"]}"/>' for x in (16, 28, 40))
    out += c.text("body", 320, 16, "9:41", 9.5, t["muted"], anchor="end")
    out += '<path d="M123 0h88v9a11 11 0 0 1-11 11h-66a11 11 0 0 1-11-11z" fill="#000"/>'
    bars = "".join(
        c.g(f'<rect x="{x}" y="19" width="4" height="20" rx="2" fill="{t["accent"]}"/>', "eq", d)
        for x, d in ((70, 0), (78, 0.3), (86, 0.15))
    )
    island = (
        f'<path d="M-104 0h208v32a26 26 0 0 1-26 26h-156a26 26 0 0 1-26-26z" fill="#000" stroke="{t["line"]}"/>'
        f'<rect x="-88" y="17" width="24" height="24" rx="7" fill="{t["accent"]}"/>'
        + c.text("body", -54, 33, "DBLabs · Çalıyor", 11, t["text"])
        + bars
    )
    out += c.at(167, 0, c.g(island, "island"))
    out += c.text("display", 167, 104, "Make room for the little things.", 13, t["muted"], anchor="middle")
    return out


def art_math(c: Card) -> str:
    t = c.t
    out = ""
    for i, (cx, symbol) in enumerate(((67, "+"), (167, "×"), (267, "÷"))):
        hot = i == 1
        tile = (
            f'<rect x="{cx - 31}" y="22" width="62" height="62" rx="17" '
            f'fill="{t["accent"] if hot else t["panel"]}" stroke="{t["accent"] if hot else t["line"]}"/>'
            + c.text("display", cx, 66, symbol, 36, t["bg"] if hot else t["text"], anchor="middle")
        )
        out += c.g(tile, "bob", i * 0.28)
    out += c.text("body", 167, 114, "LESS SCROLL. MORE PLAY.", 9.5, t["muted"], 2.4, anchor="middle")
    return out


def art_route(c: Card) -> str:
    t = c.t
    d = "M34 98C92 98 92 36 160 42S246 102 300 48"
    out = f'<circle cx="18" cy="19" r="3.5" fill="{t["accent"]}"/>'
    out += c.text("body", 28, 22.5, "CANLI KONUM", 9.5, t["muted"], 2.2)
    out += (
        f'<path d="{d}" fill="none" stroke="{t["line"]}" stroke-width="3" stroke-linecap="round" stroke-dasharray="1 9"/>'
    )
    line = (
        f'<path d="{d}" pathLength="100" fill="none" stroke="{t["accent"]}" stroke-width="3" '
        f'stroke-linecap="round" stroke-dasharray="100" stroke-dashoffset="0"'
    )
    out += line + (' class="draw"/>' if c.animated else "/>")
    out += f'<circle cx="34" cy="98" r="6" fill="{t["text"]}"/>'
    for (x, y), delay in (((160, 42), 0.0), ((300, 48), 1.2)):
        ring = f'<circle cx="{x}" cy="{y}" r="7" fill="none" stroke="{t["accent"]}" stroke-width="2" opacity="0"/>'
        out += c.g(ring, "pulse", delay) if c.animated else ""
    out += f'<circle cx="160" cy="42" r="6" fill="{t["accent"]}"/>'
    out += f'<circle cx="300" cy="48" r="6.5" fill="{t["bg"]}" stroke="{t["accent"]}" stroke-width="3"/>'
    return out


ART = {"notch": art_notch, "math": art_math, "route": art_route}


def product(profile: dict, index: int, animated: bool) -> str:
    t, p = profile["theme"], profile["products"][index]
    c = Card(390, 330, t, animated, f'{p["name"]} ({p["platform"]}) — {p["tagline"]}')
    c.radius = 24
    c.shell(t["panel"])
    pad = 28

    body = c.text("body", pad, 44, f'{p["name"].upper()} / {p["platform"]}', 11, t["muted"], 2)
    body += c.text("body", 362, 44, f"{index + 1:02d}", 11, t["muted"], 1, anchor="end")
    body += (
        f'<defs><clipPath id="art"><rect width="334" height="132" rx="16"/></clipPath></defs>'
        + c.at(
            pad,
            62,
            f'<rect width="334" height="132" rx="16" fill="{t["bg"]}"/>'
            f'<g clip-path="url(#art)">{ART[p["art"]](c)}</g>'
            f'<rect x=".5" y=".5" width="333" height="131" rx="16" fill="none" stroke="{t["line"]}"/>',
        )
    )
    body += c.text("display", pad, 242, p["name"], 28, t["text"], -1)
    body += c.text("body", pad, 270, p["tagline"], 14.5, t["muted"])
    cta = "Keşfet"
    body += c.text("body", pad, 305, cta, 13, t["accent"])
    body += c.arrow(pad + text_width("body", cta, 13) + 8, 296, 8.5, t["accent"])
    c.add(c.g(body, "rise", 0.12 * index))
    return c.svg()


# ---------------------------------------------------------------- activity

def normalize(data: dict, today: datetime.date | None = None) -> tuple[dict, datetime.date]:
    """Return ({date: count}, last_day) from whatever the data file holds."""
    counts: dict[datetime.date, int] = {}
    for day in (data or {}).get("days") or []:
        try:
            counts[datetime.date.fromisoformat(day["date"])] = max(0, int(day.get("count") or 0))
        except (KeyError, TypeError, ValueError):
            continue
    last = max(counts) if counts else (today or datetime.date.today())
    return counts, last


def level(count: int, peak: int) -> int:
    if count <= 0 or peak <= 0:
        return 0
    return max(1, min(4, math.ceil(count / peak * 4)))


def activity(profile: dict, data: dict, animated: bool) -> str:
    t, a = profile["theme"], profile["activity"]
    c = Card(1200, 240, t, animated, a["eyebrow"])
    c.shell(t["panel"])
    pad = 56

    counts, last = normalize(data)
    sunday = last - datetime.timedelta(days=(last.weekday() + 1) % 7)
    start = sunday - datetime.timedelta(weeks=52)
    window = {d: v for d, v in counts.items() if start <= d <= last}
    total = sum(window.values())
    active = sum(1 for v in window.values() if v > 0)
    repos = max(0, int((data or {}).get("public_repos") or 0))
    peak = max(window.values(), default=0)

    c.add(c.g(c.text("body", pad, 52, a["eyebrow"], 12, t["muted"], 3), "fade"))

    rows = ((total, "total"), (active, "active_days"), (repos, "public_repos"))
    for i, (value, key) in enumerate(rows):
        y = 112 + i * 46
        number = str(value)
        row = c.text("display", pad, y, number, 32, t["accent"] if i == 0 else t["text"], -1)
        row += c.text("body", pad + text_width("display", number, 32, -1) + 12, y - 2, a["labels"][key], 14, t["muted"])
        c.add(c.g(row, "rise", 0.1 + i * 0.1))

    # heat map: 53 week columns, Sunday on top
    x0, y0, pitch, cell = 300, 72, 15.9, 12.4
    css = (
        f'.c{{fill:{t["accent"]}}}.l0{{fill:{t["line"]};fill-opacity:.55}}'
        ".l1{fill-opacity:.28}.l2{fill-opacity:.5}.l3{fill-opacity:.75}.l4{fill-opacity:1}"
    )
    c.add(f"<style>{css}</style>")
    c.add(f'<defs><rect id="k" width="{cell}" height="{cell}" rx="3"/></defs>')

    labels, previous = [], None
    for col in range(53):
        month = (start + datetime.timedelta(weeks=col)).month
        if month != previous:
            if labels and col - labels[-1][0] < 3:
                labels.pop()
            labels.append((col, month))
            previous = month
    for col, month in labels:
        if col <= 50:
            c.add(c.text("body", x0 + col * pitch, 58, a["months"][month - 1], 11, t["muted"]))

    for col in range(53):
        cells = ""
        for row in range(7):
            day = start + datetime.timedelta(days=col * 7 + row)
            if day > last:
                break
            cells += f'<use href="#k" class="c l{level(counts.get(day, 0), peak)}" x="{n(x0 + col * pitch)}" y="{n(y0 + row * pitch)}"/>'
        c.add(c.g(cells, "col", 0.25 + col * 0.016))

    c.add(c.text("body", x0, 214, a["note"], 12, t["muted"]))
    low, high = a["legend"]
    x = 1143.0
    legend = c.text("body", x, 214, high, 11, t["muted"], anchor="end")
    x -= text_width("body", high, 11) + 8
    for lv in (4, 3, 2, 1, 0):
        x -= cell
        legend += f'<use href="#k" class="lg c l{lv}" x="{n(x)}" y="{n(214 - 10.4)}"/>'
        x -= 3.5
    legend += c.text("body", x - 4.5, 214, low, 11, t["muted"], anchor="end")
    c.add(c.g(legend, "fade", 0.9))
    return c.svg()


# ---------------------------------------------------------------- main

def render_all(profile: dict, data: dict, animated: bool = True) -> dict[str, str]:
    cards = {"hero.svg": hero(profile, animated)}
    for index, item in enumerate(profile["products"]):
        cards[f'{item["slug"]}.svg'] = product(profile, index, animated)
    cards["activity.svg"] = activity(profile, data, animated)
    return cards


def main() -> None:
    profile = load_json(ROOT / "data" / "profile.json", default=None)
    if profile is None:
        raise SystemExit("data/profile.json is missing or not valid JSON")
    data = load_json(ROOT / "data" / "contributions.json", default={})
    out = Path(os.environ.get("CARDS_DIR", ROOT / "cards"))
    out.mkdir(parents=True, exist_ok=True)
    animated = os.environ.get("STATIC") != "1"
    for name, svg in render_all(profile, data, animated).items():
        (out / name).write_text(svg, encoding="utf-8")
        print(f"{name:16} {len(svg.encode('utf-8')) / 1024:5.1f} KB")


if __name__ == "__main__":
    main()
