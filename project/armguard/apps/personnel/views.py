from django.urls import reverse_lazy
from django.shortcuts import redirect
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
	paginate_by = 30
	ordering = ['rank', 'last_name']

	def get_queryset(self):
		from django.db.models import Q
		qs = Personnel.objects.order_by('rank', 'last_name')
		q = self.request.GET.get('q', '').strip()
		status = self.request.GET.get('status', '').strip()
		group = self.request.GET.get('group', '').strip()
		if q:
			qs = qs.filter(
				Q(first_name__icontains=q) | Q(last_name__icontains=q) |
				Q(Personnel_ID__icontains=q) | Q(AFSN__icontains=q)
			)
		if status:
			qs = qs.filter(status=status)
		if group:
			qs = qs.filter(group=group)
		return qs

	def get_context_data(self, **kwargs):
		ctx = super().get_context_data(**kwargs)
		ctx['groups'] = Personnel.objects.values_list('group', flat=True).distinct().exclude(group__isnull=True).exclude(group='')
		return ctx

	def test_func(self):
		user = self.request.user
		if user.is_superuser or user.is_staff:
			return True
		try:
			return user.profile.role in ('System Administrator', 'Administrator', 'Armorer')
		except AttributeError:
			return False

class PersonnelDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
	model = Personnel
	template_name = "personnel/detail.html"
	context_object_name = "personnel"

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		personnel = self.object
		context["display_str"] = f"{personnel.rank} {personnel.first_name} {personnel.middle_initial} {personnel.last_name} {personnel.AFSN} PAF<br>Personnel ID: {personnel.Personnel_ID}"
		from armguard.apps.transactions.models import Transaction
		context["recent_transactions"] = Transaction.objects.filter(
			personnel=personnel
		).order_by('-timestamp')[:10]
		# ID card PNGs
		import os
		from django.conf import settings
		pid = personnel.Personnel_ID
		card_dir = os.path.join(settings.MEDIA_ROOT, 'personnel_id_cards')
		front_file = os.path.join(card_dir, f"{pid}_front.png")
		back_file  = os.path.join(card_dir, f"{pid}_back.png")
		context['id_card_front_url'] = (
			f"{settings.MEDIA_URL}personnel_id_cards/{pid}_front.png"
			if os.path.exists(front_file) else None
		)
		context['id_card_back_url'] = (
			f"{settings.MEDIA_URL}personnel_id_cards/{pid}_back.png"
			if os.path.exists(back_file) else None
		)
		# Assigned & issued weapons
		context['assigned_pistols'] = personnel.pistols_assigned.all()
		context['assigned_rifles']  = personnel.rifles_assigned.all()
		context['issued_pistols']   = personnel.pistols_issued.all()
		context['issued_rifles']    = personnel.rifles_issued.all()
		return context

	def test_func(self):
		user = self.request.user
		if user.is_superuser or user.is_staff:
			return True
		try:
			return user.profile.role in ('System Administrator', 'Administrator', 'Armorer')
		except AttributeError:
			return False

class PersonnelCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
	model = Personnel
	form_class = PersonnelForm
	template_name = "personnel/personnel_form.html"

	def test_func(self):
		return _can_manage_personnel(self.request.user)

	def form_valid(self, form):
		obj = form.save(commit=False)
		# Stamp audit fields — mirrors admin save_model()
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
		return _can_manage_personnel(self.request.user)

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		import os
		from django.conf import settings
		pid = self.object.Personnel_ID
		card_dir = os.path.join(settings.MEDIA_ROOT, 'personnel_id_cards')
		front_file = os.path.join(card_dir, f"{pid}_front.png")
		back_file  = os.path.join(card_dir, f"{pid}_back.png")
		context['id_card_front_url'] = (
			f"{settings.MEDIA_URL}personnel_id_cards/{pid}_front.png"
			if os.path.exists(front_file) else None
		)
		context['id_card_back_url'] = (
			f"{settings.MEDIA_URL}personnel_id_cards/{pid}_back.png"
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

		# Show QR only when all key identity fields are filled and a real ID is simulated
		fields_complete = all([
			p.rank, p.first_name, p.last_name, p.AFSN,
			p.Personnel_ID != 'PREVIEW',
		])
		try:
			from utils.personnel_id_card_generator import _build_front, _build_back
			img = _build_front(p) if face == 'front' else _build_back(p, skip_qr=not fields_complete)
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
		return _can_manage_personnel(self.request.user)
