#!/usr/bin/env python3
"""WORLD IN A DAY -- the front page of Sunday 22 November 2026.

A self-contained newspaper poster renderer.  It paints a 1024x1024
broadsheet front page (masthead, dateline, one lead story, eight
short stories in columns and a wire strip along the foot) onto an
in-memory RGB canvas and writes it out as a PNG.

Everything is done with the Python standard library alone: the
typeface is a little 5x7 bitmap alphabet defined below, the layout
engine wraps and centres text by measuring that alphabet, and the
PNG file is assembled chunk by chunk with zlib doing the squeezing.
The picture depends only on the words baked into this file, so two
runs always produce the same bytes.
"""

import os
import struct
import zlib

# ---------------------------------------------------------------- canvas

PAGE_W = 1024
PAGE_H = 1024

PAPER = (246, 241, 229)   # warm newsprint cream
INK = (23, 24, 28)        # near-black ink
SOFT = (110, 102, 86)     # faded brown-grey for small print
RED = (158, 27, 27)       # accent for kickers and tags
RULE_DARK = (35, 34, 30)
RULE_LIGHT = (178, 168, 144)


class Canvas:
    """A flat RGB pixel buffer with just the drawing we need."""

    def __init__(self, width, height, colour):
        self.width = width
        self.height = height
        self.pixels = bytearray(bytes(colour) * (width * height))

    def put(self, x, y, colour):
        if 0 <= x < self.width and 0 <= y < self.height:
            at = (y * self.width + x) * 3
            self.pixels[at:at + 3] = bytes(colour)

    def rect(self, x, y, w, h, colour):
        """Filled rectangle, clipped to the page."""
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(self.width, x + w)
        y1 = min(self.height, y + h)
        if x1 <= x0 or y1 <= y0:
            return
        stripe = bytes(colour) * (x1 - x0)
        for yy in range(y0, y1):
            at = (yy * self.width + x0) * 3
            self.pixels[at:at + len(stripe)] = stripe

    def hline(self, x, y, w, colour, thick=1):
        self.rect(x, y, w, thick, colour)

    def vline(self, x, y, h, colour, thick=1):
        self.rect(x, y, thick, h, colour)

    def frame(self, inset, colour, thick):
        self.hline(inset, inset, self.width - 2 * inset, colour, thick)
        self.hline(inset, self.height - inset - thick,
                   self.width - 2 * inset, colour, thick)
        self.vline(inset, inset, self.height - 2 * inset, colour, thick)
        self.vline(self.width - inset - thick, inset,
                   self.height - 2 * inset, colour, thick)


# ---------------------------------------------------------------- typeface
# A 5-wide, 7-tall bitmap alphabet.  Each glyph is seven rows of five
# characters; an "X" is ink, a "." is paper.  Drawn at integer scales.

GLYPHS = {
    "A": (".XXX.", "X...X", "X...X", "XXXXX", "X...X", "X...X", "X...X"),
    "B": ("XXXX.", "X...X", "X...X", "XXXX.", "X...X", "X...X", "XXXX."),
    "C": (".XXXX", "X....", "X....", "X....", "X....", "X....", ".XXXX"),
    "D": ("XXXX.", "X...X", "X...X", "X...X", "X...X", "X...X", "XXXX."),
    "E": ("XXXXX", "X....", "X....", "XXXX.", "X....", "X....", "XXXXX"),
    "F": ("XXXXX", "X....", "X....", "XXXX.", "X....", "X....", "X...."),
    "G": (".XXXX", "X....", "X....", "X..XX", "X...X", "X...X", ".XXX."),
    "H": ("X...X", "X...X", "X...X", "XXXXX", "X...X", "X...X", "X...X"),
    "I": (".XXX.", "..X..", "..X..", "..X..", "..X..", "..X..", ".XXX."),
    "J": ("..XXX", "....X", "....X", "....X", "....X", "X...X", ".XXX."),
    "K": ("X...X", "X..X.", "X.X..", "XX...", "X.X..", "X..X.", "X...X"),
    "L": ("X....", "X....", "X....", "X....", "X....", "X....", "XXXXX"),
    "M": ("X...X", "XX.XX", "X.X.X", "X.X.X", "X...X", "X...X", "X...X"),
    "N": ("X...X", "XX..X", "X.X.X", "X.X.X", "X..XX", "X...X", "X...X"),
    "O": (".XXX.", "X...X", "X...X", "X...X", "X...X", "X...X", ".XXX."),
    "P": ("XXXX.", "X...X", "X...X", "XXXX.", "X...X", "X....", "X...."),
    "Q": (".XXX.", "X...X", "X...X", "X...X", "X.X.X", "X..X.", ".XX.X"),
    "R": ("XXXX.", "X...X", "X...X", "XXXX.", "X.X..", "X..X.", "X...X"),
    "S": (".XXXX", "X....", "X....", ".XXX.", "....X", "....X", "XXXX."),
    "T": ("XXXXX", "..X..", "..X..", "..X..", "..X..", "..X..", "..X.."),
    "U": ("X...X", "X...X", "X...X", "X...X", "X...X", "X...X", ".XXX."),
    "V": ("X...X", "X...X", "X...X", "X...X", "X...X", ".X.X.", "..X.."),
    "W": ("X...X", "X...X", "X...X", "X.X.X", "X.X.X", "XX.XX", "X...X"),
    "X": ("X...X", ".X.X.", ".X.X.", "..X..", ".X.X.", ".X.X.", "X...X"),
    "Y": ("X...X", "X...X", ".X.X.", "..X..", "..X..", "..X..", "..X.."),
    "Z": ("XXXXX", "....X", "...X.", "..X..", ".X...", "X....", "XXXXX"),
    "0": (".XXX.", "X..XX", "X.X.X", "X.X.X", "XX..X", "X...X", ".XXX."),
    "1": ("..X..", ".XX..", "X.X..", "..X..", "..X..", "..X..", ".XXX."),
    "2": (".XXX.", "X...X", "....X", "...X.", "..X..", ".X...", "XXXXX"),
    "3": ("XXXX.", "....X", "....X", ".XXX.", "....X", "....X", "XXXX."),
    "4": ("...X.", "..XX.", ".X.X.", "X..X.", "XXXXX", "...X.", "...X."),
    "5": ("XXXXX", "X....", "XXXX.", "....X", "....X", "X...X", ".XXX."),
    "6": (".XXX.", "X....", "X....", "XXXX.", "X...X", "X...X", ".XXX."),
    "7": ("XXXXX", "....X", "...X.", "..X..", "..X..", "..X..", "..X.."),
    "8": (".XXX.", "X...X", "X...X", ".XXX.", "X...X", "X...X", ".XXX."),
    "9": (".XXX.", "X...X", "X...X", ".XXXX", "....X", "....X", ".XXX."),
    " ": (".....", ".....", ".....", ".....", ".....", ".....", "....."),
    ".": (".....", ".....", ".....", ".....", ".....", ".XX..", ".XX.."),
    ",": (".....", ".....", ".....", ".....", ".XX..", ".XX..", ".X..."),
    ";": (".....", ".XX..", ".XX..", ".....", ".XX..", ".XX..", ".X..."),
    "'": (".XX..", ".XX..", ".X...", ".....", ".....", ".....", "....."),
    "-": (".....", ".....", ".....", "XXXXX", ".....", ".....", "....."),
    ":": (".....", ".XX..", ".XX..", ".....", ".XX..", ".XX..", "....."),
    "/": ("....X", "....X", "...X.", "..X..", ".X...", "X....", "X...."),
    "%": ("XX..X", "XX.X.", "...X.", "..X..", ".X...", ".X.XX", "X..XX"),
    "·": (".....", ".....", ".....", ".XX..", ".XX..", ".....", "....."),
}

CELL_W = 5
CELL_H = 7
ADVANCE = 6  # glyph cells plus one column of air, in glyph units


def ink_width(text, scale, bold=False):
    """Pixel width of the ink a string leaves on the page."""
    if not text:
        return 0
    width = (len(text) - 1) * ADVANCE * scale + CELL_W * scale
    if bold:
        width += 1 if scale <= 3 else 2
    return width


def draw_text(cv, x, y, text, scale, colour, bold=False):
    """Draw one line of text with its top-left ink corner at (x, y)."""
    fat = (1 if scale <= 3 else 2) if bold else 0
    pen = x
    for ch in text:
        glyph = GLYPHS[ch]
        for row_i, row in enumerate(glyph):
            for col_i, mark in enumerate(row):
                if mark == "X":
                    cv.rect(pen + col_i * scale, y + row_i * scale,
                            scale + fat, scale, colour)
        pen += ADVANCE * scale
    return pen - x


def draw_centred(cv, box_x, box_w, y, text, scale, colour, bold=False):
    x = box_x + (box_w - ink_width(text, scale, bold)) // 2
    draw_text(cv, x, y, text, scale, colour, bold)
    return ink_width(text, scale, bold)


def wrap_words(text, scale, max_width, bold=False):
    """Greedy word wrap: split text into lines that fit max_width."""
    lines = []
    current = ""
    for word in text.split(" "):
        trial = word if not current else current + " " + word
        if ink_width(trial, scale, bold) <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_paragraph(cv, x, y, text, scale, width, leading, colour,
                   bold=False, centred=False):
    """Wrap and draw a block of text; return the height it used."""
    lines = wrap_words(text, scale, width, bold)
    for i, line in enumerate(lines):
        if centred:
            draw_centred(cv, x, width, y + i * leading, line, scale,
                         colour, bold)
        else:
            draw_text(cv, x, y + i * leading, line, scale, colour, bold)
    return len(lines) * leading


# ---------------------------------------------------------------- the news

LEAD_KICKER = "CLIMATE SUMMIT · ANTALYA, TURKEY"
LEAD_HEADLINE = ("COP31 TALKS COLLAPSE", "IN ANTALYA")
LEAD_DECK = (
    "THE DRAFT PACT NEVER MENTIONS FOSSIL FUELS. REJECTED BY THE EU, "
    "PANAMA, THE MARSHALL ISLANDS AND NORWAY, THE LONGEST COP IN "
    "HISTORY ENDS IN ITS FIRST BREAKDOWN SINCE COPENHAGEN 2009."
)

# (section tag, headline, summary) for the two three-column rows.
ROW_ONE = (
    ("MIDDLE EAST", "IRAN STRIKES US BASES IN BAHRAIN",
     "MISSILES AND DRONES HIT A CIVILIAN PLANT, INJURING TWO. "
     "TEHRAN CLAIMS TWO PATRIOT RADARS DESTROYED."),
    ("WASHINGTON", "'PUTIN IS NOT AMERICA'S FRIEND'",
     "INTEL CHIEF JAY CLAYTON BREAKS RANKS AFTER TRUMP'S WARM "
     "WORDS; WASHINGTON SEEKS UKRAINE DEAL BY EARLY JANUARY."),
    ("MEXICO", "MEXICO CAPTURES 'EL CHAPO ISIDRO'",
     "FBI MOST-WANTED FAUSTO ISIDRO MEZA FLORES TAKEN IN SINALOA; "
     "11 KILLED, INCLUDING 4 SOLDIERS."),
)

ROW_TWO = (
    ("UKRAINE", "RUSSIAN MISSILE HITS KRYVYI RIH",
     "A BOY OF SEVEN AND A WOMAN OF 20 KILLED AND 58 WOUNDED IN "
     "ZELENSKIY'S HOMETOWN."),
    ("TRADE", "EU-INDONESIA TRADE DEAL SIGNED",
     "LANDMARK PACT AFTER ALMOST TEN YEARS OF TALKS SCRAPS TARIFFS "
     "ON UP TO 98.5% OF GOODS."),
    ("INDONESIA", "CANDY-FACTORY FIRE IN CIKANDE",
     "THREE WORKERS DEAD AND 36 MISSING AFTER FIRE SWEEPS AN "
     "INDONESIAN CANDY FACTORY."),
)

# The two wider stories along the foot of the page.
FOOT_STORIES = (
    ("SPORT · CRICKET", "INDIA DECLARE AT 720/9",
     "A 352-RUN FIRST-TEST LEAD OVER NEW ZEALAND IN WELLINGTON."),
    ("UNITED STATES", "SEATTLE AIRPORT ICE ARRESTS CONDEMNED",
     "AIRPORT ARRESTS CONDEMNED; LA-BOUND ALASKA AIRLINES FLIGHT "
     "DELAYED."),
)

WIRE_LINES = (
    "THE WIRE · TANKERS STRUCK NEAR HORMUZ · NEPAL PM BALENDRA SHAH "
    "VISITS INDIA",
    "JEWELLER PAOLO BULGARI DIES AT 89 · DRONE HITS UN FACILITY IN "
    "SUDAN",
)


# ---------------------------------------------------------------- layout

MARGIN = 44                       # left/right edge of the text block
TEXT_W = PAGE_W - 2 * MARGIN      # 936
COL_W = 296                       # three-column measure
COL_XS = (MARGIN, 364, 684)       # column left edges (24px gutters)
ROW_H = 156                       # height of one story row


def story_block(cv, x, y, w, tag, headline, body):
    """One column story: red tag, bold headline, plain summary."""
    draw_text(cv, x, y, tag, 2, RED, bold=True)
    head_y = y + 18
    head_h = draw_paragraph(cv, x, head_y, headline, 3, w, 23, INK,
                            bold=True)
    draw_paragraph(cv, x, head_y + head_h + 5, body, 2, w, 16, INK)


def build_page():
    cv = Canvas(PAGE_W, PAGE_H, PAPER)

    # Page furniture: a heavy outer frame and a hairline inside it.
    cv.frame(14, RULE_DARK, 3)
    cv.frame(22, RULE_DARK, 1)

    # Folio strip above the nameplate.
    draw_text(cv, MARGIN, 34, "ONE PAGE · THE WHOLE PLANET", 2, SOFT)
    right = "LATE FINAL EDITION"
    draw_text(cv, PAGE_W - MARGIN - ink_width(right, 2), 34, right, 2,
              SOFT)
    cv.hline(MARGIN, 52, TEXT_W, RULE_DARK, 1)

    # Nameplate.
    draw_centred(cv, 0, PAGE_W, 60, "WORLD IN A DAY", 9, INK, bold=True)
    cv.hline(MARGIN, 134, TEXT_W, RULE_DARK, 3)
    cv.hline(MARGIN, 141, TEXT_W, RULE_DARK, 1)

    # Dateline: the day, named in full, on its own line.
    draw_centred(cv, 0, PAGE_W, 150, "SUNDAY 22 NOVEMBER 2026", 4, INK,
                 bold=True)
    cv.hline(MARGIN, 188, TEXT_W, RULE_DARK, 1)
    cv.hline(MARGIN, 192, TEXT_W, RULE_DARK, 3)

    # The lead story, centred like a broadsheet splash.
    draw_centred(cv, 0, PAGE_W, 204, LEAD_KICKER, 3, RED, bold=True)
    draw_centred(cv, 0, PAGE_W, 232, LEAD_HEADLINE[0], 6, INK, bold=True)
    draw_centred(cv, 0, PAGE_W, 280, LEAD_HEADLINE[1], 6, INK, bold=True)
    draw_paragraph(cv, MARGIN, 338, LEAD_DECK, 3, TEXT_W, 24, INK,
                   centred=True)
    cv.hline(MARGIN, 444, TEXT_W, RULE_DARK, 3)
    cv.hline(MARGIN, 450, TEXT_W, RULE_DARK, 1)

    # Two rows of three column stories, with hairlines between columns.
    for row_i, row in enumerate((ROW_ONE, ROW_TWO)):
        top = 464 + row_i * (ROW_H + 24)
        for col_i, (tag, headline, body) in enumerate(row):
            story_block(cv, COL_XS[col_i], top, COL_W, tag, headline,
                        body)
        for rule_x in (351, 671):
            cv.vline(rule_x, top + 2, 168, RULE_LIGHT, 1)
        if row_i == 0:
            cv.hline(MARGIN, top + ROW_H + 8, TEXT_W, RULE_LIGHT, 1)

    # The foot stories, two abreast on a wider measure.
    foot_y = 464 + 2 * (ROW_H + 24) + 16
    cv.hline(MARGIN, foot_y - 10, TEXT_W, RULE_DARK, 1)
    for i, (tag, headline, body) in enumerate(FOOT_STORIES):
        story_block(cv, MARGIN + i * 480, foot_y, 456, tag, headline,
                    body)
    cv.vline(511, foot_y + 2, 95, RULE_LIGHT, 1)

    # The wire: late scraps reversed out of a black band at the foot.
    band_y = 948
    cv.rect(MARGIN, band_y, TEXT_W, 50, INK)
    for i, line in enumerate(WIRE_LINES):
        draw_centred(cv, MARGIN, TEXT_W, band_y + 7 + i * 20, line, 2,
                     PAPER)

    return cv


# ---------------------------------------------------------------- PNG out

def png_bytes(cv):
    """Encode the canvas as a PNG: header, one data chunk, end."""
    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", cv.width, cv.height, 8, 2, 0, 0, 0)
    stride = cv.width * 3
    raw = bytearray()
    for yy in range(cv.height):
        raw.append(0)  # filter type 0 on every scanline
        raw += cv.pixels[yy * stride:(yy + 1) * stride]
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))


def main():
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(out_dir, exist_ok=True)
    page = build_page()
    with open(os.path.join(out_dir, "entry.png"), "wb") as fh:
        fh.write(png_bytes(page))


if __name__ == "__main__":
    main()
