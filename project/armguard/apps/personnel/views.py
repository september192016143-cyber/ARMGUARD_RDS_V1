from django.urls import reverse_lazy
from django.shortcuts import redirect, render, get_object_or_404
from django.views import View
from django.views.generic import (
	ListView, DetailView, CreateView, UpdateView, DeleteView
)
from .models import Personnel
from django.contrib.auth.mixins import UserPassesTestMixin, LoginRequiredMixin
from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
import logging
from django.contrib import messages
from armguard.utils.permissions import can_delete as _can_delete_personnel, can_add as _can_add_personnel, can_edit as _can_edit_personnel, can_manage_inventory as _can_manage_inventory

logger = logging.getLogger(__name__)

# ── Preview Personnel_ID simulation (mirrors Personnel.save() logic) ──────────
_RANKS_ENLISTED = {'AM','AW','A2C','AW2C','A1C','AW1C','SGT','SSGT','TSGT','MSGT','SMSGT','CMSGT'}
_RANKS_OFFICER  = {'2LT','1LT','CPT','MAJ','LTCOL','COL','BGEN','MGEN','LTGEN','GEN'}

def _simulate_personnel_id(rank: str, afsn: str) -> str | None:
	"""Return a simulated Personnel_ID identical in format to what the model generates.
	Returns None if rank or AFSN is empty (preview not ready yet)."""
	if not rank or not afsn:
		return None
	from django.utils import timezone
	dt   = timezone.now()
	suffix = dt.strftime('%H%d%M%m%y')
	if rank in _RANKS_ENLISTED:
		return f"PEP-{afsn}-{suffix}"
	elif rank in _RANKS_OFFICER:
		afsn_val = afsn if afsn.startswith('O-') else f"O-{afsn}"
		return f"POF_{afsn_val}-{suffix}"
	else:
		return f"P{afsn}-{suffix}"

def _can_manage_personnel(user):
	"""True for superusers, staff, and named management roles (NOT Armorer)."""
	if user.is_superuser or user.is_staff:
		return True
	try:
		return user.profile.role in ('System Administrator', 'Administrator')
	except AttributeError:
		return False

# ModelForm for Personnel
class PersonnelForm(forms.ModelForm):
	# tel is blank=True/null=True in the model — optional in the form so records
	# can be created before a phone number is known. Validator fires when provided.
	tel = forms.CharField(
		max_length=11,
		required=False,
		validators=[RegexValidator(r'^\d+$', 'Enter numbers only.')],
		help_text="Contact telephone number (digits only, max 11 characters). Required for TR issuance.",
	)

	class Meta:
		model = Personnel
		fields = [
			"rank", "first_name", "middle_initial", "last_name", "AFSN",
			"group", "squadron", "tel", "personnel_image", "status",
			# "user" intentionally excluded — user-account linking is admin-only
		]

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		# Mark all non-file/image fields as required; leave ImageField optional
		for name, field in self.fields.items():
			if not isinstance(field, (forms.ImageField, forms.FileField)):
				field.required = True
		# tel is explicitly optional — override the loop above
		self.fields['tel'].required = False
		self.fields['personnel_image'].required = False

	def clean_tel(self):
		"""Convert empty string to None to avoid unique=True collisions on blank tel."""
		val = self.cleaned_data.get('tel', '').strip()
		return val if val else None

class PersonnelListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
	model = Personnel
	template_name = "personnel/personnel_list.html"
	context_object_name = "personnel_list"
	paginate_by = 10
	ordering = ['rank', 'last_name']

	def get_queryset(self):
		from django.db.models import Q
		qs = Personnel.objects.order_by('rank', 'last_name')
		q = self.request.GET.get('q', '').strip()
		category = self.request.GET.get('category', '').strip()
		group = self.request.GET.get('group', '').strip()
		if q:
			qs = qs.filter(
				Q(first_name__icontains=q) | Q(last_name__icontains=q) |
				Q(Personnel_ID__icontains=q) | Q(AFSN__icontains=q)
			)
		if category == 'Officer':
			qs = qs.filter(rank__in=_RANKS_OFFICER)
		elif category == 'Enlisted':
			qs = qs.filter(rank__in=_RANKS_ENLISTED)
		if group:
			qs = qs.filter(group=group)
		return qs

	def render_to_response(self, context, **response_kwargs):
		if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
			return render(self.request, 'personnel/personnel_rows.html', context)
		return super().render_to_response(context, **response_kwargs)

	def get_context_data(self, **kwargs):
		ctx = super().get_context_data(**kwargs)
		ctx['groups'] = Personnel.objects.values_list('group', flat=True).distinct().exclude(group__isnull=True).exclude(group='')
		ctx['can_add'] = _can_add_personnel(self.request.user)
		ctx['can_edit'] = _can_edit_personnel(self.request.user)
		return ctx

	def test_func(self):
		return _can_manage_inventory(self.request.user)

class PersonnelDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
	model = Personnel
	template_name = "personnel/detail.html"
	context_object_name = "personnel"

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		personnel = self.object
		context["display_str"] = f"{personnel.rank} {personnel.first_name} {personnel.middle_initial} {personnel.last_name} {personnel.AFSN} PAF<br>Personnel ID: {personnel.Personnel_ID}"
		from armguard.apps.transactions.models import Transaction
		context["recent_transactions"] = (
			Transaction.objects
			.filter(personnel=personnel)
			.select_related('personnel', 'pistol', 'rifle')
			.order_by('-timestamp')[:10]
		)
		# ID card PNGs
		import os
		from django.conf import settings
		pid = personnel.Personnel_ID
		card_dir = os.path.join(settings.MEDIA_ROOT, 'personnel_id_cards')
		front_file = os.path.join(card_dir, f"{pid}_front.png")
		back_file  = os.path.join(card_dir, f"{pid}_back.png")
		context['id_card_front_url'] = (
			f"{settings.MEDIA_URL}personnel_id_cards/{pid}_front.png?v={int(os.path.getmtime(front_file))}"
			if os.path.exists(front_file) else None
		)
		context['id_card_back_url'] = (
			f"{settings.MEDIA_URL}personnel_id_cards/{pid}_back.png?v={int(os.path.getmtime(back_file))}"
			if os.path.exists(back_file) else None
		)
		# Assigned & issued weapons
		context['assigned_pistols'] = personnel.pistols_assigned.all()
		context['assigned_rifles']  = personnel.rifles_assigned.all()
		context['issued_pistols']   = personnel.pistols_issued.all()
		context['issued_rifles']    = personnel.rifles_issued.all()
		context['can_edit'] = _can_edit_personnel(self.request.user)
		return context

	def test_func(self):
		return _can_manage_inventory(self.request.user)

class PersonnelCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
	model = Personnel
	form_class = PersonnelForm
	template_name = "personnel/personnel_form.html"

	def test_func(self):
		return _can_add_personnel(self.request.user)

	def form_valid(self, form):
		obj = form.save(commit=False)
		obj.created_by = self.request.user.username
		obj.updated_by = self.request.user.username
		# Run model-level clean() so AFSN rules & issued-item validation fire
		try:
			obj.full_clean(exclude=['Personnel_ID', 'qr_code', 'qr_code_image'])
		except ValidationError as e:
			form.add_error(None, e)
			return self.form_invalid(form)
		obj.save()
		try:
			from utils.personnel_id_card_generator import generate_personnel_id_card
			generate_personnel_id_card(obj)
		except Exception as exc:
			logger.warning("ID card generation failed for %s: %s", obj.Personnel_ID, exc)
		messages.success(self.request, f"Personnel '{obj}' registered successfully.")
		# Redirect to edit so the flip card preview shows the generated PNG
		return redirect('personnel-update', pk=obj.Personnel_ID)

class PersonnelUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
	model = Personnel
	form_class = PersonnelForm
	template_name = "personnel/personnel_form.html"

	def test_func(self):
		return _can_edit_personnel(self.request.user)

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		import os
		from django.conf import settings
		pid = self.object.Personnel_ID
		card_dir = os.path.join(settings.MEDIA_ROOT, 'personnel_id_cards')
		front_file = os.path.join(card_dir, f"{pid}_front.png")
		back_file  = os.path.join(card_dir, f"{pid}_back.png")
		context['id_card_front_url'] = (
			f"{settings.MEDIA_URL}personnel_id_cards/{pid}_front.png?v={int(os.path.getmtime(front_file))}"
			if os.path.exists(front_file) else None
		)
		context['id_card_back_url'] = (
			f"{settings.MEDIA_URL}personnel_id_cards/{pid}_back.png?v={int(os.path.getmtime(back_file))}"
			if os.path.exists(back_file) else None
		)
		return context

	def form_valid(self, form):
		obj = form.save(commit=False)
		# Stamp audit field on every edit
		obj.updated_by = self.request.user.username
		# Run model-level clean() so AFSN rules & issued-item validation fire
		try:
			obj.full_clean(exclude=['Personnel_ID', 'qr_code', 'qr_code_image'])
		except ValidationError as e:
			form.add_error(None, e)
			return self.form_invalid(form)
		obj.save()
		try:
			from utils.personnel_id_card_generator import generate_personnel_id_card
			generate_personnel_id_card(obj)
		except Exception as exc:
			logger.warning("ID card generation failed for %s: %s", obj.Personnel_ID, exc)
		messages.success(self.request, f"Personnel '{obj}' updated successfully.")
		# Redirect back to edit so the flip card preview shows the regenerated PNG
		return redirect('personnel-update', pk=obj.Personnel_ID)

class PersonnelCardPreviewView(LoginRequiredMixin, View):
	"""
	POST form fields + optional photo → returns a front or back card PNG.
	Used by the real-time flip-card preview on the create/edit form.
	"""
	def _render_card(self, request, face='front'):
		import io, uuid, os
		from django.http import HttpResponse
		from django.conf import settings
		from types import SimpleNamespace

		source = request.POST if request.method == 'POST' else request.GET

		p = SimpleNamespace()
		p.Personnel_ID   = source.get('Personnel_ID') or None
		p.rank           = source.get('rank', '')
		p.first_name     = source.get('first_name', '')
		p.middle_initial = source.get('middle_initial', '')
		p.last_name      = source.get('last_name', '')
		p.AFSN           = source.get('AFSN', '')
		p.group          = source.get('group', '')
		p.squadron       = source.get('squadron', '')
		p.tel            = source.get('tel', '')

		# If Personnel_ID not posted (create form), simulate it from rank + AFSN
		if not p.Personnel_ID:
			p.Personnel_ID = _simulate_personnel_id(p.rank, p.AFSN) or 'PREVIEW'

		p.qr_code        = p.Personnel_ID
		p.qr_code_image  = None
		p.personnel_image = None

		tmp_rel = None
		photo_file = request.FILES.get('personnel_image') if request.method == 'POST' else None
		if not photo_file:
			# Edit form: no new upload — use the existing saved photo path
			existing = source.get('existing_personnel_image', '').strip()
			if existing:
				p.personnel_image = existing
		if photo_file:
			ext = os.path.splitext(photo_file.name)[1] or '.jpg'
			tmp_rel = f"personnel_id_cards/preview_{uuid.uuid4().hex[:12]}{ext}"
			tmp_abs = os.path.join(settings.MEDIA_ROOT, tmp_rel)
			os.makedirs(os.path.dirname(tmp_abs), exist_ok=True)
			with open(tmp_abs, 'wb') as fh:
				for chunk in photo_file.chunks():
					fh.write(chunk)
			p.personnel_image = tmp_rel

		# Show QR as soon as we have a real simulated ID (rank + AFSN are enough)
		skip_qr = (not p.Personnel_ID or p.Personnel_ID == 'PREVIEW')
		try:
			from utils.personnel_id_card_generator import _build_front, _build_back
			img = _build_front(p) if face == 'front' else _build_back(p, skip_qr=skip_qr)
			buf = io.BytesIO()
			img.save(buf, 'PNG')
			buf.seek(0)
			return HttpResponse(buf.read(), content_type='image/png')
		except Exception as exc:
			logger.warning("Card preview error (%s): %s", face, exc)
			return HttpResponse(status=500)
		finally:
			if tmp_rel:
				try:
					os.unlink(os.path.join(settings.MEDIA_ROOT, tmp_rel))
				except OSError:
					pass

	def get(self, request, *args, **kwargs):
		return self._render_card(request, face=request.GET.get('face', 'front'))

	def post(self, request, *args, **kwargs):
		return self._render_card(request, face=request.POST.get('face', 'front'))


class PersonnelDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
	model = Personnel
	template_name = "personnel/personnel_confirm_delete.html"
	success_url = reverse_lazy("personnel-list")

	def test_func(self):
		return _can_delete_personnel(self.request.user)


class AssignWeaponView(LoginRequiredMixin, UserPassesTestMixin, View):
	template_name = 'personnel/assign_weapon.html'

	def test_func(self):
		return _can_manage_personnel(self.request.user)

	def get(self, request, pk):
		from armguard.apps.inventory.models import Pistol, Rifle
		personnel = get_object_or_404(Personnel, pk=pk)
		current_pistols = list(personnel.pistols_assigned.all())
		current_rifles = list(personnel.rifles_assigned.all())
		pistols = Pistol.objects.exclude(item_status='Decommissioned').select_related('item_assigned_to').order_by('model')
		rifles = Rifle.objects.exclude(item_status='Decommissioned').select_related('item_assigned_to').order_by('model')
		return render(request, self.template_name, {
			'personnel': personnel,
			'pistols': pistols,
			'rifles': rifles,
			'current_pistols': current_pistols,
			'current_rifles': current_rifles,
		})

	def post(self, request, pk):
		from armguard.apps.inventory.models import Pistol, Rifle
		from django.utils import timezone
		personnel = get_object_or_404(Personnel, pk=pk)
		username = request.user.username
		now = timezone.now()

		pistol_id = request.POST.get('pistol')
		rifle_id  = request.POST.get('rifle')

		# ── Validate: block reassignment from another person ──────────────────
		# Fetch the selected items once for validation.
		selected_pistol = None
		selected_rifle  = None
		errors = []

		if pistol_id:
			try:
				selected_pistol = Pistol.objects.select_related('item_assigned_to').get(pk=pistol_id)
				if (selected_pistol.item_assigned_to_id
						and selected_pistol.item_assigned_to_id != personnel.pk):
					other = selected_pistol.item_assigned_to
					errors.append(
						f'Pistol "{selected_pistol.model} — SN: {selected_pistol.serial_number}" '
						f'is already assigned to {other.rank} {other.last_name}. '
						f'Clear it from that personnel first.'
					)
			except Pistol.DoesNotExist:
				pistol_id = None

		if rifle_id:
			try:
				selected_rifle = Rifle.objects.select_related('item_assigned_to').get(pk=rifle_id)
				if (selected_rifle.item_assigned_to_id
						and selected_rifle.item_assigned_to_id != personnel.pk):
					other = selected_rifle.item_assigned_to
					errors.append(
						f'Rifle "{selected_rifle.model} — SN: {selected_rifle.serial_number}" '
						f'is already assigned to {other.rank} {other.last_name}. '
						f'Clear it from that personnel first.'
					)
			except Rifle.DoesNotExist:
				rifle_id = None

		if errors:
			for msg in errors:
				messages.error(request, msg)
			pistols = Pistol.objects.exclude(item_status='Decommissioned').select_related('item_assigned_to').order_by('model')
			rifles  = Rifle.objects.exclude(item_status='Decommissioned').select_related('item_assigned_to').order_by('model')
			return render(request, self.template_name, {
				'personnel': personnel,
				'pistols': pistols,
				'rifles': rifles,
				'current_pistols': list(personnel.pistols_assigned.all()),
				'current_rifles':  list(personnel.rifles_assigned.all()),
			})

		# ── Pistol ────────────────────────────────────────────────────────────
		for p in personnel.pistols_assigned.all():
			p.set_assigned(None, None, None)
		personnel.set_assigned('pistol', None, None, None)

		if selected_pistol:
			selected_pistol.set_assigned(personnel.pk, now, username)
			personnel.set_assigned('pistol', selected_pistol.item_id, now, username)

		# ── Rifle ─────────────────────────────────────────────────────────────
		for r in personnel.rifles_assigned.all():
			r.set_assigned(None, None, None)
		personnel.set_assigned('rifle', None, None, None)

		if selected_rifle:
			selected_rifle.set_assigned(personnel.pk, now, username)
			personnel.set_assigned('rifle', selected_rifle.item_id, now, username)

		messages.success(request, f"Weapon assignments updated for {personnel.rank} {personnel.last_name}.")
		return redirect('personnel-detail', pk=pk)
