from django import forms
from .models import (Pistol, Rifle, Magazine, Ammunition, Accessory,
                     STATUS_CHOICES, CONDITION_CHOICES)
import re

# Status choices excluding 'Issued' (must go through Transactions)
_EDITABLE_STATUSES = [s for s in STATUS_CHOICES if s[0] != 'Issued']


class PistolForm(forms.ModelForm):
    class Meta:
        model = Pistol
        fields = ['model', 'serial_number', 'item_condition', 'item_status',
                  'description', 'serial_image']
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['item_status'].choices = _EDITABLE_STATUSES
        for f in self.fields.values():
            f.widget.attrs.setdefault('class', 'form-control')




class RifleAdminForm(forms.ModelForm):
    class Meta:
        model = Rifle
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'serial_number' in self.fields:
            self.fields['serial_number'].required = False

    def clean(self):
        cleaned_data = super().clean()
        factory_qr = cleaned_data.get('factory_qr')
        serial_number = cleaned_data.get('serial_number')
        description = cleaned_data.get('description')
        model = cleaned_data.get('model')
        # Only auto-fill if model is M4 and factory_qr is present
        if model == 'M4' and factory_qr:
            match = re.search(r'(PAF\d{8,})', factory_qr)
            if match:
                serial = match.group(1)
                if not serial_number:
                    cleaned_data['serial_number'] = serial
                before = factory_qr.split(serial)[0]
                after = factory_qr.split(serial)[1]
                if not description:
                    cleaned_data['description'] = before + after
        # Now enforce required
        if model == 'M4' and not cleaned_data.get('serial_number'):
            self.add_error('serial_number', 'This field is required.')
        return cleaned_data


class RifleForm(forms.ModelForm):
    """Front-end form for creating / editing a Rifle record."""
    class Meta:
        model = Rifle
        fields = ['model', 'factory_qr', 'serial_number', 'item_condition',
                  'item_status', 'description', 'serial_image']
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['factory_qr'].required = False
        self.fields['serial_number'].required = False
        self.fields['item_status'].choices = _EDITABLE_STATUSES
        for f in self.fields.values():
            f.widget.attrs.setdefault('class', 'form-control')

    def clean(self):
        cleaned_data = super().clean()
        factory_qr = cleaned_data.get('factory_qr')
        serial_number = cleaned_data.get('serial_number')
        description = cleaned_data.get('description')
        model = cleaned_data.get('model')
        if model == 'M4 Carbine DSAR-15 5.56mm' and factory_qr:
            match = re.search(r'(PAF\d{8,})', factory_qr)
            if match:
                serial = match.group(1)
                if not serial_number:
                    cleaned_data['serial_number'] = serial
                before = factory_qr.split(serial)[0]
                after = factory_qr.split(serial)[1]
                if not description:
                    cleaned_data['description'] = before + after
        if model == 'M4 Carbine DSAR-15 5.56mm' and not cleaned_data.get('serial_number'):
            self.add_error('serial_number', 'Serial number is required for M4 Carbine DSAR-15 5.56mm.')
        elif model != 'M4 Carbine DSAR-15 5.56mm' and not cleaned_data.get('serial_number'):
            self.add_error('serial_number', 'This field is required.')
        return cleaned_data


class MagazineForm(forms.ModelForm):
    class Meta:
        model = Magazine
        fields = ['type', 'quantity', 'description']
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs.setdefault('class', 'form-control')


class AmmunitionForm(forms.ModelForm):
    class Meta:
        model = Ammunition
        fields = ['type', 'lot_number', 'quantity', 'description']
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs.setdefault('class', 'form-control')


class AccessoryForm(forms.ModelForm):
    class Meta:
        model = Accessory
        fields = ['type', 'quantity', 'description']
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs.setdefault('class', 'form-control')
