"""
PDF Form Filler Configuration
Adjust these values to shift text positions and fix alignment issues
"""

# VERTICAL OFFSET ADJUSTMENT
# Increase this value to move ALL text DOWN (positive number)
# Decrease to move UP (negative number)
# Recommended: Try 36 points (0.5 inch) to compensate for printer margin
VERTICAL_OFFSET = 26  # points (26 points = ~0.36 inches, moved up 1cm from 54)

# ROTATION SETTING
# Set to 180 to rotate page upside down (swaps top/bottom margins)
# Set to 0 for normal orientation
ROTATION = 0  # degrees - normal orientation

# HORIZONTAL OFFSET ADJUSTMENT  
# Increase to move ALL text RIGHT (positive number)
# Decrease to move LEFT (negative number)
HORIZONTAL_OFFSET = 0  # points

# UPPER FORM COORDINATES (before offset applied)
# Y coordinates: origin (0,0) at TOP-LEFT, Y increases downward
UPPER_FORM = {
    # Date field (top right)
    'date': {'x': 415, 'y': 116, 'size': 9},
    
    # Personnel information line
    'personnel_name': {'x': 88, 'y': 160, 'size': 9},
    'personnel_rank': {'x': 255, 'y': 160, 'size': 9},
    'personnel_serial': {'x': 375, 'y': 160, 'size': 9},
    'personnel_unit': {'x': 475, 'y': 160, 'size': 9},
    
    # Item classification and ammunition
    'item_type': {'x': 230, 'y': 193, 'size': 9},
    'mags': {'x': 380, 'y': 193, 'size': 9},
    'rounds': {'x': 428, 'y': 193, 'size': 9},
    
    # Number of items and serial number
    'nr_of_items': {'x': 175, 'y': 205, 'size': 9},
    'item_serial': {'x': 335, 'y': 205, 'size': 9},
    
    # Purpose and telephone
    'duty_type': {'x': 155, 'y': 217, 'size': 9},
    'personnel_tel': {'x': 122, 'y': 229, 'size': 9},
    
    # Signatures
    'received_by': {'x': 88, 'y': 323, 'size': 8},
    'issued_by': {'x': 340, 'y': 323, 'size': 8},
}

# LOWER FORM OFFSET
# Distance from upper form to lower form
LOWER_FORM_Y_OFFSET = 453  # points

# FONT SETTINGS
FONT_NAME = "hebo"  # Helvetica Bold
FONT_COLOR = (0, 0, 0)  # Black

# QUICK ADJUSTMENT PRESETS
# Uncomment one of these to quickly apply common adjustments:

# PRESET 1: Shift down 0.5 inch (for most printers)
# VERTICAL_OFFSET = 72

# PRESET 2: Shift down 0.75 inch (for printers with larger top margin)
# VERTICAL_OFFSET = 72

# PRESET 3: Shift down 1 inch (maximum adjustment)
# VERTICAL_OFFSET = 72

# PRESET 4: No adjustment (original positions)
# VERTICAL_OFFSET = 72

# ADVANCED: Individual field adjustments (applied AFTER global offset)
# Use this to fine-tune specific fields
FIELD_ADJUSTMENTS = {
    # Example: Move date field 5 points to the right
    # 'date': {'x': 5, 'y': 0},
    
    # Example: Move personnel name down 2 points
    # 'personnel_name': {'x': 0, 'y': 2},
}

# MEASUREMENT REFERENCE
# 72 points = 1 inch
# 36 points = 0.5 inch
# 18 points = 0.25 inch
# 9 points = 0.125 inch (1/8 inch)
