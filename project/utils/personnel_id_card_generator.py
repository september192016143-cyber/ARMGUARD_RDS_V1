# personnel_id_card_generator.py
"""
Personnel ID Card Generator  -  utils/personnel_id_card_generator.py

Uses official template PNGs (media/personnel_id_temp/front.png &
media/personnel_id_temp/back.png) as base layers, then overlays
personnel-specific data on top.

Front : photo | rank / name / AFSN / PAF | contact nr | personnel ID
Back  : QR code | contact nr | personnel ID

Output (MEDIA_ROOT/personnel_id_cards/):
    <pid>_front.png
    <pid>_back.png
    <pid>.png   (both sides side-by-side)
"""

import os
import logging
from PIL import Image, ImageDraw, ImageFont

from django.conf import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Card dimensions (must match the template images)
# ---------------------------------------------------------------------------
CARD_W = 638
CARD_H = 1013

# ---------------------------------------------------------------------------
# Colours (extracted from template pixel analysis)
# ---------------------------------------------------------------------------
NAVY        = (26, 25, 106)   # header + base bar
WHITE       = (255, 255, 255)
BODY_NAVY   = (26, 25, 106)   # dark text on white body
FOOTER_TEXT = (255, 255, 255) # white text on purple/navy footer

# ---------------------------------------------------------------------------
# Layout constants  (pixels, scanned from new PAF 950CEWW template images)
#
# FRONT  "CARD-FRONT.png"  (638 x 1013 px)
#  PAF navy header      : y   0 .. 127
#  Orange chevron band  : y 128 .. 231
#  White photo box      : x 114..519 ,  y 232..637  (405 x 405 px)
#  Dark info band       : y 640 .. 806  ← text goes here
#  Orange chevron       : y 858 .. 915
#  Navy footer "ARMORY CARD" : y 920 .. 1012
#
# BACK  "back.png"  (638 x 1013 px)
#  PAF navy header      : y   0 .. 127
#  Orange chevron band  : y 128 .. 236
#  White card body      : y 237 .. 840
#  White photo box      : x 162..474 ,  y 237..580  (312 x 343 px)
#  Non-transferable text: y 600 .. 780  (pre-printed on template)
#  Orange chevron       : y 790 .. 880
#  Gray footer          : y 880 .. 1012  ← Personnel ID text here
# ---------------------------------------------------------------------------

# Front card photo placeholder  (405 x 405 px) — CARD-FRONT.png
PHOTO_X1, PHOTO_Y1 = 114, 232
PHOTO_X2, PHOTO_Y2 = 519, 637
PHOTO_W = PHOTO_X2 - PHOTO_X1   # 405 px
PHOTO_H = PHOTO_Y2 - PHOTO_Y1   # 405 px

# Front info-band text rows  (white text on dark navy band, y 640..806)
NAME_LINE_Y = 700   # rank + full name + AFSN + PAF
CATEGORY_Y  = 742   # ENLISTED or OFFICER
ID_FRONT_Y  = 775   # Personnel ID value

# Back card photo placeholder  (312 x 343 px) — back.png
BACK_PHOTO_X1, BACK_PHOTO_Y1 = 162, 237
BACK_PHOTO_X2, BACK_PHOTO_Y2 = 474, 580
BACK_PHOTO_W = BACK_PHOTO_X2 - BACK_PHOTO_X1   # 312 px
BACK_PHOTO_H = BACK_PHOTO_Y2 - BACK_PHOTO_Y1   # 343 px

# Back footer text row  (dark text on gray band, y 880..975)
BACK_FOOTER_ID_Y = 935   # Personnel ID value

# ---------------------------------------------------------------------------
# Font helpers
# ---------------------------------------------------------------------------
_FONT_CACHE: dict = {}


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    key = (size, bold)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    candidates = (
        [r"C:\Windows\Fonts\arialbd.ttf",
         r"C:\Windows\Fonts\calibrib.ttf",
         r"C:\Windows\Fonts\segoeuib.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
        if bold else
        [r"C:\Windows\Fonts\arial.ttf",
         r"C:\Windows\Fonts\calibri.ttf",
         r"C:\Windows\Fonts\segoeui.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    )
    font = None
    for path in candidates:
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, size)
                break
            except (IOError, OSError):
                continue
    _FONT_CACHE[key] = font or ImageFont.load_default()
    return _FONT_CACHE[key]


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

def _centered_text(draw: ImageDraw.ImageDraw, y: int, text: str, font,
                   color=WHITE, canvas_w: int = CARD_W):
    """Draw *text* horizontally centred at row *y*."""
    bb = draw.textbbox((0, 0), text, font=font)
    x  = (canvas_w - (bb[2] - bb[0])) // 2
    draw.text((x, y), text, font=font, fill=color)


def _load_template(filename: str) -> Image.Image:
    """Return a fresh RGB copy of a template PNG from the non-public card_templates directory."""
    path = os.path.join(settings.CARD_TEMPLATES_DIR, "personnel_id_temp", filename)
    return Image.open(path).convert("RGB")


def _paste_image_in_rect(canvas: Image.Image,
                          x1: int, y1: int, x2: int, y2: int,
                          source_path: str,
                          rounded_radius: int = 12,
                          mode: str = "cover"):
    """
    Paste *source_path* into the rectangle (x1,y1)-(x2,y2) on *canvas*.
    mode="cover"   – scale to fill, crop excess  (good for photos)
    mode="contain" – scale to fit inside, white-fill remainder (good for QR)
    """
    rw = x2 - x1
    rh = y2 - y1

    with Image.open(source_path) as src:
        src_rgba = src.convert("RGBA")

    src_ratio  = src_rgba.width / src_rgba.height
    rect_ratio = rw / rh

    if mode == "contain":
        # Scale to fit inside — no cropping, white-fill any remaining space
        if src_ratio > rect_ratio:
            nw = rw
            nh = round(src_rgba.height * rw / src_rgba.width)
        else:
            nh = rh
            nw = round(src_rgba.width * rh / src_rgba.height)
        scaled = src_rgba.resize((nw, nh), Image.LANCZOS).convert("RGB")
        result = Image.new("RGB", (rw, rh), WHITE)
        result.paste(scaled, ((rw - nw) // 2, (rh - nh) // 2))
    else:
        # Cover — scale to fill, crop excess
        if src_ratio > rect_ratio:
            nh = rh
            nw = round(src_rgba.width * rh / src_rgba.height)
        else:
            nw = rw
            nh = round(src_rgba.height * rw / src_rgba.width)
        scaled  = src_rgba.resize((nw, nh), Image.LANCZOS)
        cx      = (nw - rw) // 2
        cy      = (nh - rh) // 2
        result  = scaled.crop((cx, cy, cx + rw, cy + rh)).convert("RGB")

    # Apply rounded-rectangle mask and paste onto canvas
    mask = Image.new("L", (rw, rh), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, rw - 1, rh - 1), radius=rounded_radius, fill=255)
    canvas.paste(result, (x1, y1), mask)


def _draw_placeholder(canvas: Image.Image,
                       x1: int, y1: int, x2: int, y2: int,
                       personnel,
                       rounded_radius: int = 12):
    """Solid-navy rectangle with an initial letter when no photo exists."""
    rw, rh = x2 - x1, y2 - y1
    ph   = Image.new("RGB", (rw, rh), NAVY)
    dphr = ImageDraw.Draw(ph)
    letter = (personnel.last_name[0] if personnel.last_name else "?").upper()
    f_init = _font(rh // 2, bold=True)
    bb     = dphr.textbbox((0, 0), letter, font=f_init)
    dphr.text(((rw - (bb[2] - bb[0])) // 2,
               (rh - (bb[3] - bb[1])) // 2 - 4),
              letter, font=f_init, fill=WHITE)
    mask = Image.new("L", (rw, rh), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, rw - 1, rh - 1), radius=rounded_radius, fill=255)
    canvas.paste(ph, (x1, y1), mask)


# ---------------------------------------------------------------------------
# Front card
# ---------------------------------------------------------------------------

def _build_front(personnel) -> Image.Image:
    """
    Overlay personnel data onto "CARD-FRONT.png" (PAF 950CEWW dark-tech template).
    Content placed:
      - Photo in white placeholder rectangle  (405 x 405 px)
      - Line 1 (info band) : Rank + Full Name + AFSN + PAF  (white, bold)
      - Line 2 (info band) : ENLISTED or OFFICER             (white, bold)
      - Line 3 (info band) : Personnel ID value              (white, bold)
    """
    img  = _load_template("CARD-FRONT.png")
    draw = ImageDraw.Draw(img)

    # -- Photo (pasted into the white placeholder box) -------------------------
    if personnel.personnel_image:
        try:
            _paste_image_in_rect(
                img, PHOTO_X1, PHOTO_Y1, PHOTO_X2, PHOTO_Y2,
                os.path.join(settings.MEDIA_ROOT, str(personnel.personnel_image)),
                rounded_radius=4)
        except Exception as exc:
            logger.warning("Front: photo load failed  %s", exc)
            _draw_placeholder(img, PHOTO_X1, PHOTO_Y1, PHOTO_X2, PHOTO_Y2, personnel)
    else:
        _draw_placeholder(img, PHOTO_X1, PHOTO_Y1, PHOTO_X2, PHOTO_Y2, personnel)

    # -- Text in dark navy info band (y 668..806) — white text ----------------
    #   Line 1 NAME_LINE_Y : "{Rank} {First} {MI} {Last} {AFSN} PAF"  (bold)
    #   Line 2 CATEGORY_Y  : "ENLISTED" or "OFFICER"                   (bold)
    #   Line 3 ID_FRONT_Y  : Personnel ID value                         (bold)

    rank_str = (personnel.rank or "").upper()
    first    = (personnel.first_name or "").upper()
    last     = (personnel.last_name  or "").upper()
    mi       = (personnel.middle_initial.strip().upper()
                if personnel.middle_initial and personnel.middle_initial.strip()
                else "")
    afsn     = (personnel.AFSN or "").strip()

    # Build name line:  "AW Rose Marie M Hernandez 994562 PAF"
    parts = [rank_str, first]
    if mi:
        parts.append(mi)
    parts.append(last)
    if afsn:
        parts.append(afsn)
    parts.append("PAF")
    name_line = " ".join(p for p in parts if p)

    # Determine category label
    officer_codes = {
        '2LT', '1LT', 'CPT', 'MAJ', 'LTCOL', 'COL',
        'BGEN', 'MGEN', 'LTGEN', 'GEN',
    }
    category = "OFFICER" if rank_str in officer_codes else "ENLISTED"

    # Auto-shrink name_line font so it always fits within card width (margin 20px each side)
    max_w  = CARD_W - 40
    f_size = 24
    while f_size > 12:
        f_candidate = _font(f_size, bold=True)
        bb = draw.textbbox((0, 0), name_line, font=f_candidate)
        if (bb[2] - bb[0]) <= max_w:
            break
        f_size -= 1
    f_name_line = _font(f_size, bold=True)
    f_category  = _font(22, bold=True)
    f_id        = _font(20, bold=True)

    _centered_text(draw, NAME_LINE_Y, name_line,           f_name_line, color=WHITE)
    _centered_text(draw, CATEGORY_Y,  category,            f_category,  color=WHITE)
    _centered_text(draw, ID_FRONT_Y,  personnel.Personnel_ID, f_id,    color=WHITE)

    return img


# ---------------------------------------------------------------------------
# Back card
# ---------------------------------------------------------------------------

def _build_back(personnel, skip_qr: bool = False) -> Image.Image:
    """
    Overlay personnel data onto "back.png" (PAF 950CEWW light-background template).
    Content placed:
      - Personnel photo in white rounded photo placeholder  (312 x 343 px)
      - Personnel ID value in gray footer band

    skip_qr is kept for API compatibility but is no longer used.
    """
    img  = _load_template("back.png")
    draw = ImageDraw.Draw(img)

    # -- Photo (pasted into the white photo placeholder) ----------------------
    if personnel.personnel_image:
        try:
            _paste_image_in_rect(
                img, BACK_PHOTO_X1, BACK_PHOTO_Y1, BACK_PHOTO_X2, BACK_PHOTO_Y2,
                os.path.join(settings.MEDIA_ROOT, str(personnel.personnel_image)),
                rounded_radius=8)
        except Exception as exc:
            logger.warning("Back: photo load failed  %s", exc)
            _draw_placeholder(img, BACK_PHOTO_X1, BACK_PHOTO_Y1,
                              BACK_PHOTO_X2, BACK_PHOTO_Y2, personnel)
    else:
        _draw_placeholder(img, BACK_PHOTO_X1, BACK_PHOTO_Y1,
                          BACK_PHOTO_X2, BACK_PHOTO_Y2, personnel)

    # -- Personnel ID in footer band (y 880..975) ----------------------------
    f_id = _font(22, bold=True)
    _centered_text(draw, BACK_FOOTER_ID_Y, personnel.Personnel_ID, f_id, color=NAVY)

    return img


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_personnel_id_card(personnel) -> dict:
    """
    Generate front + back ID card PNGs for *personnel*.
    Saves to ``MEDIA_ROOT/personnel_id_cards/``.

    Returns a dict::

        {
          "combined": "personnel_id_cards/<pid>.png",
          "front":    "personnel_id_cards/<pid>_front.png",
          "back":     "personnel_id_cards/<pid>_back.png",
        }
    """
    out_dir = os.path.join(settings.MEDIA_ROOT, "personnel_id_cards")
    os.makedirs(out_dir, exist_ok=True)

    pid   = personnel.Personnel_ID        # CharField PK
    front = _build_front(personnel)
    back  = _build_back(personnel)

    front_path    = os.path.join(out_dir, f"{pid}_front.png")
    back_path     = os.path.join(out_dir, f"{pid}_back.png")
    combined_path = os.path.join(out_dir, f"{pid}.png")

    front.save(front_path,    "PNG", dpi=(300, 300))
    back.save(back_path,      "PNG", dpi=(300, 300))

    GAP  = 20
    BG   = (220, 224, 235)
    comb = Image.new("RGB", (CARD_W * 2 + GAP, CARD_H), BG)
    comb.paste(front, (0, 0))
    comb.paste(back,  (CARD_W + GAP, 0))
    comb.save(combined_path, "PNG", dpi=(300, 300))

    logger.info("ID card generated -> %s", combined_path)
    return {
        "combined": f"personnel_id_cards/{pid}.png",
        "front":    f"personnel_id_cards/{pid}_front.png",
        "back":     f"personnel_id_cards/{pid}_back.png",
    }