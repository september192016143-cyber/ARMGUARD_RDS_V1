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
# Layout constants  (pixels, scanned from ARMORY CARD template images)
#
# FRONT  "ARMORY CARD-front.png"  (638 x 1013 px)
#  PAF 950CEWW navy header  : y   0 .. 129
#  Orange top banner        : y 130 .. 183  ← OFFICER / ENLISTED overlay
#  Dark body                : y 184 .. 231
#  White photo box          : x 114..520 ,  y 232..638  (406 x 406 px)
#  Dark background gap      : y 639 .. 666
#  Dark pill box 1 (name)   : y 667 .. 721  ← name / rank / AFSN text
#  Gap                      : y 722 .. 729
#  Dark pill box 2 (ID)     : y 730 .. 806  ← ID No + Issuance Date
#  Orange chevron           : y 808 .. 932
#  Navy footer "ARMORY CARD": y 933 .. 1012
#
# BACK  "ARMORY CARD-back.png"  (638 x 1013 px)
#  ARMGUARD navy header     : y   0 .. 146
#  Gray QR placeholder      : x 76..562 ,  y 147..710  (486 x 563 px)
#  Pre-printed blue text box: y 710 .. 829  (non-transferable — baked in)
#  White gap                : y 830 .. 932
#  Navy footer              : y 933 .. 1012
#  NOTE: contact nr and footer text are baked into the template;
#        only the QR code is overlaid dynamically.
# ---------------------------------------------------------------------------

# Front card photo placeholder  (406 x 406 px)
PHOTO_X1, PHOTO_Y1 = 114, 232
PHOTO_X2, PHOTO_Y2 = 520, 638
PHOTO_W = PHOTO_X2 - PHOTO_X1   # 406 px
PHOTO_H = PHOTO_Y2 - PHOTO_Y1   # 406 px

# Orange top banner label (y 130..183, centre ≈ 156)
CATEGORY_BANNER_Y = 140   # "OFFICER" or "ENLISTED" — white bold, large

# Front pill-box text rows  (white text on dark navy pills)
NAME_LINE_Y = 680   # pill box 1 — rank + full name + AFSN + PAF
ID_LINE_Y   = 743   # pill box 2 upper — "ID No: {Personnel_ID}"
DATE_LINE_Y = 771   # pill box 2 lower — "Issuance Date: {DD Mon YYYY}"

# Back card gray placeholder bounds  (486 x 563 px)
_BACK_PLACEHOLDER_X1, _BACK_PLACEHOLDER_Y1 = 76, 147
_BACK_PLACEHOLDER_X2, _BACK_PLACEHOLDER_Y2 = 562, 710

# QR code render area — exactly 486 x 486, centred vertically in the placeholder
BACK_QR_X1 = _BACK_PLACEHOLDER_X1                                        # 76
BACK_QR_X2 = _BACK_PLACEHOLDER_X2                                        # 562
BACK_QR_W  = BACK_QR_X2 - BACK_QR_X1                                    # 486 px
BACK_QR_H  = BACK_QR_W                                                   # 486 px (square)
_ph         = (_BACK_PLACEHOLDER_Y2 - _BACK_PLACEHOLDER_Y1 - BACK_QR_H) // 2  # 38 px
BACK_QR_Y1 = _BACK_PLACEHOLDER_Y1 + _ph                                  # 185
BACK_QR_Y2 = BACK_QR_Y1 + BACK_QR_H                                     # 671

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
    Overlay personnel data onto "ARMORY CARD-front.png".
    Content placed:
      - Orange top banner  : "OFFICER" or "ENLISTED"  (white bold, large)
      - Photo              : in white placeholder rectangle (406 x 406 px)
      - Pill box 1         : Rank + Full Name + AFSN + PAF [+ (duty_type)]  (white bold)
      - Pill box 2 line 1  : "ID No: {Personnel_ID}"                        (white bold)
      - Pill box 2 line 2  : "Issuance Date: {DD Mon YYYY}"                 (white bold)
    """
    from datetime import date

    img  = _load_template("ARMORY CARD-front.png")
    draw = ImageDraw.Draw(img)

    rank_str = (personnel.rank or "").upper()
    first    = (personnel.first_name or "").upper()
    last     = (personnel.last_name  or "").upper()
    mi       = (personnel.middle_initial.strip().upper()
                if personnel.middle_initial and personnel.middle_initial.strip()
                else "")
    afsn     = (personnel.AFSN or "").strip()
    duty     = (getattr(personnel, "duty_type", None) or "").strip()

    # Determine category label
    officer_codes = {
        '2LT', '1LT', 'CPT', 'MAJ', 'LTCOL', 'COL',
        'BGEN', 'MGEN', 'LTGEN', 'GEN',
    }
    category = "OFFICER" if rank_str in officer_codes else "ENLISTED"

    # -- Orange banner label (y 130..183) — white bold, large, centred --------
    f_banner = _font(36, bold=True)
    _centered_text(draw, CATEGORY_BANNER_Y, category, f_banner, color=WHITE)

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

    # -- Pill box 1 : name line -----------------------------------------------
    #   "{Rank} {First} {MI} {Last} {AFSN} PAF" [+ "({duty_type})"]
    parts = [rank_str, first]
    if mi:
        parts.append(mi)
    parts.append(last)
    if afsn:
        parts.append(afsn)
    parts.append("PAF")
    if duty:
        parts.append(f"({duty})")
    name_line = " ".join(p for p in parts if p)

    # Auto-shrink so it always fits within pill box width (20 px margin each side)
    max_w  = CARD_W - 40
    f_size = 24
    while f_size > 11:
        f_candidate = _font(f_size, bold=True)
        bb = draw.textbbox((0, 0), name_line, font=f_candidate)
        if (bb[2] - bb[0]) <= max_w:
            break
        f_size -= 1
    f_name_line = _font(f_size, bold=True)

    _centered_text(draw, NAME_LINE_Y, name_line, f_name_line, color=WHITE)

    # -- Pill box 2 : ID + issuance date --------------------------------------
    f_pill2 = _font(22, bold=True)
    id_text   = f"ID No: {personnel.Personnel_ID}"
    date_text = "Issuance Date: " + date.today().strftime("%d %b %Y")

    _centered_text(draw, ID_LINE_Y,   id_text,   f_pill2, color=WHITE)
    _centered_text(draw, DATE_LINE_Y, date_text, f_pill2, color=WHITE)

    return img


# ---------------------------------------------------------------------------
# Back card
# ---------------------------------------------------------------------------

def _build_back(personnel, skip_qr: bool = False) -> Image.Image:
    """
    Overlay personnel data onto "ARMORY CARD-back.png".
    Content placed:
      - QR code in gray placeholder rectangle  (486 x 563 px)

    The contact number, unit phone, and footer text are pre-printed in the
    template itself and are NOT overlaid dynamically.

    skip_qr=True  — omit QR (used by live preview before a record is saved).
    """
    img  = _load_template("ARMORY CARD-back.png")
    draw = ImageDraw.Draw(img)  # noqa: F841 — kept for consistency

    # -- QR code — fitted into the back-specific placeholder rect -------------
    qr_placed = False

    if skip_qr:
        qr_placed = True   # skip both load and fallback generation

    def _paste_qr(qr_img: Image.Image):
        """
        Auto-crop any solid border from *qr_img*, scale to fill the
        placeholder rect (centred), and paste onto *img*.
        """
        qr_rgb = qr_img.convert("RGB")
        # getbbox() returns bounding box of non-black pixels (removes outer black frame)
        bbox = qr_rgb.getbbox()
        if bbox:
            qr_rgb = qr_rgb.crop(bbox)
        # Scale QR to exactly 486 x 486 and paste at the centred render area
        qr_scaled = qr_rgb.resize((BACK_QR_W, BACK_QR_H), Image.LANCZOS)
        img.paste(qr_scaled, (BACK_QR_X1, BACK_QR_Y1))
        # Draw a thin white border to separate QR from the gray placeholder
        ImageDraw.Draw(img).rectangle(
            (BACK_QR_X1 - 2, BACK_QR_Y1 - 2, BACK_QR_X1 + BACK_QR_W + 1, BACK_QR_Y1 + BACK_QR_H + 1),
            outline=WHITE, width=2)

    if getattr(personnel, "qr_code_image", None):
        try:
            qr_path = os.path.join(settings.MEDIA_ROOT, str(personnel.qr_code_image))
            with Image.open(qr_path) as qr_src:
                _paste_qr(qr_src.copy())
            qr_placed = True
        except Exception as exc:
            logger.warning("Back: QR image load failed  %s", exc)

    if not qr_placed:
        try:
            import qrcode as qrlib
            qr_data = (getattr(personnel, "qr_code", None)
                       or personnel.Personnel_ID)
            qr_obj  = qrlib.QRCode(
                box_size=10, border=1,
                error_correction=qrlib.constants.ERROR_CORRECT_M)
            qr_obj.add_data(qr_data)
            qr_obj.make(fit=True)
            qr_pil = qr_obj.make_image(fill_color="black",
                                        back_color="white").convert("RGB")
            _paste_qr(qr_pil)
        except Exception as exc:
            logger.warning("Back: QR generation failed  %s", exc)

    # No dynamic text overlay — contact number and footer are baked into template
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