import json

from django.contrib.auth import get_user_model, logout
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib import messages
from django.views.generic import ListView, CreateView, UpdateView
from django.urls import reverse_lazy
from django.views import View
from django import forms
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from .models import UserProfile, ROLE_CHOICES, PasswordHistory
from armguard.apps.personnel.models import Personnel
# H1 FIX: Import shared permission helper instead of duplicating it here.
from armguard.utils.permissions import is_admin as _is_admin


@require_POST
def logout_view(request):
    logout(request)
    return redirect('login')


User = get_user_model()


def _personnel_map_json(qs):
    """Return a JSON string mapping pk -> {first, last, pid} for auto-fill."""
    return json.dumps({
        str(p['pk']): {'first': p['first_name'], 'last': p['last_name'], 'pid': p['Personnel_ID']}
        for p in qs.values('pk', 'first_name', 'last_name', 'Personnel_ID')
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
    role        = forms.ChoiceField(choices=ROLE_CHOICES)
    is_staff    = forms.BooleanField(required=False, label='Staff (Django admin access)')
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
        return _is_admin(self.request.user)


class UserCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    template_name = 'users/user_form.html'
    success_url   = reverse_lazy('user-list')

    def test_func(self):
        return _is_admin(self.request.user)

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
        return _is_admin(self.request.user)

    def _make_form(self, data=None):
        user = self.object
        current_role = getattr(getattr(user, 'profile', None), 'role', 'Armorer')
        current_linked = getattr(user, 'personnel', None)  # reverse OneToOne
        current_linked_pk = current_linked.Personnel_ID if current_linked else None
        initial = {
            'first_name':        user.first_name,
            'last_name':         user.last_name,
            'email':             user.email,
            'is_staff':          user.is_staff,
            'is_active':         user.is_active,
            'role':              current_role,
            'linked_personnel':  current_linked_pk,
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
        return _is_admin(self.request.user)

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


