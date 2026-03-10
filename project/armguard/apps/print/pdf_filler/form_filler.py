"""
PDF Form Filler for Temp_Rec.pdf
Fills transaction forms with actual data during normal transactions
Uses PyMuPDF to overlay text on the PDF template
"""
import logging

logger = logging.getLogger('armguard.print')

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    logger.warning("PyMuPDF (fitz) is not installed — PDF form filling will be limited. "
                   "Install it with: pip install pymupdf")
    
from io import BytesIO
import os
from django.conf import settings
from .form_config import (
    VERTICAL_OFFSET, HORIZONTAL_OFFSET, UPPER_FORM, 
    LOWER_FORM_Y_OFFSET, FONT_NAME, FONT_COLOR, FIELD_ADJUSTMENTS, ROTATION
)


class TransactionFormFiller:
    """Fills Temp_Rec.pdf form with transaction data by overlaying text"""
    
    def __init__(self):
        self.template_path = os.path.join(
            settings.CARD_TEMPLATES_DIR,
            'TR_PDF_TEMPLATE',
            'Temp_Rec.pdf'
        )
    
    def fill_transaction_form(self, transaction):
        """
        Fill the Temp_Rec.pdf form with transaction data by overlaying text.
        Only valid for TR (Temporary Receipt) issuance type.

        Args:
            transaction: Transaction model instance

        Returns:
            BytesIO: Filled PDF as bytes

        Raises:
            ValueError: if issuance_type is not TR
        """
        issuance = (transaction.issuance_type or '')
        if not issuance.startswith('TR'):
            raise ValueError(
                f"TransactionFormFiller only handles TR (Temporary Receipt) transactions. "
                f"Got issuance_type='{issuance}' for transaction {transaction.transaction_id}."
            )

        if not PYMUPDF_AVAILABLE:
            # Fallback: return the blank template so the view can still produce *some* PDF.
            logger.warning(
                "PyMuPDF not available — returning blank PDF template for transaction %s.",
                getattr(transaction, 'transaction_id', '?'),
            )
            try:
                with open(self.template_path, 'rb') as f:
                    return BytesIO(f.read())
            except FileNotFoundError:
                logger.error(
                    "TR PDF template not found at '%s' — returning empty BytesIO.",
                    self.template_path,
                )
                return BytesIO()

        pistol = transaction.pistol
        rifle  = transaction.rifle
        is_withdrawal = (transaction.transaction_type == 'Withdrawal')

        if pistol and rifle and is_withdrawal:
            # Two pages: page 1 = pistol TR, page 2 = rifle TR
            pistol_doc = self._build_filled_doc(transaction, weapon='pistol')
            rifle_doc  = self._build_filled_doc(transaction, weapon='rifle')
            combined = fitz.open()
            combined.insert_pdf(pistol_doc)
            combined.insert_pdf(rifle_doc)
            pistol_doc.close()
            rifle_doc.close()
            output = BytesIO()
            output.write(combined.tobytes())
            output.seek(0)
            combined.close()
            return output
        else:
            doc = self._build_filled_doc(transaction, weapon=None)
            output = BytesIO()
            output.write(doc.tobytes())
            output.seek(0)
            doc.close()
            return output

    def _build_filled_doc(self, transaction, weapon=None):
        """
        Build and return a filled fitz.Document for one weapon.
        Caller is responsible for closing the returned document.
        weapon: 'pistol', 'rifle', or None (auto-detect primary weapon).
        """
        template_doc = fitz.open(self.template_path)
        if VERTICAL_OFFSET != 0:
            doc = self._create_shifted_pdf(template_doc)
            template_doc.close()
        else:
            doc = template_doc
        page = doc[0]
        data = self._prepare_data(transaction, weapon=weapon)
        self._add_text_overlays(page, data)
        return doc
    
    def _create_shifted_pdf(self, source_doc):
        """
        Create a new PDF with content shifted down by VERTICAL_OFFSET
        This moves the logo and all background elements down to prevent cutting
        Uses Legal paper size (8.5" x 14" = 612 x 1008 points)
        Can optionally rotate 180 degrees to swap top/bottom margins
        No scaling - uses exact coordinates
        """
        # Create new empty document
        new_doc = fitz.open()
        
        # Get source page dimensions
        source_page = source_doc[0]
        source_rect = source_page.rect
        
        # Use Legal paper size (14 inches = 1008 points)
        # Standard US Legal: 8.5" x 14" = 612 x 1008 points
        legal_width = 612
        legal_height = 1008
        new_page = new_doc.new_page(width=legal_width, height=legal_height)
        
        # Set page size explicitly in multiple ways for printer compatibility
        new_page.set_mediabox(fitz.Rect(0, 0, legal_width, legal_height))
        
        # Draw white background
        new_page.draw_rect(fitz.Rect(0, 0, legal_width, legal_height),
                          color=None, fill=(1, 1, 1))
        
        # Copy source page content to new page, shifted down
        # The content will be positioned starting at VERTICAL_OFFSET from top
        target_rect = fitz.Rect(0, VERTICAL_OFFSET, source_rect.width, VERTICAL_OFFSET + source_rect.height)
        new_page.show_pdf_page(target_rect, source_doc, 0)
        
        # Apply rotation if configured (180 degrees swaps top/bottom margins)
        if ROTATION == 180:
            new_page.set_rotation(180)
        
        # Set document metadata to indicate Legal paper
        new_doc.set_metadata({
            'title': 'Transaction Receipt - Legal Size',
            'producer': 'ArmGuard System'
        })
        
        return new_doc

    def _prepare_data(self, transaction, weapon=None):
        """
        Prepare transaction data for display.
        weapon: 'pistol' | 'rifle' | None (auto — pistol takes priority).
        When weapon is specified, only that weapon's item/mags/rounds are used.
        """
        from django.utils import timezone as tz

        personnel = transaction.personnel

        # ── Personnel name ─────────────────────────────────────────────────────
        mi = (personnel.middle_initial or '').strip()
        if mi:
            personnel_name = f"{personnel.first_name} {mi} {personnel.last_name}"
        else:
            personnel_name = f"{personnel.first_name} {personnel.last_name}"

        # ── Issuer ─────────────────────────────────────────────────────────────
        armorer = getattr(transaction, 'armorer_personnel', None)
        if armorer is not None:
            a_mi = (armorer.middle_initial or '').strip()
            a_mi_part = f" {a_mi}" if a_mi else ''
            a_afsn = (armorer.AFSN or '').strip()
            issued_by = f"{armorer.rank} {armorer.first_name}{a_mi_part} {armorer.last_name} {a_afsn} PAF"
        else:
            issued_by = (transaction.transaction_personnel or 'Armorer').strip()

        pistol = transaction.pistol
        rifle  = transaction.rifle

        # ── Weapon-specific item / mags / rounds ───────────────────────────────
        if weapon == 'pistol' and pistol:
            item_type   = pistol.model or 'Pistol'
            item_serial = pistol.serial_number or ''
            total_mags  = transaction.pistol_magazine_quantity or 0
            total_rounds = transaction.pistol_ammunition_quantity or 0
        elif weapon == 'rifle' and rifle:
            item_type   = rifle.model or 'Rifle'
            item_serial = rifle.serial_number or ''
            total_mags  = transaction.rifle_magazine_quantity or 0
            total_rounds = transaction.rifle_ammunition_quantity or 0
        else:
            # Auto: pistol takes priority; fall back to rifle; sum all mags/rounds
            if pistol:
                item_type   = pistol.model or 'Pistol'
                item_serial = pistol.serial_number or ''
            elif rifle:
                item_type   = rifle.model or 'Rifle'
                item_serial = rifle.serial_number or ''
            else:
                item_type   = ''
                item_serial = ''
            total_mags   = (transaction.pistol_magazine_quantity or 0) + (transaction.rifle_magazine_quantity or 0)
            total_rounds = (transaction.pistol_ammunition_quantity or 0) + (transaction.rifle_ammunition_quantity or 0)

        # ── Purpose / duty type ────────────────────────────────────────────────
        duty_type = (transaction.purpose or 'Duty Security').strip()
        # ── Accessories ──────────────────────────────────────────────────────
        holster_qty    = getattr(transaction, 'pistol_holster_quantity', None) or 0
        mag_pouch_qty  = getattr(transaction, 'magazine_pouch_quantity', None) or 0
        sling_qty      = getattr(transaction, 'rifle_sling_quantity', None) or 0
        bandoleer_qty  = getattr(transaction, 'bandoleer_quantity', None) or 0

        pistol_acc = [(holster_qty, 'Pistol Holster'), (mag_pouch_qty, 'Magazine Pouch')]
        rifle_acc  = [(sling_qty, 'Rifle Sling'), (bandoleer_qty, 'Bandoleer')]
        all_acc    = pistol_acc + rifle_acc

        if weapon == 'pistol':
            acc_candidates = pistol_acc
        elif weapon == 'rifle':
            acc_candidates = rifle_acc
        else:
            acc_candidates = all_acc

        accessories_lines = [f"{name} x{qty}" for qty, name in acc_candidates if qty]
        # ── Timestamp (use local time) ─────────────────────────────────────────
        local_ts = tz.localtime(transaction.timestamp)

        # ── Full personnel signature line ──────────────────────────────────────
        afsn = (personnel.AFSN or '').strip()
        group = (personnel.group or '').strip()
        mi_part = f" {mi}" if mi else ''
        personnel_full = f"{personnel.rank} {personnel.first_name}{mi_part} {personnel.last_name} {afsn} PAF"

        return {
            'date': local_ts.strftime('%d/%m/%Y'),
            'time': local_ts.strftime('%H:%M:%S'),
            'transaction_id': str(transaction.transaction_id),
            'personnel_name': personnel_name,
            'personnel_rank': personnel.rank or '',
            'personnel_serial': afsn,
            'personnel_unit': group,
            'personnel_tel': (personnel.tel or ''),
            'personnel_full': personnel_full,
            'item_type': item_type,
            'item_serial': item_serial,
            'action': transaction.transaction_type,
            'mags': str(total_mags) if total_mags else '0',
            'rounds': str(total_rounds) if total_rounds else '0',
            'duty_type': duty_type,
            'notes': transaction.notes or '',
            'accessories_lines': accessories_lines,
            'issued_by': issued_by,
        }
    
    def _add_text_overlays(self, page, data):
        """
        Add text overlays to the PDF page
        Based on Temp_Rec.pdf analysis - form has 2 identical sections (top and bottom)
        Coordinates: Origin (0,0) at TOP-LEFT, Y increases downward
        Page size: 612 x 936 points
        """
        # Fill top form
        self._fill_upper_form(page, data)
        
        # Fill bottom form
        self._fill_lower_form(page, data)
    
    def _apply_offsets(self, x, y, field_name=None):
        """Apply global and field-specific offsets to coordinates"""
        # Apply global offsets
        x += HORIZONTAL_OFFSET
        y += VERTICAL_OFFSET
        
        # Apply field-specific adjustments if configured
        if field_name and field_name in FIELD_ADJUSTMENTS:
            x += FIELD_ADJUSTMENTS[field_name].get('x', 0)
            y += FIELD_ADJUSTMENTS[field_name].get('y', 0)
        
        return (x, y)
    
    def _fill_upper_form(self, page, data):
        """Fill the upper form section with configurable positions"""
        # Date field (top right)
        pos = self._apply_offsets(UPPER_FORM['date']['x'], UPPER_FORM['date']['y'], 'date')
        page.insert_text(pos, data['date'], fontsize=UPPER_FORM['date']['size'], 
                        fontname=FONT_NAME, color=FONT_COLOR)
        
        # Personnel information line
        pos = self._apply_offsets(UPPER_FORM['personnel_name']['x'], UPPER_FORM['personnel_name']['y'], 'personnel_name')
        page.insert_text(pos, data['personnel_name'], fontsize=UPPER_FORM['personnel_name']['size'], 
                        fontname=FONT_NAME, color=FONT_COLOR)
        
        pos = self._apply_offsets(UPPER_FORM['personnel_rank']['x'], UPPER_FORM['personnel_rank']['y'], 'personnel_rank')
        page.insert_text(pos, data['personnel_rank'], fontsize=UPPER_FORM['personnel_rank']['size'], 
                        fontname=FONT_NAME, color=FONT_COLOR)
        
        pos = self._apply_offsets(UPPER_FORM['personnel_serial']['x'], UPPER_FORM['personnel_serial']['y'], 'personnel_serial')
        page.insert_text(pos, data['personnel_serial'], fontsize=UPPER_FORM['personnel_serial']['size'], 
                        fontname=FONT_NAME, color=FONT_COLOR)
        
        pos = self._apply_offsets(UPPER_FORM['personnel_unit']['x'], UPPER_FORM['personnel_unit']['y'], 'personnel_unit')
        page.insert_text(pos, data['personnel_unit'], fontsize=UPPER_FORM['personnel_unit']['size'], 
                        fontname=FONT_NAME, color=FONT_COLOR)
        
        # Item classification and ammunition
        pos = self._apply_offsets(UPPER_FORM['item_type']['x'], UPPER_FORM['item_type']['y'], 'item_type')
        page.insert_text(pos, data['item_type'], fontsize=UPPER_FORM['item_type']['size'], 
                        fontname=FONT_NAME, color=FONT_COLOR)
        
        pos = self._apply_offsets(UPPER_FORM['mags']['x'], UPPER_FORM['mags']['y'], 'mags')
        page.insert_text(pos, data['mags'], fontsize=UPPER_FORM['mags']['size'], 
                        fontname=FONT_NAME, color=FONT_COLOR)
        
        pos = self._apply_offsets(UPPER_FORM['rounds']['x'], UPPER_FORM['rounds']['y'], 'rounds')
        page.insert_text(pos, data['rounds'], fontsize=UPPER_FORM['rounds']['size'], 
                        fontname=FONT_NAME, color=FONT_COLOR)
        
        # Number of items and serial number
        pos = self._apply_offsets(UPPER_FORM['nr_of_items']['x'], UPPER_FORM['nr_of_items']['y'], 'nr_of_items')
        page.insert_text(pos, "1", fontsize=UPPER_FORM['nr_of_items']['size'], 
                        fontname=FONT_NAME, color=FONT_COLOR)
        
        pos = self._apply_offsets(UPPER_FORM['item_serial']['x'], UPPER_FORM['item_serial']['y'], 'item_serial')
        page.insert_text(pos, data['item_serial'], fontsize=UPPER_FORM['item_serial']['size'], 
                        fontname=FONT_NAME, color=FONT_COLOR)
        
        # Purpose and telephone
        pos = self._apply_offsets(UPPER_FORM['duty_type']['x'], UPPER_FORM['duty_type']['y'], 'duty_type')
        page.insert_text(pos, data['duty_type'], fontsize=UPPER_FORM['duty_type']['size'], 
                        fontname=FONT_NAME, color=FONT_COLOR)
        
        pos = self._apply_offsets(UPPER_FORM['personnel_tel']['x'], UPPER_FORM['personnel_tel']['y'], 'personnel_tel')
        page.insert_text(pos, data['personnel_tel'], fontsize=UPPER_FORM['personnel_tel']['size'], 
                        fontname=FONT_NAME, color=FONT_COLOR)
        
        # Signatures
        pos = self._apply_offsets(UPPER_FORM['received_by']['x'], UPPER_FORM['received_by']['y'], 'received_by')
        page.insert_text(pos, data['personnel_full'], fontsize=UPPER_FORM['received_by']['size'], 
                        fontname=FONT_NAME, color=FONT_COLOR)
        
        pos = self._apply_offsets(UPPER_FORM['issued_by']['x'], UPPER_FORM['issued_by']['y'], 'issued_by')
        page.insert_text(pos, data['issued_by'], fontsize=UPPER_FORM['issued_by']['size'], 
                        fontname=FONT_NAME, color=FONT_COLOR)
        pos = self._apply_offsets(UPPER_FORM['issued_by']['x'], UPPER_FORM['issued_by']['y'] + 11)
        page.insert_text(pos, 'Duty Armorer', fontsize=UPPER_FORM['issued_by']['size'],
                        fontname=FONT_NAME, color=FONT_COLOR)

        # Accessories and remarks (space below received_by on the left)
        self._fill_accessories_remarks(
            page, data,
            base_x=UPPER_FORM['received_by']['x'],
            base_y=371
        )
    
    def _fill_lower_form(self, page, data):
        """Fill the lower form section with configurable positions"""
        # Apply lower form offset
        y_offset = LOWER_FORM_Y_OFFSET
        
        # Date field (top right)
        pos = self._apply_offsets(UPPER_FORM['date']['x'], UPPER_FORM['date']['y'] + y_offset, 'date')
        page.insert_text(pos, data['date'], fontsize=UPPER_FORM['date']['size'], 
                        fontname=FONT_NAME, color=FONT_COLOR)
        
        # Personnel information line
        pos = self._apply_offsets(UPPER_FORM['personnel_name']['x'], UPPER_FORM['personnel_name']['y'] + y_offset, 'personnel_name')
        page.insert_text(pos, data['personnel_name'], fontsize=UPPER_FORM['personnel_name']['size'], 
                        fontname=FONT_NAME, color=FONT_COLOR)
        
        pos = self._apply_offsets(UPPER_FORM['personnel_rank']['x'], UPPER_FORM['personnel_rank']['y'] + y_offset, 'personnel_rank')
        page.insert_text(pos, data['personnel_rank'], fontsize=UPPER_FORM['personnel_rank']['size'], 
                        fontname=FONT_NAME, color=FONT_COLOR)
        
        pos = self._apply_offsets(UPPER_FORM['personnel_serial']['x'], UPPER_FORM['personnel_serial']['y'] + y_offset, 'personnel_serial')
        page.insert_text(pos, data['personnel_serial'], fontsize=UPPER_FORM['personnel_serial']['size'], 
                        fontname=FONT_NAME, color=FONT_COLOR)
        
        pos = self._apply_offsets(UPPER_FORM['personnel_unit']['x'], UPPER_FORM['personnel_unit']['y'] + y_offset, 'personnel_unit')
        page.insert_text(pos, data['personnel_unit'], fontsize=UPPER_FORM['personnel_unit']['size'], 
                        fontname=FONT_NAME, color=FONT_COLOR)
        
        # Item classification and ammunition
        pos = self._apply_offsets(UPPER_FORM['item_type']['x'], UPPER_FORM['item_type']['y'] + y_offset, 'item_type')
        page.insert_text(pos, data['item_type'], fontsize=UPPER_FORM['item_type']['size'], 
                        fontname=FONT_NAME, color=FONT_COLOR)
        
        pos = self._apply_offsets(UPPER_FORM['mags']['x'], UPPER_FORM['mags']['y'] + y_offset, 'mags')
        page.insert_text(pos, data['mags'], fontsize=UPPER_FORM['mags']['size'], 
                        fontname=FONT_NAME, color=FONT_COLOR)
        
        pos = self._apply_offsets(UPPER_FORM['rounds']['x'] + 6, UPPER_FORM['rounds']['y'] + y_offset, 'rounds')
        page.insert_text(pos, data['rounds'], fontsize=UPPER_FORM['rounds']['size'], 
                        fontname=FONT_NAME, color=FONT_COLOR)
        
        # Number of items and serial number
        pos = self._apply_offsets(UPPER_FORM['nr_of_items']['x'], UPPER_FORM['nr_of_items']['y'] + y_offset, 'nr_of_items')
        page.insert_text(pos, "1", fontsize=UPPER_FORM['nr_of_items']['size'], 
                        fontname=FONT_NAME, color=FONT_COLOR)
        
        pos = self._apply_offsets(UPPER_FORM['item_serial']['x'], UPPER_FORM['item_serial']['y'] + y_offset, 'item_serial')
        page.insert_text(pos, data['item_serial'], fontsize=UPPER_FORM['item_serial']['size'], 
                        fontname=FONT_NAME, color=FONT_COLOR)
        
        # Purpose and telephone
        pos = self._apply_offsets(UPPER_FORM['duty_type']['x'], UPPER_FORM['duty_type']['y'] + y_offset, 'duty_type')
        page.insert_text(pos, data['duty_type'], fontsize=UPPER_FORM['duty_type']['size'], 
                        fontname=FONT_NAME, color=FONT_COLOR)
        
        pos = self._apply_offsets(UPPER_FORM['personnel_tel']['x'], UPPER_FORM['personnel_tel']['y'] + y_offset, 'personnel_tel')
        page.insert_text(pos, data['personnel_tel'], fontsize=UPPER_FORM['personnel_tel']['size'], 
                        fontname=FONT_NAME, color=FONT_COLOR)
        
        # Signatures (note: lower form signature position is slightly different)
        pos = self._apply_offsets(UPPER_FORM['received_by']['x'], UPPER_FORM['received_by']['y'] + y_offset - 10, 'received_by')
        page.insert_text(pos, data['personnel_full'], fontsize=UPPER_FORM['received_by']['size'], 
                        fontname=FONT_NAME, color=FONT_COLOR)
        
        pos = self._apply_offsets(UPPER_FORM['issued_by']['x'], UPPER_FORM['issued_by']['y'] + y_offset - 10, 'issued_by')
        page.insert_text(pos, data['issued_by'], fontsize=UPPER_FORM['issued_by']['size'], 
                        fontname=FONT_NAME, color=FONT_COLOR)
        pos = self._apply_offsets(UPPER_FORM['issued_by']['x'], UPPER_FORM['issued_by']['y'] + y_offset - 10 + 11)
        page.insert_text(pos, 'Duty Armorer', fontsize=UPPER_FORM['issued_by']['size'],
                        fontname=FONT_NAME, color=FONT_COLOR)

        # Accessories and remarks (space below received_by on the left)
        self._fill_accessories_remarks(
            page, data,
            base_x=UPPER_FORM['received_by']['x'],
            base_y=371 + y_offset - 10
        )
    
    def _fill_accessories_remarks(self, page, data, base_x, base_y):
        """
        Render withdrawn accessories list and remarks/notes below received_by.
        base_x/base_y are raw template coordinates (offsets applied inside).
        """
        acc_lines = data.get('accessories_lines', [])
        remarks   = (data.get('notes') or '').strip()
        if not acc_lines and not remarks:
            return

        LINE_H = 10
        FONT_SIZE = 7
        ACC_FONT = "helv"
        BLUE = (0, 0, 1)
        RED = (1, 0, 0)
        y = base_y

        if acc_lines:
            pos = self._apply_offsets(base_x, y)
            page.insert_text(pos, 'Withdrawn Accessories:', fontsize=FONT_SIZE,
                             fontname=ACC_FONT, color=BLUE)
            y += LINE_H
            for line in acc_lines:
                pos = self._apply_offsets(base_x + 8, y)
                page.insert_text(pos, line, fontsize=FONT_SIZE,
                                 fontname=ACC_FONT, color=RED)
                y += LINE_H

        if remarks:
            if acc_lines:
                y += 4
            pos = self._apply_offsets(base_x, y)
            page.insert_text(pos, 'Remarks:', fontsize=FONT_SIZE,
                             fontname=ACC_FONT, color=BLUE)
            y += LINE_H
            # Wrap long remarks at ~70 chars
            words = remarks.split()
            current = ''
            for word in words:
                if len(current) + len(word) + 1 <= 70:
                    current = (current + ' ' + word).strip()
                else:
                    pos = self._apply_offsets(base_x + 8, y)
                    page.insert_text(pos, current, fontsize=FONT_SIZE,
                                     fontname=ACC_FONT, color=RED)
                    y += LINE_H
                    current = word
            if current:
                pos = self._apply_offsets(base_x + 8, y)
                page.insert_text(pos, current, fontsize=FONT_SIZE,
                                 fontname=ACC_FONT, color=RED)

    def get_page_info(self):
        """
        Get PDF page dimensions and info for coordinate mapping
        Useful for debugging text placement
        """
        doc = fitz.open(self.template_path)
        page = doc[0]
        info = {
            'width': page.rect.width,
            'height': page.rect.height,
            'rotation': page.rotation,
        }
        doc.close()
        return info
