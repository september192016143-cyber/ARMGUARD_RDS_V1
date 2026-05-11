import os
import shutil
import logging

from django.contrib.auth import get_user_model, logout
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib import messages
from django.views.generic import ListView, CreateView, UpdateView
from django.urls import reverse_lazy
from django.views import View
from django import forms
from django.shortcuts import redirect, render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.conf import settings as django_settings
from django.contrib.auth.decorators import login_required
from django.utils.http import url_has_allowed_host_and_scheme
from .models import UserProfile, ROLE_CHOICES, PasswordHistory, AuditLog, _get_client_ip, _get_user_agent
from armguard.apps.personnel.models import Personnel, PersonnelGroup, PersonnelSquadron
# H1 FIX: Import per-module permission helpers for user management.
from armguard.utils.permissions import can_manage_users as _can_manage_users, is_admin as _is_admin

_logger = logging.getLogger(__name__)


@require_POST
def logout_view(request):
    logout(request)
    return redirect('login')


User = get_user_model()


def _personnel_map(qs):
    """Return a dict mapping pk -> {first, last, pid, afsn} for auto-fill.
    Returned as a plain dict so the template uses |json_script (XSS-safe).
    """
    return {
        str(p['pk']): {'first': p['first_name'], 'last': p['last_name'], 'pid': p['Personnel_ID'], 'afsn': p['AFSN'] or ''}
        for p in qs.values('pk', 'first_name', 'last_name', 'Personnel_ID', 'AFSN')
    }


def _personnel_pid_map(qs):
    """Return a dict mapping Personnel_ID -> pk for QR scan / ID search.
    Returned as a plain dict so the template uses |json_script (XSS-safe).
    """
    return {
        p['Personnel_ID']: str(p['pk'])
        for p in qs.values('pk', 'Personnel_ID')
    }


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

    def __init__(self, *args, current_role=None, current_linked_pk=None, current_user=None, **kwargs):
        self._user = current_user
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
                validate_password(p1, self._user)
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
    paginate_by          = 25

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
            'personnel_map':     _personnel_map(qs),
            'personnel_pid_map': _personnel_pid_map(qs),
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
                                  current_linked_pk=current_linked_pk, current_user=user)
        return UserUpdateForm(initial=initial, current_role=current_role,
                              current_linked_pk=current_linked_pk, current_user=user)

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
            'personnel_map':     _personnel_map(qs),
            'personnel_pid_map': _personnel_pid_map(qs),
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

            # Capture old permission values BEFORE applying changes so we can diff them.
            _PERM_FIELDS = [
                'role',
                'perm_inventory_view', 'perm_inventory_add',
                'perm_inventory_edit', 'perm_inventory_delete',
                'perm_personnel_view', 'perm_personnel_add',
                'perm_personnel_edit', 'perm_personnel_delete',
                'perm_transaction_view', 'perm_transaction_create',
                'perm_reports', 'perm_print', 'perm_users_manage',
                'require_2fa',
            ]
            old_values = {f: getattr(profile, f) for f in _PERM_FIELDS}

            profile.role = cd['role']
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

            # Write an AuditLog entry for every permission/role change.
            new_values = {f: getattr(profile, f) for f in _PERM_FIELDS}
            changed = {f: (old_values[f], new_values[f]) for f in _PERM_FIELDS if old_values[f] != new_values[f]}
            if changed:
                change_detail = '; '.join(
                    f"{f}: {ov!r} → {nv!r}" for f, (ov, nv) in changed.items()
                )
                try:
                    AuditLog.objects.create(
                        user=request.user,
                        action='UPDATE',
                        model_name='UserProfile',
                        object_pk=str(self.object.pk),
                        message=f"Permission changes on '{self.object.username}': {change_detail}",
                    )
                except Exception:
                    _logger.exception(
                        "Failed to write AuditLog for permission change on user %s",
                        self.object.pk,
                    )
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
            _next = request.POST.get('next') or ''
            if _next and url_has_allowed_host_and_scheme(_next, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
                return redirect(_next)
            return redirect('dashboard')
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
            _next = request.POST.get('next') or ''
            if _next and url_has_allowed_host_and_scheme(_next, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
                return redirect(_next)
            return redirect('dashboard')
        # Wrong code — record in AuditLog so security reviewers can see 2FA bypass attempts.
        try:
            AuditLog.objects.create(
                user=request.user,
                action='OTP_FAILED',
                model_name='User',
                object_pk=str(request.user.pk),
                message=f"OTP verification failed for '{request.user.username}'.",
                ip_address=_get_client_ip(request),
                user_agent=_get_user_agent(request),
            )
        except Exception:
            _logger.warning("Failed to write OTP_FAILED AuditLog for user %s", request.user.pk)
        return self._render(request, error='Invalid code. Please try again.')

    def _render(self, request, error):
        from django.shortcuts import render
        return render(request, self.template_name, {
            'error': error,
            'next': request.GET.get('next') or request.POST.get('next', ''),
        })


# ---------------------------------------------------------------------------
# Session ping — keeps the session alive when "Stay Logged In" is clicked
# ---------------------------------------------------------------------------

@require_POST
@login_required
def session_ping(request):
    """Touch the session so the cookie expiry is reset. Returns 204 No Content."""
    request.session.modified = True
    from django.http import HttpResponse
    return HttpResponse(status=204)


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
            'rows': personnel_rows,
        },
        'pistols': {
            'total': _fmt(pi_total), 'total_bytes': pi_total,
            'avg': _fmt(pi_avg), 'count': len(pistol_rows),
            'rows': pistol_rows,
        },
        'rifles': {
            'total': _fmt(ri_total), 'total_bytes': ri_total,
            'avg': _fmt(ri_avg), 'count': len(rifle_rows),
            'rows': rifle_rows,
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
        s = SystemSettings.get()
        total_users   = User.objects.filter(is_active=True).count()
        enrolled_pks  = set(TOTPDevice.objects.filter(confirmed=True).values_list('user_id', flat=True))
        users_with_2fa    = len(enrolled_pks)
        users_without_2fa = max(0, total_users - users_with_2fa)
        non_super_users = (
            User.objects.filter(is_active=True, is_superuser=False)
            .select_related('profile')
            .order_by('username')
        )
        purpose_visibility_rows = [
            {'label': 'Duty Sentinel',  'pistol_field': 'purpose_duty_sentinel_show_pistol',  'pistol_value': s.purpose_duty_sentinel_show_pistol,  'rifle_field': 'purpose_duty_sentinel_show_rifle',  'rifle_value': s.purpose_duty_sentinel_show_rifle,  'auto_consumables_field': 'purpose_duty_sentinel_auto_consumables', 'auto_consumables_value': s.purpose_duty_sentinel_auto_consumables, 'auto_accessories_field': 'purpose_duty_sentinel_auto_accessories', 'auto_accessories_value': s.purpose_duty_sentinel_auto_accessories, 'auto_print_field': 'auto_print_tr_duty_sentinel', 'auto_print_value': s.auto_print_tr_duty_sentinel},
            {'label': 'Duty Vigil',     'pistol_field': 'purpose_duty_vigil_show_pistol',     'pistol_value': s.purpose_duty_vigil_show_pistol,     'rifle_field': 'purpose_duty_vigil_show_rifle',     'rifle_value': s.purpose_duty_vigil_show_rifle,     'auto_consumables_field': 'purpose_duty_vigil_auto_consumables',    'auto_consumables_value': s.purpose_duty_vigil_auto_consumables,    'auto_accessories_field': 'purpose_duty_vigil_auto_accessories',    'auto_accessories_value': s.purpose_duty_vigil_auto_accessories,    'auto_print_field': 'auto_print_tr_duty_vigil',    'auto_print_value': s.auto_print_tr_duty_vigil},
            {'label': 'Duty Security',  'pistol_field': 'purpose_duty_security_show_pistol',  'pistol_value': s.purpose_duty_security_show_pistol,  'rifle_field': 'purpose_duty_security_show_rifle',  'rifle_value': s.purpose_duty_security_show_rifle,  'auto_consumables_field': 'purpose_duty_security_auto_consumables', 'auto_consumables_value': s.purpose_duty_security_auto_consumables, 'auto_accessories_field': 'purpose_duty_security_auto_accessories', 'auto_accessories_value': s.purpose_duty_security_auto_accessories, 'auto_print_field': 'auto_print_tr_duty_security', 'auto_print_value': s.auto_print_tr_duty_security},
            {'label': 'Honor Guard',    'pistol_field': 'purpose_honor_guard_show_pistol',    'pistol_value': s.purpose_honor_guard_show_pistol,    'rifle_field': 'purpose_honor_guard_show_rifle',    'rifle_value': s.purpose_honor_guard_show_rifle,    'auto_consumables_field': 'purpose_honor_guard_auto_consumables',   'auto_consumables_value': s.purpose_honor_guard_auto_consumables,   'auto_accessories_field': 'purpose_honor_guard_auto_accessories',   'auto_accessories_value': s.purpose_honor_guard_auto_accessories,   'auto_print_field': 'auto_print_tr_honor_guard',   'auto_print_value': s.auto_print_tr_honor_guard},
            {'label': 'Others',         'pistol_field': 'purpose_others_show_pistol',         'pistol_value': s.purpose_others_show_pistol,         'rifle_field': 'purpose_others_show_rifle',         'rifle_value': s.purpose_others_show_rifle,         'auto_consumables_field': 'purpose_others_auto_consumables',        'auto_consumables_value': s.purpose_others_auto_consumables,        'auto_accessories_field': 'purpose_others_auto_accessories',        'auto_accessories_value': s.purpose_others_auto_accessories,        'auto_print_field': 'auto_print_tr_others',        'auto_print_value': s.auto_print_tr_others},
            {'label': 'OREX',           'pistol_field': 'purpose_orex_show_pistol',           'pistol_value': s.purpose_orex_show_pistol,           'rifle_field': 'purpose_orex_show_rifle',           'rifle_value': s.purpose_orex_show_rifle,           'auto_consumables_field': 'purpose_orex_auto_consumables',          'auto_consumables_value': s.purpose_orex_auto_consumables,          'auto_accessories_field': 'purpose_orex_auto_accessories',          'auto_accessories_value': s.purpose_orex_auto_accessories,          'auto_print_field': 'auto_print_tr_orex',          'auto_print_value': s.auto_print_tr_orex},
        ]
        auto_consumable_rows = []  # retired — now in purpose_visibility_rows
        from django.db.models import Count, Value, IntegerField, Subquery, OuterRef
        from django.db.models.functions import Coalesce
        personnel_groups = PersonnelGroup.objects.annotate(
            personnel_count=Coalesce(
                Subquery(
                    Personnel.objects.filter(group=OuterRef('name'))
                        .values('group')
                        .annotate(c=Count('group'))
                        .values('c')[:1],
                    output_field=IntegerField(),
                ),
                Value(0),
            )
        )
        personnel_squadrons = PersonnelSquadron.objects.annotate(
            personnel_count=Coalesce(
                Subquery(
                    Personnel.objects.filter(squadron=OuterRef('name'))
                        .values('squadron')
                        .annotate(c=Count('squadron'))
                        .values('c')[:1],
                    output_field=IntegerField(),
                ),
                Value(0),
            )
        )
        return render(request, self.template_name, {
            's':                       s,
            'total_users':             total_users,
            'users_with_2fa':          users_with_2fa,
            'users_without_2fa':       users_without_2fa,
            'non_super_users':         non_super_users,
            'enrolled_2fa_ids':        enrolled_pks,
            'purpose_visibility_rows': purpose_visibility_rows,
            'auto_consumable_rows':    auto_consumable_rows,
            'personnel_groups':        personnel_groups,
            'personnel_squadrons':     personnel_squadrons,
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
        # Per-role idle session timeouts (UI submits minutes; DB stores seconds)
        _timeout_fields = {
            'timeout_system_admin':    30,
            'timeout_admin_view_only': 30,
            'timeout_admin_edit_add':  30,
            'timeout_armorer':         60,
            'timeout_superuser':        0,
        }
        for field, default in _timeout_fields.items():
            try:
                minutes = int(request.POST.get(field, default))
                setattr(obj, field, max(0, minutes) * 60)
            except (ValueError, TypeError):
                setattr(obj, field, default * 60)
        # Branding — logo upload / clear
        if request.POST.get('clear_app_logo') and obj.app_logo:
            obj.app_logo.delete(save=False)
            obj.app_logo = None
        elif request.FILES.get('app_logo'):
            _logo_file = request.FILES['app_logo']
            # Validate size (2 MB cap) and content (magic-byte check via Pillow).
            _LOGO_MAX_BYTES = 2 * 1024 * 1024
            if _logo_file.size > _LOGO_MAX_BYTES:
                messages.error(request, 'Logo file too large (max 2 MB).')
                return redirect('system-settings')
            try:
                from PIL import Image as _PilImg
                _pil = _PilImg.open(_logo_file)
                if _pil.format not in ('JPEG', 'PNG', 'GIF', 'WEBP'):
                    raise ValueError('unsupported format')
                _pil.verify()
                _logo_file.seek(0)
            except Exception:
                messages.error(request, 'Logo must be a valid image file (JPEG, PNG, GIF, or WebP).')
                return redirect('system-settings')
            if obj.app_logo:
                obj.app_logo.delete(save=False)
            obj.app_logo = _logo_file
        # ── Per-purpose auto TR print ─────────────────────────────────────────
        for field in [
            'auto_print_tr_duty_sentinel', 'auto_print_tr_duty_vigil',
            'auto_print_tr_duty_security', 'auto_print_tr_honor_guard',
            'auto_print_tr_others',        'auto_print_tr_orex',
        ]:
            setattr(obj, field, field in request.POST)

        # Per-purpose weapon field visibility
        for field in [
            'purpose_duty_sentinel_show_pistol',  'purpose_duty_sentinel_show_rifle',
            'purpose_duty_vigil_show_pistol',     'purpose_duty_vigil_show_rifle',
            'purpose_duty_security_show_pistol',  'purpose_duty_security_show_rifle',
            'purpose_honor_guard_show_pistol',    'purpose_honor_guard_show_rifle',
            'purpose_others_show_pistol',         'purpose_others_show_rifle',
            'purpose_orex_show_pistol',           'purpose_orex_show_rifle',
        ]:
            setattr(obj, field, field in request.POST)
        # Guard: every purpose must expose at least one weapon column.
        # If both pistol and rifle are unchecked for a purpose the transaction
        # form would show no weapon fields at all, making that purpose unusable.
        _purpose_pairs = [
            ('Duty Sentinel',  'purpose_duty_sentinel_show_pistol',  'purpose_duty_sentinel_show_rifle'),
            ('Duty Vigil',     'purpose_duty_vigil_show_pistol',     'purpose_duty_vigil_show_rifle'),
            ('Duty Security',  'purpose_duty_security_show_pistol',  'purpose_duty_security_show_rifle'),
            ('Honor Guard',    'purpose_honor_guard_show_pistol',    'purpose_honor_guard_show_rifle'),
            ('Others',         'purpose_others_show_pistol',         'purpose_others_show_rifle'),
            ('OREX',           'purpose_orex_show_pistol',           'purpose_orex_show_rifle'),
        ]
        invalid_purposes = [
            label for label, pf, rf in _purpose_pairs
            if not getattr(obj, pf) and not getattr(obj, rf)
        ]
        if invalid_purposes:
            messages.error(
                request,
                'Each purpose must have at least one weapon field (Pistol or Rifle) enabled. '
                'Both are disabled for: ' + ', '.join(invalid_purposes) + '.'
            )
            return redirect('system-settings')

        # ── TR / PAR defaults ─────────────────────────────────────────────────
        try:
            obj.tr_default_return_hours = max(1, int(request.POST.get('tr_default_return_hours', 24)))
        except (ValueError, TypeError):
            obj.tr_default_return_hours = 24
        obj.require_par_document = 'require_par_document' in request.POST
        _dit = request.POST.get('default_issuance_type', 'TR (Temporary Receipt)')
        obj.default_issuance_type = _dit if _dit in (
            'TR (Temporary Receipt)', 'PAR (Property Acknowledgement Receipt)'
        ) else 'TR (Temporary Receipt)'

        # ── Per-purpose auto-consumables & accessories ────────────────────────
        for field in [
            'purpose_duty_sentinel_auto_consumables', 'purpose_duty_vigil_auto_consumables',
            'purpose_duty_security_auto_consumables', 'purpose_honor_guard_auto_consumables',
            'purpose_others_auto_consumables',        'purpose_orex_auto_consumables',
            'purpose_duty_sentinel_auto_accessories', 'purpose_duty_vigil_auto_accessories',
            'purpose_duty_security_auto_accessories', 'purpose_honor_guard_auto_accessories',
            'purpose_others_auto_accessories',        'purpose_orex_auto_accessories',
        ]:
            setattr(obj, field, field in request.POST)

        # ── Per-purpose loadout defaults + accessory max quantities ──────────
        _psi_fields = {
            # Duty Sentinel
            'duty_sentinel_holster_qty':           1,
            'duty_sentinel_mag_pouch_qty':         3,
            'duty_sentinel_pistol_mag_qty':        4,
            'duty_sentinel_pistol_ammo_qty':       42,
            'duty_sentinel_rifle_sling_qty':       1,
            'duty_sentinel_rifle_short_mag_qty':   7,
            'duty_sentinel_rifle_long_mag_qty':    7,
            'duty_sentinel_rifle_ammo_qty':        210,
            # Duty Vigil
            'duty_vigil_holster_qty':              1,
            'duty_vigil_mag_pouch_qty':            1,
            'duty_vigil_pistol_mag_qty':           2,
            'duty_vigil_pistol_ammo_qty':          21,
            'duty_vigil_rifle_sling_qty':          1,
            'duty_vigil_rifle_short_mag_qty':      7,
            'duty_vigil_rifle_long_mag_qty':       7,
            'duty_vigil_rifle_ammo_qty':           210,
            # Duty Security
            'duty_security_holster_qty':           1,
            'duty_security_mag_pouch_qty':         1,
            'duty_security_pistol_mag_qty':        2,
            'duty_security_pistol_ammo_qty':       21,
            'duty_security_rifle_sling_qty':       1,
            'duty_security_rifle_short_mag_qty':   7,
            'duty_security_rifle_long_mag_qty':    7,
            'duty_security_rifle_ammo_qty':        210,
            # Honor Guard
            'honor_guard_holster_qty':             1,
            'honor_guard_mag_pouch_qty':           1,
            'honor_guard_pistol_mag_qty':          2,
            'honor_guard_pistol_ammo_qty':         21,
            'honor_guard_rifle_sling_qty':         1,
            'honor_guard_rifle_short_mag_qty':     7,
            'honor_guard_rifle_long_mag_qty':      7,
            'honor_guard_rifle_ammo_qty':          210,
            # Others
            'others_holster_qty':                  1,
            'others_mag_pouch_qty':                1,
            'others_pistol_mag_qty':               4,
            'others_pistol_ammo_qty':              42,
            'others_rifle_sling_qty':              1,
            'others_rifle_short_mag_qty':          7,
            'others_rifle_long_mag_qty':           7,
            'others_rifle_ammo_qty':               210,
            # OREX
            'orex_holster_qty':                    1,
            'orex_mag_pouch_qty':                  1,
            'orex_pistol_mag_qty':                 4,
            'orex_pistol_ammo_qty':                42,
            'orex_rifle_sling_qty':                1,
            'orex_rifle_short_mag_qty':            7,
            'orex_rifle_long_mag_qty':             7,
            'orex_rifle_ammo_qty':                 210,
            'duty_sentinel_bandoleer_qty':         0,
            'duty_vigil_bandoleer_qty':            0,
            'duty_security_bandoleer_qty':         0,
            'honor_guard_bandoleer_qty':           0,
            'others_bandoleer_qty':                0,
            'orex_bandoleer_qty':                  0,
            # Accessory max quantities
            'max_pistol_holster_qty':              1,
            'max_magazine_pouch_qty':              3,
            'max_rifle_sling_qty':                 1,
            'max_bandoleer_qty':                   1,
        }
        for field, default in _psi_fields.items():
            try:
                setattr(obj, field, max(0, int(request.POST.get(field, default))))
            except (ValueError, TypeError):
                setattr(obj, field, default)

        obj.save()
        messages.success(request, 'System settings saved.')
        return redirect('system-settings')


# ── Personnel Group management (Settings page) ───────────────────────────────

def _group_guard(request):
    """Return None if superuser, else a redirect."""
    if not request.user.is_authenticated or not request.user.is_superuser:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')


@login_required
@require_POST
def group_add(request):
    resp = _group_guard(request)
    if resp:
        return resp
    name = request.POST.get('name', '').strip()
    if not name:
        messages.error(request, 'Group name cannot be empty.')
        return redirect('system-settings')
    if len(name) > 50:
        messages.error(request, 'Group name must be 50 characters or fewer.')
        return redirect('system-settings')
    _, created = PersonnelGroup.objects.get_or_create(
        name=name,
        defaults={'order': PersonnelGroup.objects.count()},
    )
    if created:
        messages.success(request, f'Group "{name}" added.')
    else:
        messages.warning(request, f'Group "{name}" already exists.')
    return redirect('system-settings')


@login_required
@require_POST
def group_rename(request, pk):
    resp = _group_guard(request)
    if resp:
        return resp
    group = get_object_or_404(PersonnelGroup, pk=pk)
    new_name = request.POST.get('name', '').strip()
    if not new_name:
        messages.error(request, 'Group name cannot be empty.')
        return redirect('system-settings')
    if len(new_name) > 50:
        messages.error(request, 'Group name must be 50 characters or fewer.')
        return redirect('system-settings')
    if PersonnelGroup.objects.filter(name=new_name).exclude(pk=pk).exists():
        messages.error(request, f'A group named "{new_name}" already exists.')
        return redirect('system-settings')
    old_name = group.name
    from django.db import transaction
    with transaction.atomic():
        Personnel.objects.filter(group=old_name).update(group=new_name)
        group.name = new_name
        group.save()
    messages.success(request, f'Group renamed from "{old_name}" to "{new_name}".')
    return redirect('system-settings')


@login_required
@require_POST
def group_delete(request, pk):
    resp = _group_guard(request)
    if resp:
        return resp
    group = get_object_or_404(PersonnelGroup, pk=pk)
    count = Personnel.objects.filter(group=group.name).count()
    if count > 0:
        messages.error(
            request,
            f'Cannot delete "{group.name}" — {count} personnel member{"s" if count != 1 else ""} '
            f'still assigned to this group. Reassign them first.'
        )
        return redirect('system-settings')
    group.delete()
    messages.success(request, f'Group "{group.name}" deleted.')
    return redirect('system-settings')


# ── Personnel Squadron management (Settings page) ─────────────────────────────

@login_required
@require_POST
def squadron_add(request):
    resp = _group_guard(request)
    if resp:
        return resp
    name = request.POST.get('name', '').strip()
    if not name:
        messages.error(request, 'Squadron name cannot be empty.')
        return redirect('system-settings')
    if len(name) > 50:
        messages.error(request, 'Squadron name must be 50 characters or fewer.')
        return redirect('system-settings')
    _, created = PersonnelSquadron.objects.get_or_create(
        name=name,
        defaults={'order': PersonnelSquadron.objects.count()},
    )
    if created:
        messages.success(request, f'Squadron "{name}" added.')
    else:
        messages.warning(request, f'Squadron "{name}" already exists.')
    return redirect('system-settings')


@login_required
@require_POST
def squadron_rename(request, pk):
    resp = _group_guard(request)
    if resp:
        return resp
    squadron = get_object_or_404(PersonnelSquadron, pk=pk)
    new_name = request.POST.get('name', '').strip()
    if not new_name:
        messages.error(request, 'Squadron name cannot be empty.')
        return redirect('system-settings')
    if len(new_name) > 50:
        messages.error(request, 'Squadron name must be 50 characters or fewer.')
        return redirect('system-settings')
    if PersonnelSquadron.objects.filter(name=new_name).exclude(pk=pk).exists():
        messages.error(request, f'A squadron named "{new_name}" already exists.')
        return redirect('system-settings')
    old_name = squadron.name
    from django.db import transaction
    with transaction.atomic():
        Personnel.objects.filter(squadron=old_name).update(squadron=new_name)
        squadron.name = new_name
        squadron.save()
    messages.success(request, f'Squadron renamed from "{old_name}" to "{new_name}".')
    return redirect('system-settings')


@login_required
@require_POST
def squadron_delete(request, pk):
    resp = _group_guard(request)
    if resp:
        return resp
    squadron = get_object_or_404(PersonnelSquadron, pk=pk)
    count = Personnel.objects.filter(squadron=squadron.name).count()
    if count > 0:
        messages.error(
            request,
            f'Cannot delete "{squadron.name}" — {count} personnel member{"s" if count != 1 else ""} '
            f'still assigned to this squadron. Reassign them first.'
        )
        return redirect('system-settings')
    squadron.delete()
    messages.success(request, f'Squadron "{squadron.name}" deleted.')
    return redirect('system-settings')


# ── Data Truncation (superuser-only) ──────────────────────────────────────────

@login_required
@require_POST
def truncate_data(request):
    """
    Truncate selected data tables.  Superuser-only.
    Supported targets (via POST checkbox 'truncate_<name>'):
      - transaction_logs  → TransactionLogs
      - transactions      → Transaction
      - snapshots         → AnalyticsSnapshot
    """
    if not request.user.is_superuser:
        messages.error(request, 'Only superusers can perform data truncation.')
        return redirect('system-settings')

    confirm = request.POST.get('confirm_truncate', '').strip()
    if confirm != 'TRUNCATE':
        messages.error(request, 'Confirmation text did not match. Nothing was deleted.')
        return redirect('system-settings')

    from armguard.apps.transactions.models import Transaction, TransactionLogs
    from armguard.apps.inventory.models import AnalyticsSnapshot, Rifle, Pistol
    from armguard.apps.personnel.models import Personnel
    from django.db import connection as _db_conn

    # All Personnel columns that hold transaction-derived ISSUED state.
    # "assigned" fields are set independently (not by transactions) so they
    # are intentionally excluded — only "issued" fields are cleared.
    _PERSONNEL_CLEAR_COLS = [
        'rifle_item_issued',              'rifle_item_issued_timestamp',     'rifle_item_issued_by',
        'pistol_item_issued',             'pistol_item_issued_timestamp',    'pistol_item_issued_by',
        'magazine_item_issued',           'magazine_item_issued_quantity',   'magazine_item_issued_timestamp',   'magazine_item_issued_by',
        'pistol_magazine_item_issued',    'pistol_magazine_item_issued_quantity', 'pistol_magazine_item_issued_timestamp', 'pistol_magazine_item_issued_by',
        'rifle_magazine_item_issued',     'rifle_magazine_item_issued_quantity',  'rifle_magazine_item_issued_timestamp',  'rifle_magazine_item_issued_by',
        'ammunition_item_issued',         'ammunition_item_issued_quantity',   'ammunition_item_issued_timestamp',   'ammunition_item_issued_by',
        'pistol_ammunition_item_issued',  'pistol_ammunition_item_issued_quantity', 'pistol_ammunition_item_issued_timestamp', 'pistol_ammunition_item_issued_by',
        'rifle_ammunition_item_issued',   'rifle_ammunition_item_issued_quantity',  'rifle_ammunition_item_issued_timestamp',  'rifle_ammunition_item_issued_by',
        'pistol_holster_issued',          'pistol_holster_issued_quantity',   'pistol_holster_issued_timestamp',   'pistol_holster_issued_by',
        'magazine_pouch_issued',          'magazine_pouch_issued_quantity',   'magazine_pouch_issued_timestamp',   'magazine_pouch_issued_by',
        'rifle_sling_issued',             'rifle_sling_issued_quantity',      'rifle_sling_issued_timestamp',      'rifle_sling_issued_by',
        'bandoleer_issued',               'bandoleer_issued_quantity',        'bandoleer_issued_timestamp',        'bandoleer_issued_by',
    ]

    # Map checkbox key → (label, db_table).
    # We use raw SQL DELETE instead of ORM .delete() to:
    #   a) bypass per-row post_delete signals (signals.py fires _write_audit_log
    #      for every row, which can create hundreds of AuditLog entries and
    #      exhaust the DB connection — causing the ActivityLog middleware write
    #      to silently fail after this view returns).
    #   b) be significantly faster for bulk deletes.
    # One summarising AuditLog entry is written below instead.
    targets = {
        'transaction_logs': ('Transaction Logs',   TransactionLogs._meta.db_table),
        'transactions':     ('Transactions',        Transaction._meta.db_table),
        'snapshots':        ('Analytics Snapshots', AnalyticsSnapshot._meta.db_table),
    }

    deleted_summary = []
    _clear_personnel = False
    try:
        with _db_conn.cursor() as _cur:

            # ── Step 1: Restore consumable pool quantities BEFORE deleting rows ──
            # We aggregate net depletion (Withdrawals minus Returns) per pool from
            # the Transaction table while it still exists, then add it back.
            # This mirrors the exact sign convention in adjust_consumable_quantities().
            if request.POST.get('truncate_transactions'):
                from armguard.apps.inventory.models import Magazine, Ammunition, Accessory
                _txn_tbl = Transaction._meta.db_table
                _mag_tbl = Magazine._meta.db_table
                _amm_tbl = Ammunition._meta.db_table
                _acc_tbl = Accessory._meta.db_table

                # Magazine pools — FK-linked per pool row
                for _fk_col, _qty_col in [
                    ('pistol_magazine_id', 'pistol_magazine_quantity'),
                    ('rifle_magazine_id',  'rifle_magazine_quantity'),
                ]:
                    _cur.execute(  # noqa: S608
                        f'UPDATE "{_mag_tbl}" '
                        f'SET quantity = GREATEST(0, quantity + COALESCE(CAST(('
                        f'  SELECT'
                        f'    COALESCE(SUM(CASE WHEN transaction_type=\'Withdrawal\' THEN {_qty_col} ELSE 0 END), 0)'
                        f'  - COALESCE(SUM(CASE WHEN transaction_type=\'Return\'    THEN {_qty_col} ELSE 0 END), 0)'
                        f'  FROM "{_txn_tbl}"'
                        f'  WHERE {_fk_col} = "{_mag_tbl}".id'
                        f'    AND {_qty_col} IS NOT NULL'
                        f') AS INTEGER), 0))'
                    )

                # Ammunition pools — FK-linked per pool row
                for _fk_col, _qty_col in [
                    ('pistol_ammunition_id', 'pistol_ammunition_quantity'),
                    ('rifle_ammunition_id',  'rifle_ammunition_quantity'),
                ]:
                    _cur.execute(  # noqa: S608
                        f'UPDATE "{_amm_tbl}" '
                        f'SET quantity = GREATEST(0, quantity + COALESCE(CAST(('
                        f'  SELECT'
                        f'    COALESCE(SUM(CASE WHEN transaction_type=\'Withdrawal\' THEN {_qty_col} ELSE 0 END), 0)'
                        f'  - COALESCE(SUM(CASE WHEN transaction_type=\'Return\'    THEN {_qty_col} ELSE 0 END), 0)'
                        f'  FROM "{_txn_tbl}"'
                        f'  WHERE {_fk_col} = "{_amm_tbl}".id'
                        f'    AND {_qty_col} IS NOT NULL'
                        f') AS INTEGER), 0))'
                    )

                # Accessory pools — no FK; net goes to the highest-quantity pool of
                # each type (mirrors services.py order_by('-quantity').first()).
                for _acc_type, _qty_col in [
                    ('Pistol Holster',        'pistol_holster_quantity'),
                    ('Pistol Magazine Pouch', 'magazine_pouch_quantity'),
                    ('Rifle Sling',           'rifle_sling_quantity'),
                    ('Bandoleer',             'bandoleer_quantity'),
                ]:
                    _cur.execute(  # noqa: S608
                        f'UPDATE "{_acc_tbl}" '
                        f'SET quantity = GREATEST(0, quantity + CAST(('
                        f'  SELECT'
                        f'    COALESCE(SUM(CASE WHEN transaction_type=\'Withdrawal\' THEN {_qty_col} ELSE 0 END), 0)'
                        f'  - COALESCE(SUM(CASE WHEN transaction_type=\'Return\'    THEN {_qty_col} ELSE 0 END), 0)'
                        f'  FROM "{_txn_tbl}"'
                        f'  WHERE {_qty_col} IS NOT NULL'
                        f') AS INTEGER)) '
                        f'WHERE id = ('
                        f'  SELECT id FROM "{_acc_tbl}" WHERE type = %s ORDER BY quantity DESC LIMIT 1'
                        f')',
                        [_acc_type],
                    )

                deleted_summary.append('Inventory pool quantities restored (net of all withdrawals minus returns)')

            # ── Step 2: Delete selected tables ───────────────────────────────────
            for key, (label, table) in targets.items():
                if request.POST.get(f'truncate_{key}'):
                    _cur.execute(f'DELETE FROM "{table}"')  # noqa: S608 — table name from trusted model meta
                    deleted_summary.append(f'{label}: {_cur.rowcount} row(s) deleted')
                    if key in ('transaction_logs', 'transactions'):
                        _clear_personnel = True

            # Clear all transaction-derived fields from Personnel rows so they don't
            # show stale issued/assigned data after the transaction history is wiped.
            if _clear_personnel:
                _p_table = Personnel._meta.db_table
                _set_clause = ', '.join(f'"{col}" = NULL' for col in _PERSONNEL_CLEAR_COLS)
                _cur.execute(f'UPDATE "{_p_table}" SET {_set_clause}')  # noqa: S608
                deleted_summary.append(f'Personnel fields cleared: {_cur.rowcount} record(s) reset')

                # Reset Rifle and Pistol item_status back to 'Available' and clear
                # issued tracking (item_issued_to_id, item_issued_timestamp, item_issued_by).
                for _inv_model in (Rifle, Pistol):
                    _inv_table = _inv_model._meta.db_table
                    _cur.execute(
                        f'UPDATE "{_inv_table}" SET '  # noqa: S608
                        f'"item_status" = \'Available\', '
                        f'"item_issued_to_id" = NULL, '
                        f'"item_issued_timestamp" = NULL, '
                        f'"item_issued_by" = NULL '
                        f'WHERE "item_status" = \'Issued\''
                    )
                    _label = _inv_model.__name__
                    deleted_summary.append(f'{_label} items reset to Available: {_cur.rowcount} item(s)')

        if deleted_summary:
            detail = ' | '.join(deleted_summary)
            AuditLog.objects.create(
                user=request.user,
                action='DELETE',
                model_name='DataTruncation',
                object_pk='—',
                message=f'Manual data truncation by {request.user.username}: {detail}',
                ip_address=_get_client_ip(request),
                user_agent=_get_user_agent(request),
            )
            # Write directly to ActivityLog as a guaranteed failsafe — the
            # middleware normally handles this, but the raw-SQL bulk delete above
            # can leave the DB connection in an unexpected state, causing the
            # middleware's _safe_record() to silently drop the entry.
            from armguard.apps.users.models import ActivityLog
            ActivityLog.objects.create(
                user=request.user,
                ip_address=_get_client_ip(request),
                user_agent=_get_user_agent(request),
                method='POST',
                path=request.path_info,
                view_name='settings-truncate',
                flag='NORMAL',
                status_code=302,
                response_ms=0,
            )
            messages.success(request, f'Truncation complete. {detail}.')
        else:
            messages.warning(request, 'No tables were selected.')
    except Exception as _exc:
        _logger.error('Data truncation failed: %s', _exc, exc_info=True)
        messages.error(
            request,
            f'Truncation failed ({type(_exc).__name__}). No data was changed. '
            f'Check server logs for details.',
        )

    return redirect('system-settings')


@login_required
@require_POST
def simulate_orex_run(request):
    """
    Start an OREX withdrawal simulation in a background thread and return
    to the dashboard immediately.  The thread writes progress and results
    to a SimulationRun record so the dashboard widget can poll for status.
    Superuser-only.
    """
    if not request.user.is_superuser:
        messages.error(request, 'Only superusers can run the OREX simulation.')
        return redirect('system-settings')

    try:
        count    = max(1, min(int(request.POST.get('sim_count', 114)), 500))
        operator = (request.POST.get('sim_operator', '').strip() or request.user.username)[:150]
        commit   = request.POST.get('sim_commit') == '1'
        delay    = max(0, min(int(request.POST.get('sim_delay', 5)), 60))
    except (ValueError, TypeError):
        messages.error(request, 'Invalid simulation parameters.')
        return redirect('system-settings')

    from armguard.apps.users.models import SimulationRun
    import threading

    # Block a new run if one is already in progress
    if SimulationRun.objects.filter(status__in=['queued', 'running']).exists():
        messages.warning(request, 'A simulation is already in progress. Check the Dashboard for status.')
        return redirect('dashboard')

    run = SimulationRun.objects.create(
        operator=operator,
        commit=commit,
        sim_count=count,
        delay_seconds=delay,
        started_by=request.user,
    )

    t = threading.Thread(
        target=_run_orex_background,
        args=(str(run.run_id), request.user.pk),
        daemon=False,  # non-daemon: worker process won't exit until simulation finishes
    )
    t.start()

    mode = 'COMMIT' if commit else 'DRY-RUN'
    messages.info(
        request,
        f'OREX simulation started [{mode}] — {count} personnel, {delay}s/transaction. '
        f'Check the Dashboard for live progress.',
    )
    return redirect('dashboard')


def _run_orex_background(run_id, user_pk):
    """
    Background thread: runs the OREX simulation with per-transaction delay,
    writes progress back to SimulationRun, then marks it completed/error.
    DB connection is closed when the thread exits (thread-local connection).
    """
    from armguard.apps.users.models import SimulationRun, ActivityLog, AuditLog
    from armguard.apps.personnel.models import Personnel
    from armguard.apps.inventory.models import Rifle, FirearmDiscrepancy
    from armguard.apps.transactions.models import Transaction
    from django.contrib.auth import get_user_model
    from django.core.exceptions import ValidationError
    from django.utils import timezone
    from django.db import connection as _db_conn
    import datetime
    import time as _time

    try:
        run = SimulationRun.objects.get(run_id=run_id)
        run.status = SimulationRun.STATUS_RUNNING
        run.save(update_fields=['status'])

        User = get_user_model()
        try:
            user = User.objects.get(pk=user_pk)
        except User.DoesNotExist:
            user = None

        count     = run.sim_count
        operator  = run.operator
        commit    = run.commit
        delay_s   = run.delay_seconds

        personnel_list = list(
            Personnel.objects
            .filter(status='Active', rifle_item_issued__isnull=True)
            .order_by('Personnel_ID')[:count]
        )
        discrepant_ids = set(
            FirearmDiscrepancy.objects
            .filter(rifle__isnull=False, status='Open')
            .values_list('rifle_id', flat=True)
        )
        available_rifles = list(
            Rifle.objects
            .filter(item_status='Available')
            .exclude(item_id__in=discrepant_ids)
            .order_by('item_number')
        )

        if not personnel_list or not available_rifles:
            SimulationRun.objects.filter(run_id=run_id).update(
                status=SimulationRun.STATUS_ERROR,
                error_message='No Active personnel without a rifle, or no Available rifles.',
                completed_at=timezone.now(),
            )
            return

        # ── OREX loadout from SystemSettings ──────────────────────────────────
        from armguard.apps.users.models import SystemSettings
        from armguard.apps.inventory.models import Magazine as _Magazine

        ss = SystemSettings.get()

        # Magazine pool selection is now done per-transaction inside the loop
        # because different rifle models require different magazine calibers:
        #   M14 Rifle 7.62mm     → 'M14' capacity (Mag Assy, 7.62mm: M14)
        #   M4 14.5" DGIS EMTAN  → 'EMTAN' type   (Mag Assy, 5.56mm: EMTAN)
        #   All other 5.56mm     → '20-rounds' or '30-rounds' alloy pool
        # Pre-cache pool objects keyed by capacity to avoid N queries per pair.
        from armguard.apps.inventory.models import MAG_WEAPON_COMPATIBILITY as _MAG_COMPAT
        _mag_pool_cache = {}

        def _get_orex_mag_pool(rifle_model):
            """Return the best available magazine pool for the given rifle model."""
            allowed_types = [t for t, ms in _MAG_COMPAT.items() if rifle_model in ms]
            if not allowed_types:
                return None
            pool = (
                _Magazine.objects
                .filter(weapon_type='Rifle', type__in=allowed_types, quantity__gt=0)
                .order_by('-quantity')
                .first()
            )
            return pool

        _rifle_mag_qty = 1  # OREX standard: 1 magazine per rifle

        _rifle_sling_qty = ss.orex_rifle_sling_qty if ss.orex_rifle_sling_qty else None
        _bandoleer_qty   = ss.orex_bandoleer_qty   if ss.orex_bandoleer_qty   else None

        pairs      = list(zip(personnel_list, available_rifles))
        _pairs_needed = len(pairs)

        # Pre-flight: if accessory pools don't have enough stock for all pairs,
        # skip those accessories to avoid mid-run failures.
        from armguard.apps.inventory.models import Accessory as _Accessory
        if _rifle_sling_qty:
            _sling_pool = _Accessory.objects.filter(type='Rifle Sling').order_by('-quantity').first()
            if not _sling_pool or _sling_pool.quantity < _pairs_needed * _rifle_sling_qty:
                _rifle_sling_qty = None  # not enough stock — skip slings
        if _bandoleer_qty:
            _bando_pool = _Accessory.objects.filter(type='Bandoleer').order_by('-quantity').first()
            if not _bando_pool or _bando_pool.quantity < _pairs_needed * _bandoleer_qty:
                _bandoleer_qty = None  # not enough stock — skip bandoleers
        skip_count = len(personnel_list) - len(pairs)
        ok_count   = 0
        err_count  = 0
        results    = []
        return_by  = timezone.now() + datetime.timedelta(hours=24)
        wall_start = _time.perf_counter()

        SimulationRun.objects.filter(run_id=run_id).update(
            total=len(pairs) + skip_count,
            skip_count=skip_count,
        )

        for idx, (person, rifle) in enumerate(pairs, start=1):
            person_name = f'{person.rank or ""} {person.first_name} {person.last_name}'.strip()
            # Select magazine pool caliber-matched to this specific rifle model.
            _rifle_model = getattr(rifle, 'model', '')
            _rifle_mag_pool = _mag_pool_cache.get(_rifle_model)
            if _rifle_mag_pool is None:
                _rifle_mag_pool = _get_orex_mag_pool(_rifle_model)
                # Cache even None so we don't re-query for same model that has no stock.
                _mag_pool_cache[_rifle_model] = _rifle_mag_pool
            txn = Transaction(
                transaction_type='Withdrawal',
                issuance_type='TR (Temporary Receipt)',
                purpose='OREX',
                personnel=person,
                rifle=rifle,
                transaction_personnel=operator,
                return_by=return_by,
                rifle_magazine=_rifle_mag_pool,
                rifle_magazine_quantity=_rifle_mag_qty if _rifle_mag_pool else None,
                rifle_sling_quantity=_rifle_sling_qty,
                bandoleer_quantity=_bandoleer_qty,
            )
            try:
                txn.full_clean()
            except ValidationError as exc:
                err_count += 1
                note = '; '.join(
                    m for msgs in exc.message_dict.values() for m in msgs
                ) if hasattr(exc, 'message_dict') else str(exc)
                results.append([idx, person.Personnel_ID, person_name, rifle.item_id, 'error', note])
            else:
                if commit:
                    _saved = False
                    _save_exc = None
                    for _attempt in range(4):  # up to 4 attempts with backoff
                        try:
                            txn.save(user=user)
                            _saved = True
                            break
                        except Exception as _exc:
                            _save_exc = _exc
                            if 'database is locked' in str(_exc).lower() and _attempt < 3:
                                _time.sleep(2 ** _attempt)  # 1s, 2s, 4s
                                continue
                            break
                    if _saved:
                        ok_count += 1
                        results.append([idx, person.Personnel_ID, person_name, rifle.item_id, 'saved', ''])
                    else:
                        err_count += 1
                        results.append([idx, person.Personnel_ID, person_name, rifle.item_id, 'error', str(_save_exc)[:120]])
                else:
                    ok_count += 1
                    results.append([idx, person.Personnel_ID, person_name, rifle.item_id, 'dry-ok', ''])

            # Atomic progress update — other readers see this while thread runs
            SimulationRun.objects.filter(run_id=run_id).update(
                progress=idx,
                ok_count=ok_count,
                err_count=err_count,
            )

            if delay_s > 0:
                _time.sleep(delay_s)

        wall_time  = _time.perf_counter() - wall_start
        mode_label = 'COMMIT' if commit else 'DRY-RUN'

        # Write audit logs
        if user:
            ActivityLog.objects.create(
                user=user,
                ip_address=None,
                user_agent='SimulationThread/background',
                method='POST',
                path='/users/settings/simulate-orex/',
                view_name='settings-simulate-orex',
                flag='NORMAL',
                status_code=200,
                response_ms=int(wall_time * 1000),
            )
            AuditLog.objects.create(
                user=user,
                action='OTHER',
                model_name='Transaction',
                object_pk='—',
                message=(
                    f'OREX simulation [{mode_label}] by {operator}: '
                    f'{ok_count} ok, {err_count} error(s), {skip_count} skipped '
                    f'out of {len(pairs) + skip_count} personnel in {wall_time:.1f}s '
                    f'({delay_s}s/transaction)'
                ),
                ip_address=None,
                user_agent='SimulationThread/background',
            )

        SimulationRun.objects.filter(run_id=run_id).update(
            status=SimulationRun.STATUS_COMPLETED,
            ok_count=ok_count,
            err_count=err_count,
            wall_time=round(wall_time, 2),
            results_json=results,
            completed_at=timezone.now(),
        )

    except Exception as exc:
        try:
            from django.utils import timezone as _tz
            SimulationRun.objects.filter(run_id=run_id).update(
                status='error',
                error_message=str(exc)[:500],
                completed_at=_tz.now(),
            )
        except Exception:
            pass
    finally:
        _db_conn.close()


@login_required
def simulate_orex_status_json(request):
    """Return status of the most recent SimulationRun as JSON. Superuser only."""
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    from armguard.apps.users.models import SimulationRun
    from django.utils import timezone as _tz
    import datetime

    # Auto-expire runs stuck in queued/running for > 30 minutes
    stale_cutoff = _tz.now() - datetime.timedelta(minutes=30)
    SimulationRun.objects.filter(
        status__in=['queued', 'running'],
        started_at__lt=stale_cutoff,
    ).update(
        status='error',
        error_message='Run expired — no progress in 30 minutes (server may have restarted).',
        completed_at=_tz.now(),
    )

    run = SimulationRun.objects.first()
    if not run:
        return JsonResponse({'status': 'none'})

    pct = round(run.progress / run.total * 100) if run.total > 0 else 0
    return JsonResponse({
        'status':        run.status,
        'run_id':        str(run.run_id),
        'operator':      run.operator,
        'commit':        run.commit,
        'sim_count':     run.sim_count,
        'delay_seconds': run.delay_seconds,
        'ok_count':      run.ok_count,
        'err_count':     run.err_count,
        'skip_count':    run.skip_count,
        'total':         run.total,
        'progress':      run.progress,
        'pct':           pct,
        'wall_time':     run.wall_time,
        'error_message': run.error_message,
        'started_at':    run.started_at.isoformat(),
        'completed_at':  run.completed_at.isoformat() if run.completed_at else None,
    })


@login_required
@require_POST
def simulate_orex_reset(request):
    """Force-cancel a stuck queued/running SimulationRun. Superuser only."""
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    from armguard.apps.users.models import SimulationRun
    from django.utils import timezone as _tz

    run_id = request.POST.get('run_id', '').strip()
    qs = SimulationRun.objects.filter(status__in=['queued', 'running'])
    if run_id:
        qs = qs.filter(run_id=run_id)

    updated = qs.update(
        status='error',
        error_message=f'Manually reset by {request.user.username}.',
        completed_at=_tz.now(),
    )
    if updated:
        messages.success(request, f'Simulation run reset ({updated} record(s) cleared).')
    else:
        messages.warning(request, 'No active simulation run found to reset.')
    return redirect('dashboard')


@login_required
def simulate_orex_results(request, run_id):
    """Show the per-row results table for a completed SimulationRun. Superuser only."""
    if not request.user.is_superuser:
        messages.error(request, 'Only superusers can view simulation results.')
        return redirect('dashboard')

    from armguard.apps.users.models import SimulationRun
    run = get_object_or_404(SimulationRun, run_id=run_id)

    return render(request, 'users/sim_orex_results.html', {
        'run':        run,
        'results':    run.results_json,
        'ok_count':   run.ok_count,
        'err_count':  run.err_count,
        'skip_count': run.skip_count,
        'total':      run.total,
        'wall_time':  run.wall_time,
        'commit':     run.commit,
        'operator':   run.operator,
    })



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


@require_POST
def cleanup_orphaned_personnel_media(request):
    """Delete personnel media files on disk that have no matching Personnel record."""
    if not _is_admin(request.user):
        return JsonResponse({'error': 'Forbidden'}, status=403)

    media_root = str(django_settings.MEDIA_ROOT)
    existing_ids = set(Personnel.objects.values_list('Personnel_ID', flat=True))

    removed = []

    # ── Personnel images  ( IMG_<last>_<ID>.jpeg ) ────────────────────────────
    img_dir = os.path.join(media_root, 'personnel_images')
    if os.path.isdir(img_dir):
        for entry in os.scandir(img_dir):
            if not entry.is_file():
                continue
            # filename is IMG_<LastName>_<PersonnelID>.jpeg
            name = entry.name
            # extract ID: last segment before extension after last underscore
            stem = os.path.splitext(name)[0]          # e.g. IMG_SMITH_PAF-001
            parts = stem.split('_')
            pid = parts[-1] if len(parts) >= 2 else None
            if pid and pid not in existing_ids:
                try:
                    os.remove(entry.path)
                    removed.append(f'personnel_images/{name}')
                except OSError:
                    pass

    # ── QR images  ( <ID>_qr.png or <ID>.png ) ───────────────────────────────
    qr_dir = os.path.join(media_root, 'qr_code_images_personnel')
    if os.path.isdir(qr_dir):
        for entry in os.scandir(qr_dir):
            if not entry.is_file():
                continue
            stem = os.path.splitext(entry.name)[0]
            # strip common suffixes to recover the Personnel_ID
            pid = stem.replace('_qr', '')
            if pid not in existing_ids:
                try:
                    os.remove(entry.path)
                    removed.append(f'qr_code_images_personnel/{entry.name}')
                except OSError:
                    pass

    # ── ID cards  ( <ID>.png / <ID>_front.png / <ID>_back.png ) ─────────────
    card_dir = os.path.join(media_root, 'personnel_id_cards')
    if os.path.isdir(card_dir):
        for entry in os.scandir(card_dir):
            if not entry.is_file():
                continue
            stem = os.path.splitext(entry.name)[0]    # e.g. PAF-001_front
            # strip _front / _back suffix to get the ID
            pid = stem.replace('_front', '').replace('_back', '')
            # skip preview files (named preview_<hex>)
            if stem.startswith('preview_'):
                continue
            if pid not in existing_ids:
                try:
                    os.remove(entry.path)
                    removed.append(f'personnel_id_cards/{entry.name}')
                except OSError:
                    pass

    return JsonResponse({'removed': len(removed), 'files': removed})
