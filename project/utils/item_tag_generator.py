"""
Item Tag Generator  —  utils/item_tag_generator.py
===================================================
Generates a printable PNG tag for each inventory item.

Dimension basis:  qr_print_layout.QR_SIZE_MM = 20mm  (2 cm × 2 cm)

Canvas: 900 × 450 px  — exact 2:1 ratio matching the 90 × 45 mm print card
        → uniform scale of 10 px per mm
        → QR_SIZE = 200 px = 20 mm = 2 cm  ✓
        → number height budget = 200 px = 20 mm = 2 cm  ✓

Design:
  ┌──────────────────────────────────────────────┐
  │                                              │
  │   0001                   [■■■■■■■■■]         │
  │                          [■ QR CODE ■]       │
  │                          [■■■■■■■■■]         │
  ├──────────────────────────────────────────────┤
  │  .45 PISTOL              458675              │
  └──────────────────────────────────────────────┘

Output: core/media/item_id_tags/<item_id>.png
"""

import os
import logging
from PIL import Image, ImageDraw

from django.conf import settings

logger = logging.getLogger(__name__)

# ─── Canvas dimensions ──────────────────────────────────────────────────────
# 900 × 310 px = 90 × 31 mm  (10 px/mm uniform scale)
# Height is exactly what the content needs — no wasted space.
TAG_W = 900
TAG_H = 310

# ─── Colours ────────────────────────────────────────────────────────────────
BG         = (255, 255, 255)
BORDER     = (220, 223, 228)
NUMBER_COL = (13,  18,  38)    # near-black navy
NO_NUM_COL = (209, 213, 219)   # #d1d5db  placeholder
TYPE_COL   = (13,  18,  38)
SERIAL_COL = (13,  18,  38)
DIVIDER    = (220, 223, 228)
QR_BG      = (240, 241, 243)   # placeholder when no QR image

# ─── Layout constants (10 px = 1 mm) ────────────────────────────────────────
PAD_X      = 26     # left/right inner padding
PAD_TOP    = 20     # 2 mm — top inner padding
QR_SIZE    = 200    # 20 mm = 2 cm  (matches qr_print_layout.QR_SIZE_MM = 20)
                    # num height budget is also 200 px = 2 cm
DIV_GAP    = 10     # 1 mm — gap between QR bottom and divider
# row band: div_y=230, row2_top=236, row2_bot=300 (TAG_H-PAD_BOT), avail=64px, font≤50px ✓
PAD_BOT    = 10     # 1 mm — padding below bottom row
GAP_NQ     = 22     # horizontal gap between number area and QR column
BORDER_W   = 4      # card outline stroke
CORNER_R   = 20     # corner radius (proportional to thinner card)

# ─── Font cache ────────────────────────────────────────────────────────────
_FONT_CACHE: dict = {}

_BLACK_PATHS = [                          # heaviest weight first
    'C:/Windows/Fonts/ariblk.ttf',        # Arial Black
    'C:/Windows/Fonts/arialbd.ttf',       # Arial Bold
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
    '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
    '/usr/share/fonts/truetype/freefont/FreeSansBold.ttf',
]
_MONO_PATHS = [
    'C:/Windows/Fonts/courbd.ttf',        # Courier New Bold
    'C:/Windows/Fonts/cour.ttf',
    '/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf',
    '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf',
    '/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf',
]


def _font(size: int, bold: bool = False, mono: bool = False):
    key = (size, bold, mono)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    from PIL import ImageFont
    paths = _MONO_PATHS if mono else _BLACK_PATHS
    for p in paths:
        if os.path.exists(p):
            try:
                f = ImageFont.truetype(p, size)
                _FONT_CACHE[key] = f
                return f
            except Exception:
                continue
    f = ImageFont.load_default()
    _FONT_CACHE[key] = f
    return f


def _rounded_rect(draw, bbox, radius, fill, outline=None, outline_width=2):
    draw.rounded_rectangle(list(bbox), radius=radius,
                            fill=fill, outline=outline, width=outline_width)


# ─── Model label map ───────────────────────────────────────────────────────
# Maps the exact model choice strings to a short, tag-friendly label.
# Shown bottom-left of the tag instead of the generic 'PISTOL' / 'RIFLE'.
_MODEL_LABEL = {
    # Pistols
    'Glock 17 9mm':           'GLOCK 17',
    'M1911 Cal.45':           'M1911',
    'Armscor Hi Cap Cal.45':  'ARMSCOR',
    'RIA Hi Cap Cal.45':      'RIA',
    'M1911 Customized Cal.45':'M1911-C',
    # Rifles
    'M4 Carbine DSAR-15 5.56mm':    'M4',
    'M4 14.5" DGIS EMTAN 5.56mm':   'M4 EMTAN',
    'M16A1 Rifle 5.56mm':           'M16A1',
    'M14 Rifle 7.62mm':             'M14',
    'M653 Carbine 5.56mm':          'M653',
}


def _short_model_label(item) -> str:
    """Return a compact uppercase model label for the tag bottom row."""
    model = getattr(item, 'model', None)
    if model and model in _MODEL_LABEL:
        return _MODEL_LABEL[model]
    # Fallback: strip calibre/mm suffixes and uppercase, e.g. 'M16A2 Rifle 5.56mm' → 'M16A2'
    if model:
        import re as _re
        clean = _re.sub(r'\s+(cal\.?\d+|\d+\.\d+mm|\d+x\d+mm|\d+mm)', '', model, flags=_re.I).strip()
        return clean.upper()
    # Last resort: generic type
    return item.get_item_type_display().upper()



def generate_item_tag(item) -> dict:
    """Generate a PNG tag for the given Item and save to disk."""
    out_dir = os.path.join(settings.MEDIA_ROOT, 'item_id_tags')
    os.makedirs(out_dir, exist_ok=True)
    img = _build_tag(item)
    tag_path = os.path.join(out_dir, f"{item.id}.png")
    img.save(tag_path, 'PNG', dpi=(300, 300))
    logger.info("Item tag saved: %s", tag_path)
    # BUG-FIX: Populate the ImageField in the DB so item.item_tag is not NULL.
    # Previously item_tag was only written to disk — the DB field was never set,
    # causing a permanent DB ↔ disk desync.
    # Use queryset.update() to bypass the full Pistol/Rifle save() chain (no
    # timestamp/QR side-effects) and do a single targeted UPDATE.
    try:
        relative_path = f"item_id_tags/{item.id}.png"
        type(item).objects.filter(pk=item.id).update(item_tag=relative_path)
        # Keep the in-memory instance in sync as well
        item.item_tag.name = relative_path
        logger.info("item_tag field updated for %s", item.id)
    except Exception as exc:
        logger.warning("Could not update item_tag field for %s: %s", item.id, exc)
    return {'tag': tag_path}


# ─── Internal rendering ────────────────────────────────────────────────────

def _load_qr_image(item):
    """Return PIL Image of the QR code for this item, or None.
    Uses item.qr_code_image (set by Pistol/Rifle.save()) directly.
    """
    try:
        qr_field = getattr(item, 'qr_code_image', None)
        if qr_field and qr_field.name:
            try:
                qr_path = qr_field.path
            except Exception:
                qr_path = os.path.join(settings.MEDIA_ROOT, str(qr_field.name))
            if os.path.exists(qr_path):
                return Image.open(qr_path).convert('RGB')
    except Exception as exc:
        logger.warning("Could not load QR for item %s: %s", item.id, exc)
    return None


def _best_font_for(draw, text: str, max_w: int, max_h: int,
                   bold: bool = True, mono: bool = False) -> object:
    """Return the largest font that fits text within (max_w × max_h)."""
    for fsize in range(280, 18, -4):
        f = _font(fsize, bold=bold, mono=mono)
        if f is None:
            continue
        bb = draw.textbbox((0, 0), text, font=f)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        if tw <= max_w and th <= max_h:
            return f
    return _font(20, bold=bold, mono=mono)


def _build_tag(item) -> Image.Image:
    img  = Image.new('RGB', (TAG_W, TAG_H), BG)
    draw = ImageDraw.Draw(img)

    # ── Card outline ───────────────────────────────────────────────────────
    _rounded_rect(draw, [0, 0, TAG_W - 1, TAG_H - 1],
                  CORNER_R, BG, BORDER, BORDER_W)

    # ── Geometry ───────────────────────────────────────────────────────────
    # QR block: right-aligned, top-aligned with PAD_TOP
    qr_x  = TAG_W - PAD_X - QR_SIZE          # left edge of QR block
    qr_y  = PAD_TOP                           # top edge of QR block
    div_y = qr_y + QR_SIZE + DIV_GAP         # horizontal divider y

    # Number area: left column, from PAD_X to (qr_x - GAP_NQ)
    num_right = qr_x - GAP_NQ
    num_avail_w = num_right - PAD_X
    num_avail_h = QR_SIZE                     # same height budget as QR

    # Bottom row band
    row2_top = div_y + 6
    row2_bot = TAG_H - PAD_BOT
    row2_cy  = (row2_top + row2_bot) // 2

    # ── QR code ────────────────────────────────────────────────────────────
    qr_img = _load_qr_image(item)
    if qr_img:
        qr_img = qr_img.resize((QR_SIZE, QR_SIZE), Image.LANCZOS)
        img.paste(qr_img, (qr_x, qr_y))
    else:
        _rounded_rect(draw, [qr_x, qr_y, qr_x + QR_SIZE, qr_y + QR_SIZE],
                      8, QR_BG, BORDER, 2)
        ph = _font(32, mono=True)
        draw.text((qr_x + QR_SIZE // 2, qr_y + QR_SIZE // 2),
                  'NO QR', font=ph, fill=(156, 163, 175), anchor='mm')

    # ── Item number ────────────────────────────────────────────────────────
    try:
        num_text = f"{int(item.item_number):04d}" if item.item_number else '----'
    except (ValueError, TypeError):
        num_text = str(item.item_number) if item.item_number else '----'
    num_col  = NUMBER_COL if item.item_number else NO_NUM_COL

    num_font = _best_font_for(draw, num_text, num_avail_w, num_avail_h, bold=True)
    num_cx   = PAD_X + num_avail_w // 2
    num_cy   = qr_y + QR_SIZE // 2           # vertically centred with QR

    draw.text((num_cx, num_cy), num_text,
              font=num_font, fill=num_col, anchor='mm')

    # ── Horizontal divider ─────────────────────────────────────────────────
    draw.line([(PAD_X, div_y), (TAG_W - PAD_X, div_y)], fill=DIVIDER, width=3)

    # ── Bottom row: type (left)  ·  vertical tick  ·  serial (right) ──────
    # Both fields use the SAME monospace font, height capped at 5 mm = 50 px.
    ROW_FONT_MAX_H = 50   # 5 mm × 10 px/mm
    sep_x = TAG_W // 2

    type_text  = _short_model_label(item)
    serial_text = item.serial

    # Find the largest mono font that fits both texts within their half-widths
    # and within the 50 px height cap.
    half_w_type   = sep_x - PAD_X - 12
    half_w_serial = TAG_W - PAD_X - sep_x - 12
    row_font = _best_font_for(draw, type_text,   half_w_type,   ROW_FONT_MAX_H, bold=True, mono=True)
    # Shrink further if needed to fit the serial in its half too
    for fsize in range(280, 18, -4):
        f = _font(fsize, bold=True, mono=True)
        if f is None:
            continue
        bb_t = draw.textbbox((0, 0), type_text,   font=f)
        bb_s = draw.textbbox((0, 0), serial_text, font=f)
        th = max(bb_t[3] - bb_t[1], bb_s[3] - bb_s[1])
        tw_t = bb_t[2] - bb_t[0]
        tw_s = bb_s[2] - bb_s[0]
        if th <= ROW_FONT_MAX_H and tw_t <= half_w_type and tw_s <= half_w_serial:
            row_font = f
            break

    type_cx   = PAD_X + half_w_type // 2
    serial_cx = sep_x + half_w_serial // 2

    draw.text((type_cx,   row2_cy), type_text,   font=row_font, fill=TYPE_COL,   anchor='mm')

    # Thin vertical separator
    draw.line([(sep_x, row2_top + 6), (sep_x, row2_bot - 6)],
              fill=DIVIDER, width=2)

    draw.text((serial_cx, row2_cy), serial_text, font=row_font, fill=SERIAL_COL, anchor='mm')

    return img


def _build_stacked_tag(item, stack: int) -> Image.Image:
    """
    Build a single PNG with `stack` number+QR rows above one shared bottom label.
    Each row is separated by a thin line; only the last row has the bottom label.
    """
    if stack <= 1:
        return _build_tag(item)

    # ── Derive geometry from the single-tag constants ─────────────────────
    SECTION_H = PAD_TOP + QR_SIZE + DIV_GAP   # = 230 px  (top section up to divider)
    BOTTOM_H  = TAG_H - SECTION_H              # = 80 px   (divider + label row)
    SEP_H     = 4                              # thin separator between copies

    total_h = stack * SECTION_H + (stack - 1) * SEP_H + BOTTOM_H

    # Build the base single tag so we can crop sections from it
    base = _build_tag(item)
    section_crop = base.crop((0, 0, TAG_W, SECTION_H))
    bottom_crop  = base.crop((0, SECTION_H, TAG_W, TAG_H))

    img  = Image.new('RGB', (TAG_W, total_h), BG)
    draw = ImageDraw.Draw(img)

    y = 0
    for i in range(stack):
        img.paste(section_crop, (0, y))
        y += SECTION_H
        if i < stack - 1:
            # Thin separator line between rows
            draw.line([(PAD_X, y + SEP_H // 2), (TAG_W - PAD_X, y + SEP_H // 2)],
                      fill=DIVIDER, width=2)
            y += SEP_H

    img.paste(bottom_crop, (0, y))

    # Redraw card outline over the full stacked image
    _rounded_rect(draw, [0, 0, TAG_W - 1, total_h - 1],
                  CORNER_R, None, BORDER, BORDER_W)

    return img


def get_stacked_tag_b64(item, stack: int) -> str:
    """Return a base64 data-URL PNG for use as an <img src=...>."""
    import io, base64
    img = _build_stacked_tag(item, stack)
    buf = io.BytesIO()
    img.save(buf, 'PNG', dpi=(300, 300))
    b64 = base64.b64encode(buf.getvalue()).decode('ascii')
    return f'data:image/png;base64,{b64}'

