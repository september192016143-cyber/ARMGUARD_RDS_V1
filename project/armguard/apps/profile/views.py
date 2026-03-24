"""
Profile app views.

User profile management:
  - View own profile information
  - Edit personal details (name, email, photo)
  - Change password
  - View permissions and linked personnel record
"""
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.contrib import messages
from django.shortcuts import render, redirect
from django import forms

User = get_user_model()


# ── Forms ─────────────────────────────────────────────────────────────────────

class ProfileEditForm(forms.Form):
    """Form for editing user's personal information"""
    first_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First name'})
    )
    last_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last name'})
    )
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'email@example.com'})
    )
    profile_photo = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        help_text='Upload a profile photo (JPG, PNG, GIF, max 5MB)'
    )
    remove_photo = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label='Remove current photo'
    )

    def clean_profile_photo(self):
        photo = self.cleaned_data.get('profile_photo')
        if photo:
            # Check file size (5MB limit)
            if photo.size > 5 * 1024 * 1024:
                raise ValidationError('Image file too large (max 5MB)')
            # Check file extension
            ext = photo.name.lower().rsplit('.', 1)[-1]
            if ext not in ('jpg', 'jpeg', 'png', 'gif', 'webp'):
                raise ValidationError('Invalid image format. Use JPG, PNG, GIF, or WebP.')
        return photo


class PasswordChangeForm(forms.Form):
    """Form for changing password"""
    current_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Current password'}),
        label='Current Password'
    )
    new_password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'New password'}),
        label='New Password',
        help_text='At least 8 characters'
    )
    new_password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Confirm new password'}),
        label='Confirm New Password'
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_current_password(self):
        password = self.cleaned_data.get('current_password')
        if not self.user.check_password(password):
            raise ValidationError('Current password is incorrect.')
        return password

    def clean_new_password2(self):
        password1 = self.cleaned_data.get('new_password1')
        password2 = self.cleaned_data.get('new_password2')
        if password1 and password2 and password1 != password2:
            raise ValidationError('New passwords do not match.')
        return password2

    def clean_new_password1(self):
        password = self.cleaned_data.get('new_password1')
        if password:
            # Use Django's password validation
            try:
                validate_password(password, self.user)
            except ValidationError as e:
                raise ValidationError(e.messages)
        return password


# ── Views ─────────────────────────────────────────────────────────────────────

@login_required
def profile_view(request):
    """Display user's profile information"""
    user = request.user
    profile = getattr(user, 'profile', None)
    
    # Get linked personnel record if exists
    personnel = getattr(user, 'personnel', None)
    
    # Get permission summary
    permissions = {}
    if profile:
        if user.is_superuser or profile.role == 'System Administrator':
            permissions['description'] = 'Full system access (all permissions)'
        elif profile.role == 'Administrator — View Only':
            permissions['description'] = 'View-only access to all modules'
            permissions['details'] = [
                'View inventory',
                'View personnel',
                'View transactions',
               ' View reports'
            ]
        elif profile.role == 'Administrator — Edit & Add':
            permissions['description'] = 'Full edit access to all modules'
            permissions['details'] = [
                'Full inventory access',
                'Full personnel access',
                'Create transactions',
                'View reports',
                'Print documents'
            ]
        elif profile.role == 'Armorer':
            permissions['description'] = 'Operations focused'
            permissions['details'] = [
                'View inventory',
                'View personnel',
                'Create transactions',
                'View transaction history'
            ]

    # ID card images + weapons (same as PersonnelDetailView)
    id_card_front_url = None
    id_card_back_url = None
    assigned_pistols = []
    assigned_rifles = []
    issued_pistols = []
    issued_rifles = []
    if personnel:
        import os
        from django.conf import settings
        pid = personnel.pk
        card_dir = os.path.join(settings.MEDIA_ROOT, 'personnel_id_cards')
        front_file = os.path.join(card_dir, f"{pid}_front.png")
        back_file  = os.path.join(card_dir, f"{pid}_back.png")
        id_card_front_url = (
            f"{settings.MEDIA_URL}personnel_id_cards/{pid}_front.png?v={int(os.path.getmtime(front_file))}"
            if os.path.exists(front_file) else None
        )
        id_card_back_url = (
            f"{settings.MEDIA_URL}personnel_id_cards/{pid}_back.png?v={int(os.path.getmtime(back_file))}"
            if os.path.exists(back_file) else None
        )
        assigned_pistols = personnel.pistols_assigned.all()
        assigned_rifles  = personnel.rifles_assigned.all()
        issued_pistols   = personnel.pistols_issued.all()
        issued_rifles    = personnel.rifles_issued.all()

    context = {
        'user': user,
        'profile': profile,
        'personnel': personnel,
        'permissions': permissions,
        'page_title': 'My Profile',
        'id_card_front_url': id_card_front_url,
        'id_card_back_url': id_card_back_url,
        'assigned_pistols': assigned_pistols,
        'assigned_rifles': assigned_rifles,
        'issued_pistols': issued_pistols,
        'issued_rifles': issued_rifles,
    }
    return render(request, 'profile/view.html', context)


@login_required
def profile_edit(request):
    """Edit user's personal information"""
    user = request.user
    
    if request.method == 'POST':
        form = ProfileEditForm(request.POST, request.FILES)
        if form.is_valid():
            # Update basic user fields
            user.first_name = form.cleaned_data['first_name']
            user.last_name = form.cleaned_data['last_name']
            user.email = form.cleaned_data['email']
            user.save()
            
            # Handle profile photo
            if form.cleaned_data.get('profile_photo'):
                # Save to personnel record if linked
                if hasattr(user, 'personnel'):
                    personnel = user.personnel
                    # Delete old photo if exists
                    if personnel.personnel_image:
                        personnel.personnel_image.delete(save=False)
                    personnel.personnel_image = form.cleaned_data['profile_photo']
                    personnel.save()
            
            # Remove photo if requested
            elif form.cleaned_data.get('remove_photo'):
                if hasattr(user, 'personnel') and user.personnel.personnel_image:
                    user.personnel.personnel_image.delete(save=True)
            
            messages.success(request, 'Profile updated successfully.')
            return redirect('profile:view')
    else:
        # Pre-fill form with current data
        form = ProfileEditForm(initial={
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
        })
    
    context = {
        'form': form,
        'user': user,
        'page_title': 'Edit Profile',
    }
    return render(request, 'profile/edit.html', context)


@login_required
def password_change(request):
    """Change user's password"""
    user = request.user
    
    if request.method == 'POST':
        form = PasswordChangeForm(user, request.POST)
        if form.is_valid():
            # Set new password
            user.set_password(form.cleaned_data['new_password1'])
            user.save()
            
            # Update session to prevent logout
            update_session_auth_hash(request, user)
            
            messages.success(request, 'Password changed successfully.')
            return redirect('profile:view')
    else:
        form = PasswordChangeForm(user)
    
    context = {
        'form': form,
        'user': user,
        'page_title': 'Change Password',
    }
    return render(request, 'profile/password_change.html', context)
