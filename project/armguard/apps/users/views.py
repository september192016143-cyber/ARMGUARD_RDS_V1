import json
import os
import shutil

from django.contrib.auth import get_user_model, logout
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib import messages
from django.views.generic import ListView, CreateView, UpdateView
from django.urls import reverse_lazy
from django.views import View
from django import forms
from django.shortcuts import redirect, render
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.conf import settings as django_settings
from django.contrib.auth.decorators import login_required
from .models import UserProfile, ROLE_CHOICES, PasswordHistory
from armguard.apps.personnel.models import Personnel
# H1 FIX: Import per-module permission helpers for user management.
from armguard.utils.permissions import can_manage_users as _can_manage_users, is_admin as _is_admin


@require_POST
def logout_view(request):
    logout(request)
    return redirect('login')


User = get_user_model()


def _personnel_map_json(qs):
    """Return a JSON string mapping pk -> {first, last, pid, afsn} for auto-fill."""
    return json.dumps({
        str(p['pk']): {'first': p['first_name'], 'last': p['last_name'], 'pid': p['Personnel_ID'], 'afsn': p['AFSN'] or ''}
        for p in qs.values('pk', 'first_name', 'last_name', 'Personnel_ID', 'AFSN')
    })


def _personnel_pid_map_json(qs):
    """Return a JSON string mapping Personnel_ID -> pk for QR scan / ID search."""
    return json.dumps({
        p['Personnel_ID']: str(p['pk'])
        for p in qs.values('pk', 'Personnel_ID')
    })


# ---------------------------------------------------------------------------
# Forms
# ---------------------------------------------------------------------------

class _PersonnelChoiceField(forms.ModelChoiceField):
    """ModelChoiceField that displays rank + full name + AFSN + Personnel_ID."""
    def label_from_instance(self, obj):
        return f"{obj.get_rank_display()} {obj.first_name} {obj.last_name} — {obj.AFSN} | {obj.Personnel_ID}"


class UserCreateForm(forms.Form):
    username    = forms.CharField(max_length=150, widget=forms.TextInput(attrs={'autocomplete': 'username'}))
    first_name  = forms.CharField(max_length=150, required=False, widget=forms.TextInput(attrs={'autocomplete': 'given-name'}))
    last_name   = forms.CharField(max_length=150, required=False, widget=forms.TextInput(attrs={'autocomplete': 'family-name'}))
    email       = forms.EmailField(required=False, widget=forms.EmailInput(attrs={'autocomplete': 'email'}))
    role         = forms.ChoiceField(choices=ROLE_CHOICES)
    is_staff     = forms.BooleanField(required=False, label='Staff (Django admin access)')
    # Per-module permission flags (fine-tune after assigning a Role Group)
    perm_inventory_view   = forms.BooleanField(required=False, label='Can view inventory', initial=False)
    perm_inventory_add    = forms.BooleanField(required=False, label='Can add inventory records', initial=False)
    perm_inventory_edit   = forms.BooleanField(required=False, label='Can edit inventory records', initial=False)
    perm_inventory_delete = forms.BooleanField(required=False, label='Can delete inventory records', initial=False)
    perm_personnel_view   = forms.BooleanField(required=False, label='Can view personnel', initial=False)
    perm_personnel_add    = forms.BooleanField(required=False, label='Can add personnel records', initial=False)
    perm_personnel_edit   = forms.BooleanField(required=False, label='Can edit personnel records', initial=False)
    perm_personnel_delete = forms.BooleanField(required=False, label='Can delete personnel records', initial=False)
    perm_transaction_view   = forms.BooleanField(required=False, label='Can view transactions', initial=False)
    perm_transaction_create = forms.BooleanField(required=False, label='Can create transactions', initial=False)
    perm_reports       = forms.BooleanField(required=False, label='Can view reports', initial=False)
    perm_print         = forms.BooleanField(required=False, label='Can access Print module (ID cards, item tags, PDFs)', initial=False)
    perm_users_manage  = forms.BooleanField(required=False, label='Can manage user accounts', initial=False)
    require_2fa        = forms.BooleanField(required=False, label='Require 2FA for this user', initial=True)
    password1   = forms.CharField(widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}), label='Password')
    password2   = forms.CharField(widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}), label='Confirm password')
    linked_personnel = _PersonnelChoiceField(
        queryset=Personnel.objects.filter(user__isnull=True).order_by('last_name', 'first_name'),
        required=False,
        empty_label='— No linked personnel —',
        label='Link to Personnel Record',
        help_text='Optionally link this account to an existing personnel record.',
    )

    def clean_username(self):
        uname = self.cleaned_data['username'].strip()
        if User.objects.filter(username=uname).exists():
            raise forms.ValidationError('A user with that username already exists.')
        return uname

    def clean(self):
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError
        cd = super().clean()
        p1, p2 = cd.get('password1', ''), cd.get('password2', '')
        if p1 and p2 and p1 != p2:
            self.add_error('password2', 'Passwords do not match.')
        elif p1:
            try:
                validate_password(p1)
            except DjangoValidationError as e:
                self.add_error('password1', e)
        return cd


class UserUpdateForm(forms.Form):
    first_name    = forms.CharField(max_length=150, required=False, widget=forms.TextInput(attrs={'autocomplete': 'given-name'}))
    last_name     = forms.CharField(max_length=150, required=False, widget=forms.TextInput(attrs={'autocomplete': 'family-name'}))
    email         = forms.EmailField(required=False, widget=forms.EmailInput(attrs={'autocomplete': 'email'}))
    role          = forms.ChoiceField(choices=ROLE_CHOICES)
    is_staff      = forms.BooleanField(required=False, label='Staff (Django admin access)')
    is_active     = forms.BooleanField(required=False, label='Active', initial=True)
    # Per-module permission flags (fine-tune after assigning a Role Group)
    perm_inventory_view   = forms.BooleanField(required=False, label='Can view inventory')
    perm_inventory_add    = forms.BooleanField(required=False, label='Can add inventory records')
    perm_inventory_edit   = forms.BooleanField(required=False, label='Can edit inventory records')
    perm_inventory_delete = forms.BooleanField(required=False, label='Can delete inventory records')
    perm_personnel_view   = forms.BooleanField(required=False, label='Can view personnel')
    perm_personnel_add    = forms.BooleanField(required=False, label='Can add personnel records')
    perm_personnel_edit   = forms.BooleanField(required=False, label='Can edit personnel records')
    perm_personnel_delete = forms.BooleanField(required=False, label='Can delete personnel records')
    perm_transaction_view   = forms.BooleanField(required=False, label='Can view transactions')
    perm_transaction_create = forms.BooleanField(required=False, label='Can create transactions')
    perm_reports       = forms.BooleanField(required=False, label='Can view reports')
    perm_print         = forms.BooleanField(required=False, label='Can access Print module (ID cards, item tags, PDFs)')
    perm_users_manage  = forms.BooleanField(required=False, label='Can manage user accounts')
    require_2fa        = forms.BooleanField(required=False, label='Require 2FA for this user')
    new_password1 = forms.CharField(widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}), required=False,
                                    label='New password',
                                    help_text='Leave blank to keep current password.')
    new_password2 = forms.CharField(widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}), required=False,
                                    label='Confirm new password')
    linked_personnel = _PersonnelChoiceField(
        queryset=Personnel.objects.none(),   # overridden in __init__
        required=False,
        empty_label='— No linked personnel —',
        label='Link to Personnel Record',
        help_text='Optionally link this account to a personnel record.',
    )

    def __init__(self, *args, current_role=None, current_linked_pk=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Preserve unknown role values (e.g. legacy 'Viewer') so saving doesn't overwrite them
        if current_role:
            known = [c[0] for c in ROLE_CHOICES]
            if current_role not in known:
                self.fields['role'].choices = [(current_role, current_role)] + list(ROLE_CHOICES)
        # Queryset: unlinked + whichever is currently linked to this user
        qs = Personnel.objects.filter(user__isnull=True)
        if current_linked_pk:
            from django.db.models import Q
            qs = Personnel.objects.filter(Q(user__isnull=True) | Q(Personnel_ID=current_linked_pk))
        self.fields['linked_personnel'].queryset = qs.order_by('last_name', 'first_name')

    def clean(self):
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError
        cd = super().clean()
        p1, p2 = cd.get('new_password1', ''), cd.get('new_password2', '')
        if p1 and p1 != p2:
            self.add_error('new_password2', 'Passwords do not match.')
        elif p1:
            try:
                validate_password(p1)
            except DjangoValidationError as e:
                self.add_error('new_password1', e)
        return cd


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

class UserListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model                = User
    template_name        = 'users/user_list.html'
    context_object_name  = 'users'
    ordering             = ['username']

    def test_func(self):
        return _can_manage_users(self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['can_add'] = _can_manage_users(self.request.user)
        ctx['can_edit'] = _can_manage_users(self.request.user)
        try:
            from django_otp.plugins.otp_totp.models import TOTPDevice
            ctx['enrolled_2fa_ids'] = set(
                TOTPDevice.objects.filter(confirmed=True).values_list('user_id', flat=True)
            )
        except Exception:
            ctx['enrolled_2fa_ids'] = set()
        return ctx


class UserCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    template_name = 'users/user_form.html'
    success_url   = reverse_lazy('user-list')

    def test_func(self):
        return _can_manage_users(self.request.user)

    def get(self, request, *args, **kwargs):
        qs = Personnel.objects.filter(user__isnull=True)
        return self.render_to_response({
            'form': UserCreateForm(), 'action': 'Add',
            'personnel_json':     _personnel_map_json(qs),
            'personnel_pid_json': _personnel_pid_map_json(qs),
        })

    def post(self, request, *args, **kwargs):
        form = UserCreateForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            user = User.objects.create_user(
                username   = cd['username'],
                password   = cd['password1'],
                first_name = cd['first_name'],
                last_name  = cd['last_name'],
                email      = cd['email'],
                is_staff   = cd['is_staff'] if request.user.is_superuser else False,
            )
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.role = cd['role']
            if cd['role'] in ('Administrator', 'Administrator — View Only', 'Administrator — Edit & Add', 'Armorer'):
                profile.perm_inventory_view   = cd.get('perm_inventory_view', False)
                profile.perm_inventory_add    = cd.get('perm_inventory_add', False)
                profile.perm_inventory_edit   = cd.get('perm_inventory_edit', False)
                profile.perm_inventory_delete = cd.get('perm_inventory_delete', False)
                profile.perm_personnel_view   = cd.get('perm_personnel_view', False)
                profile.perm_personnel_add    = cd.get('perm_personnel_add', False)
                profile.perm_personnel_edit   = cd.get('perm_personnel_edit', False)
                profile.perm_personnel_delete = cd.get('perm_personnel_delete', False)
                profile.perm_transaction_view   = cd.get('perm_transaction_view', False)
                profile.perm_transaction_create = cd.get('perm_transaction_create', False)
                profile.perm_reports       = cd.get('perm_reports', False)
                profile.perm_print         = cd.get('perm_print', False)
                profile.perm_users_manage  = cd.get('perm_users_manage', False)
            profile.require_2fa = cd.get('require_2fa', True)
            profile.save()
            # G16-EXT: Record initial password in history to prevent immediate reuse.
            PasswordHistory.objects.create(user=user, password_hash=user.password)
            # Link personnel record if selected
            if cd.get('linked_personnel'):
                p = cd['linked_personnel']
                p.user = user
                p.save(update_fields=['user'])
            messages.success(request, f"User '{user.username}' created successfully.")
            return redirect(self.success_url)
        return self.render_to_response({'form': form, 'action': 'Add'})


class UserUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model         = User
    template_name = 'users/user_form.html'
    success_url   = reverse_lazy('user-list')
    fields        = []   # handled manually

    def test_func(self):
        return _can_manage_users(self.request.user)

    def _make_form(self, data=None):
        user = self.object
        current_role = getattr(getattr(user, 'profile', None), 'role', 'Armorer')
        current_linked = getattr(user, 'personnel', None)  # reverse OneToOne
        current_linked_pk = current_linked.Personnel_ID if current_linked else None
        profile = getattr(user, 'profile', None)
        initial = {
            'first_name':        user.first_name,
            'last_name':         user.last_name,
            'email':             user.email,
            'is_staff':          user.is_staff,
            'is_active':         user.is_active,
            'role':              current_role,
            'linked_personnel':  current_linked_pk,
            'perm_inventory_view':   getattr(profile, 'perm_inventory_view', False),
            'perm_inventory_add':    getattr(profile, 'perm_inventory_add', False),
            'perm_inventory_edit':   getattr(profile, 'perm_inventory_edit', False),
            'perm_inventory_delete': getattr(profile, 'perm_inventory_delete', False),
            'perm_personnel_view':   getattr(profile, 'perm_personnel_view', False),
            'perm_personnel_add':    getattr(profile, 'perm_personnel_add', False),
            'perm_personnel_edit':   getattr(profile, 'perm_personnel_edit', False),
            'perm_personnel_delete': getattr(profile, 'perm_personnel_delete', False),
            'perm_transaction_view':   getattr(profile, 'perm_transaction_view', False),
            'perm_transaction_create': getattr(profile, 'perm_transaction_create', False),
            'perm_reports':      getattr(profile, 'perm_reports', False),
            'perm_print':        getattr(profile, 'perm_print', False),
            'perm_users_manage': getattr(profile, 'perm_users_manage', False),
            'require_2fa':       getattr(profile, 'require_2fa', True),
        }
        if data:
            return UserUpdateForm(data, initial=initial, current_role=current_role,
                                  current_linked_pk=current_linked_pk)
        return UserUpdateForm(initial=initial, current_role=current_role,
                              current_linked_pk=current_linked_pk)

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.is_superuser and not request.user.is_superuser:
            messages.error(request, "You do not have permission to edit a superuser account.")
            return redirect('user-list')
        current_linked = getattr(self.object, 'personnel', None)
        current_linked_pk = current_linked.Personnel_ID if current_linked else None
        from django.db.models import Q
        qs = Personnel.objects.filter(
            Q(user__isnull=True) | Q(Personnel_ID=current_linked_pk)
        ) if current_linked_pk else Personnel.objects.filter(user__isnull=True)
        return self.render_to_response({
            'form': self._make_form(), 'action': 'Edit', 'edit_user': self.object,
            'personnel_json':     _personnel_map_json(qs),
            'personnel_pid_json': _personnel_pid_map_json(qs),
        })

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.is_superuser and not request.user.is_superuser:
            messages.error(request, "You do not have permission to edit a superuser account.")
            return redirect('user-list')
        form = self._make_form(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            self.object.first_name = cd['first_name']
            self.object.last_name  = cd['last_name']
            self.object.email      = cd['email']
            if request.user.is_superuser:
                self.object.is_staff = cd['is_staff']
            self.object.is_active  = cd['is_active']
            if cd['new_password1']:
                self.object.set_password(cd['new_password1'])
            self.object.save()
            # G16-EXT: Record new password in history after successful change.
            if cd['new_password1']:
                PasswordHistory.objects.create(
                    user=self.object, password_hash=self.object.password
                )
            profile, _ = UserProfile.objects.get_or_create(user=self.object)
            profile.role = cd['role']
            if cd['role'] in ('Administrator', 'Administrator — View Only', 'Administrator — Edit & Add', 'Armorer'):
                profile.perm_inventory_view   = cd.get('perm_inventory_view', False)
                profile.perm_inventory_add    = cd.get('perm_inventory_add', False)
                profile.perm_inventory_edit   = cd.get('perm_inventory_edit', False)
                profile.perm_inventory_delete = cd.get('perm_inventory_delete', False)
                profile.perm_personnel_view   = cd.get('perm_personnel_view', False)
                profile.perm_personnel_add    = cd.get('perm_personnel_add', False)
                profile.perm_personnel_edit   = cd.get('perm_personnel_edit', False)
                profile.perm_personnel_delete = cd.get('perm_personnel_delete', False)
                profile.perm_transaction_view   = cd.get('perm_transaction_view', False)
                profile.perm_transaction_create = cd.get('perm_transaction_create', False)
                profile.perm_reports       = cd.get('perm_reports', False)
                profile.perm_print         = cd.get('perm_print', False)
                profile.perm_users_manage  = cd.get('perm_users_manage', False)
            profile.require_2fa = cd.get('require_2fa', True)
            profile.save()
            # Update personnel link: clear old link, set new one
            old_linked = getattr(self.object, 'personnel', None)
            new_linked = cd.get('linked_personnel')   # Personnel instance or None
            if old_linked != new_linked:
                if old_linked:
                    old_linked.user = None
                    old_linked.save(update_fields=['user'])
                if new_linked:
                    new_linked.user = self.object
                    new_linked.save(update_fields=['user'])
            messages.success(request, f"User '{self.object.username}' updated successfully.")
            return redirect(self.success_url)
        return self.render_to_response(
            {'form': form, 'action': 'Edit', 'edit_user': self.object})


class UserDeleteView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return _can_manage_users(self.request.user)

    def post(self, request, pk, *args, **kwargs):
        from django.shortcuts import get_object_or_404
        user = get_object_or_404(User, pk=pk)
        if user.is_superuser and not request.user.is_superuser:
            messages.error(request, "You do not have permission to delete a superuser account.")
            return redirect('user-list')
        if user == request.user:
            messages.error(request, "You cannot delete your own account.")
            return redirect('user-list')
        username = user.username
        user.delete()
        messages.success(request, f"User '{username}' deleted.")
        return redirect('user-list')


class UserToggle2FAView(LoginRequiredMixin, View):
    """Toggle the per-user require_2fa flag. Requires edit permission."""

    def post(self, request, pk, *args, **kwargs):
        req_profile = getattr(request.user, 'profile', None)
        if not request.user.is_superuser and not (req_profile and req_profile.perm_users_manage):
            messages.error(request, 'You do not have permission to change 2FA settings.')
            return redirect('user-list')
        from django.shortcuts import get_object_or_404
        target = get_object_or_404(User, pk=pk)
        if target.is_superuser:
            messages.error(request, 'Cannot change 2FA requirements for a superuser account.')
            return redirect('user-list')
        target_profile, _ = UserProfile.objects.get_or_create(user=target)
        target_profile.require_2fa = not target_profile.require_2fa
        target_profile.save(update_fields=['require_2fa'])
        state = 'required' if target_profile.require_2fa else 'exempted'
        messages.success(request, f"2FA is now {state} for \u2018{target.username}\u2019.")
        return redirect('user-list')


class UserRevoke2FAView(LoginRequiredMixin, View):
    """Superuser-only: delete all confirmed TOTP devices for a target user."""

    def post(self, request, pk, *args, **kwargs):
        if not request.user.is_superuser:
            messages.error(request, 'Only superusers can revoke 2FA devices.')
            return redirect('user-list')
        from django.shortcuts import get_object_or_404
        from django_otp.plugins.otp_totp.models import TOTPDevice
        from django_otp.plugins.otp_static.models import StaticDevice
        target = get_object_or_404(User, pk=pk)
        deleted_totp, _ = TOTPDevice.objects.filter(user=target).delete()
        deleted_static, _ = StaticDevice.objects.filter(user=target).delete()
        total = deleted_totp + deleted_static
        if total:
            messages.success(request, f"2FA device(s) revoked for '{target.username}'. They will be prompted to re-enroll on next login.")
        else:
            messages.info(request, f"No 2FA devices were enrolled for '{target.username}'.")
        return redirect('user-list')


# ---------------------------------------------------------------------------
# G15 FIX: TOTP multi-factor authentication views
# ---------------------------------------------------------------------------

import base64
import io
import qrcode
from django_otp.plugins.otp_totp.models import TOTPDevice
from django_otp import login as otp_login, match_token


class OTPSetupView(LoginRequiredMixin, View):
    """
    Enroll a TOTP device for the current user.

    GET  → generates a new (unconfirmed) TOTPDevice, renders QR code.
    POST → accepts the first token; if correct, marks device confirmed and
           redirects to OTP verify (which logs in with the device straight away).
    """
    template_name = 'registration/otp_setup.html'

    def get(self, request):
        # Delete any leftover unconfirmed device from a previous aborted setup.
        TOTPDevice.objects.filter(user=request.user, confirmed=False).delete()
        device = TOTPDevice.objects.create(
            user=request.user,
            name=f'{request.user.username}-totp',
            confirmed=False,
        )
        qr_uri = device.config_url   # otpauth:// URI for the authenticator app
        qr_img = qrcode.make(qr_uri)
        buf = io.BytesIO()
        qr_img.save(buf, format='PNG')
        qr_b64 = base64.b64encode(buf.getvalue()).decode()
        return self._render(request, device=device, qr_b64=qr_b64, error=None)

    def post(self, request):
        device = TOTPDevice.objects.filter(user=request.user, confirmed=False).first()
        if not device:
            return redirect('otp-setup')
        token = request.POST.get('token', '').strip()
        if device.verify_token(token):
            device.confirmed = True
            device.save(update_fields=['confirmed'])
            otp_login(request, device)           # marks session as OTP-verified
            request.session['_otp_step_done'] = True  # bypass OTPRequiredMiddleware fast-path
            messages.success(request, 'Two-factor authentication enabled. You are now signed in.')
            return redirect(request.POST.get('next') or 'dashboard')
        # Wrong token — regenerate QR so the user can retry.
        qr_img = qrcode.make(device.config_url)
        buf = io.BytesIO()
        qr_img.save(buf, format='PNG')
        qr_b64 = base64.b64encode(buf.getvalue()).decode()
        return self._render(request, device=device, qr_b64=qr_b64,
                            error='Invalid code. Please try again.')

    def _render(self, request, device, qr_b64, error):
        from django.shortcuts import render
        return render(request, self.template_name, {
            'device': device, 'qr_b64': qr_b64, 'error': error,
            'next': request.GET.get('next') or request.POST.get('next', ''),
        })


class OTPVerifyView(LoginRequiredMixin, View):
    """
    Verify the TOTP token for an already-enrolled device.

    GET  → renders token form.
    POST → verifies token; on success marks session as OTP-verified.
    """
    template_name = 'registration/otp_verify.html'

    def get(self, request):
        # If user has no confirmed device, send them to setup.
        if not TOTPDevice.objects.filter(user=request.user, confirmed=True).exists():
            setup_url = reverse_lazy('otp-setup')
            next_url = request.GET.get('next', '')
            return redirect(f'{setup_url}?next={next_url}')
        return self._render(request, error=None)

    def post(self, request):
        token = request.POST.get('token', '').strip()
        device = match_token(request.user, token)
        if device is not None:
            otp_login(request, device)
            # Mark OTP step as completed in the session so OTPRequiredMiddleware
            # can fast-path on subsequent requests without re-calling is_verified().
            request.session['_otp_step_done'] = True
            next_url = request.POST.get('next') or 'dashboard'
            return redirect(next_url)
        return self._render(request, error='Invalid code. Please try again.')

    def _render(self, request, error):
        from django.shortcuts import render
        return render(request, self.template_name, {
            'error': error,
            'next': request.GET.get('next') or request.POST.get('next', ''),
        })


# ---------------------------------------------------------------------------
# Storage status JSON (admin-only)
# ---------------------------------------------------------------------------

def _dir_size(path):
    """Return total size in bytes of all files under *path* (non-recursive)."""
    total = 0
    try:
        with os.scandir(path) as it:
            for entry in it:
                try:
                    if entry.is_file(follow_symlinks=False):
                        total += entry.stat(follow_symlinks=False).st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


def _file_size(field_file):
    """Safely return the size in bytes of a FieldFile. 0 if missing/unreadable."""
    try:
        if field_file and field_file.name:
            return field_file.size
    except (OSError, ValueError):
        pass
    return 0


def _path_size(path):
    """Return size of a plain path string. 0 if missing."""
    try:
        return os.path.getsize(str(path))
    except OSError:
        return 0


def _fmt(size_bytes):
    for unit in ('B', 'KB', 'MB', 'GB'):
        if size_bytes < 1024:
            return f'{size_bytes:.1f} {unit}'
        size_bytes /= 1024
    return f'{size_bytes:.1f} GB'


def _per_record_storage(media_root):
    """Return per-record storage breakdown for Personnel, Pistols, and Rifles."""
    from armguard.apps.personnel.models import Personnel
    from armguard.apps.inventory.models import Pistol, Rifle

    id_cards_dir = os.path.join(str(media_root), 'personnel_id_cards')

    # ── Personnel ─────────────────────────────────────────────────────────────
    personnel_rows = []
    for p in Personnel.objects.only(
        'Personnel_ID', 'rank', 'first_name', 'last_name',
        'personnel_image', 'qr_code_image',
    ):
        size = (
            _file_size(p.personnel_image) +
            _file_size(p.qr_code_image) +
            _path_size(os.path.join(id_cards_dir, f'{p.Personnel_ID}.png')) +
            _path_size(os.path.join(id_cards_dir, f'{p.Personnel_ID}_front.png')) +
            _path_size(os.path.join(id_cards_dir, f'{p.Personnel_ID}_back.png'))
        )
        name = f'{p.rank} {p.first_name} {p.last_name}'.strip()
        personnel_rows.append({'id': p.Personnel_ID, 'name': name, 'size_bytes': size, 'size': _fmt(size)})

    personnel_rows.sort(key=lambda r: r['size_bytes'], reverse=True)
    p_total = sum(r['size_bytes'] for r in personnel_rows)
    p_avg   = (p_total // len(personnel_rows)) if personnel_rows else 0

    # ── Pistols ───────────────────────────────────────────────────────────────
    pistol_rows = []
    for item in Pistol.objects.only('item_id', 'serial_number', 'serial_image', 'qr_code_image', 'item_tag'):
        size = _file_size(item.serial_image) + _file_size(item.qr_code_image) + _file_size(item.item_tag)
        pistol_rows.append({'id': item.item_id, 'name': item.item_id, 'size_bytes': size, 'size': _fmt(size)})

    pistol_rows.sort(key=lambda r: r['size_bytes'], reverse=True)
    pi_total = sum(r['size_bytes'] for r in pistol_rows)
    pi_avg   = (pi_total // len(pistol_rows)) if pistol_rows else 0

    # ── Rifles ────────────────────────────────────────────────────────────────
    rifle_rows = []
    for item in Rifle.objects.only('item_id', 'serial_number', 'serial_image', 'qr_code_image', 'item_tag'):
        size = _file_size(item.serial_image) + _file_size(item.qr_code_image) + _file_size(item.item_tag)
        rifle_rows.append({'id': item.item_id, 'name': item.item_id, 'size_bytes': size, 'size': _fmt(size)})

    rifle_rows.sort(key=lambda r: r['size_bytes'], reverse=True)
    ri_total = sum(r['size_bytes'] for r in rifle_rows)
    ri_avg   = (ri_total // len(rifle_rows)) if rifle_rows else 0

    return {
        'personnel': {
            'total': _fmt(p_total), 'total_bytes': p_total,
            'avg': _fmt(p_avg), 'count': len(personnel_rows),
            'rows': personnel_rows[:15],
        },
        'pistols': {
            'total': _fmt(pi_total), 'total_bytes': pi_total,
            'avg': _fmt(pi_avg), 'count': len(pistol_rows),
            'rows': pistol_rows[:15],
        },
        'rifles': {
            'total': _fmt(ri_total), 'total_bytes': ri_total,
            'avg': _fmt(ri_avg), 'count': len(rifle_rows),
            'rows': rifle_rows[:15],
        },
    }


# ── System Settings (superuser-only) ──────────────────────────────────────────

class SystemSettingsView(LoginRequiredMixin, View):
    template_name = 'users/settings.html'

    def _guard(self, request):
        if not request.user.is_superuser:
            messages.error(request, 'Access denied.')
            return redirect('dashboard')

    def get(self, request):
        resp = self._guard(request)
        if resp:
            return resp
        from .models import SystemSettings
        from django_otp.plugins.otp_totp.models import TOTPDevice
        total_users   = User.objects.filter(is_active=True).count()
        enrolled_pks  = set(TOTPDevice.objects.filter(confirmed=True).values_list('user_id', flat=True))
        users_with_2fa    = len(enrolled_pks)
        users_without_2fa = max(0, total_users - users_with_2fa)
        non_super_users = (
            User.objects.filter(is_active=True, is_superuser=False)
            .select_related('profile')
            .order_by('username')
        )
        return render(request, self.template_name, {
            's':                  SystemSettings.get(),
            'total_users':        total_users,
            'users_with_2fa':     users_with_2fa,
            'users_without_2fa':  users_without_2fa,
            'non_super_users':    non_super_users,
            'enrolled_2fa_ids':   enrolled_pks,
        })

    def post(self, request):
        resp = self._guard(request)
        if resp:
            return resp
        from .models import SystemSettings
        obj = SystemSettings.get()
        obj.commander_name        = request.POST.get('commander_name', '').strip()
        obj.commander_rank        = request.POST.get('commander_rank', '').strip()
        obj.commander_branch      = request.POST.get('commander_branch', 'PAF').strip()
        obj.commander_designation = request.POST.get('commander_designation', 'Squadron Commander').strip()
        obj.armorer_branch        = request.POST.get('armorer_branch', 'PAF').strip()
        obj.unit_name             = request.POST.get('unit_name', '').strip()
        try:
            obj.pistol_magazine_max_qty = int(request.POST.get('pistol_magazine_max_qty', 4))
        except (ValueError, TypeError):
            obj.pistol_magazine_max_qty = 4
        rifle_val = request.POST.get('rifle_magazine_max_qty', '').strip()
        obj.rifle_magazine_max_qty = int(rifle_val) if rifle_val.isdigit() else None
        # Security fields
        obj.mfa_required = 'mfa_required' in request.POST
        try:
            min_len = int(request.POST.get('password_min_length', 8))
            obj.password_min_length = max(1, min(128, min_len))
        except (ValueError, TypeError):
            obj.password_min_length = 8
        try:
            hist = int(request.POST.get('password_history_count', 5))
            obj.password_history_count = max(0, min(20, hist))
        except (ValueError, TypeError):
            obj.password_history_count = 5
        # Branding — logo upload / clear
        if request.POST.get('clear_app_logo') and obj.app_logo:
            obj.app_logo.delete(save=False)
            obj.app_logo = None
        elif request.FILES.get('app_logo'):
            if obj.app_logo:
                obj.app_logo.delete(save=False)
            obj.app_logo = request.FILES['app_logo']
        obj.save()
        messages.success(request, 'System settings saved.')
        return redirect('system-settings')


@login_required
def storage_status_json(request):
    if not _is_admin(request.user):
        return JsonResponse({'error': 'Forbidden'}, status=403)

    # ── Disk usage ────────────────────────────────────────────────────────────
    media_root = django_settings.MEDIA_ROOT
    try:
        du = shutil.disk_usage(media_root)
        disk = {
            'total_bytes': du.total,
            'used_bytes':  du.used,
            'free_bytes':  du.free,
            'total':       _fmt(du.total),
            'used':        _fmt(du.used),
            'free':        _fmt(du.free),
            'used_pct':    round(du.used / du.total * 100, 1) if du.total else 0,
        }
    except OSError:
        disk = {}

    # ── Media folder breakdown ────────────────────────────────────────────────
    media_folders = [
        ('Personnel Images',     'personnel_images'),
        ('Personnel ID Cards',   'personnel_id_cards'),
        ('QR — Personnel',       'qr_code_images_personnel'),
        ('QR — Pistol',          'qr_code_images_pistol'),
        ('QR — Rifle',           'qr_code_images_rifle'),
        ('Serial Images — Pistol','serial_images_pistol'),
        ('Serial Images — Rifle', 'serial_images_rifle'),
        ('Item ID Tags',         'item_id_tags'),
        ('TR PDF',               'TR_PDF'),
    ]
    folders = []
    for label, rel in media_folders:
        path = media_root / rel if hasattr(media_root, '__truediv__') else os.path.join(str(media_root), rel)
        size = _dir_size(path)
        try:
            count = len([e for e in os.scandir(path) if e.is_file()])
        except OSError:
            count = 0
        folders.append({'label': label, 'size_bytes': size, 'size': _fmt(size), 'files': count})

    # ── Database sizes ────────────────────────────────────────────────────────
    db_path = django_settings.DATABASES['default'].get('NAME', '')
    try:
        db_bytes = os.path.getsize(str(db_path))
        db_size  = _fmt(db_bytes)
    except OSError:
        db_bytes = 0
        db_size  = '—'

    # ── Record counts ─────────────────────────────────────────────────────────
    User = get_user_model()
    try:
        from armguard.apps.inventory.models import Pistol, Rifle, Magazine, Ammunition, Accessory
        from armguard.apps.transactions.models import Transaction
        records = [
            {'label': 'Personnel',    'count': Personnel.objects.count()},
            {'label': 'Pistols',      'count': Pistol.objects.count()},
            {'label': 'Rifles',       'count': Rifle.objects.count()},
            {'label': 'Magazines',    'count': Magazine.objects.count()},
            {'label': 'Ammunition',   'count': Ammunition.objects.count()},
            {'label': 'Accessories',  'count': Accessory.objects.count()},
            {'label': 'Transactions', 'count': Transaction.objects.count()},
            {'label': 'Users',        'count': User.objects.count()},
        ]
    except Exception:
        records = []

    return JsonResponse({
        'disk':       disk,
        'folders':    folders,
        'db':         {'size': db_size, 'size_bytes': db_bytes},
        'records':    records,
        'per_record': _per_record_storage(media_root),
    })
