from django.urls import reverse_lazy
from django.shortcuts import redirect, render, get_object_or_404
from django.views import View
from django.views.generic import (
	ListView, DetailView, CreateView, UpdateView, DeleteView
)
from .models import Personnel, PersonnelGroup
from django.contrib.auth.mixins import UserPassesTestMixin, LoginRequiredMixin
from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
import logging
from django.contrib import messages
from armguard.utils.permissions import (
    can_view_personnel as _can_view_personnel,
    can_add_personnel  as _can_add_personnel,
    can_edit_personnel as _can_edit_personnel,
    can_delete_personnel as _can_delete_personnel,
)

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

class PersonnelForm(forms.ModelForm):
	# tel is blank=True/null=True in the model — optional in the form so records
	# can be created before a phone number is known. Validator fires when provided.
	tel = forms.CharField(
		max_length=11,
		required=False,
		validators=[RegexValidator(r'^\d+$', 'Enter numbers only.')],
		help_text="Contact telephone number (digits only, max 11 characters). Required for TR issuance.",
	)

	# Declare group explicitly as a plain ChoiceField so Django never locks it
	# to the model's static GROUP_CHOICES. Choices are populated from the DB-backed
	# PersonnelGroup table in __init__, so dynamically added groups are always valid.
	group = forms.ChoiceField(choices=[], required=True)

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
		# Build group choices from DB; fall back to static list if table is empty
		db_choices = PersonnelGroup.get_choices()
		group_choices = db_choices if db_choices else Personnel.GROUP_CHOICES
		self.fields['group'].choices = [('', '---------')] + list(group_choices)

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
		ctx['groups'] = PersonnelGroup.objects.values_list('name', flat=True)
		ctx['can_add'] = _can_add_personnel(self.request.user)
		ctx['can_edit'] = _can_edit_personnel(self.request.user)
		return ctx

	def test_func(self):
		return _can_view_personnel(self.request.user)

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
		return _can_view_personnel(self.request.user)

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
		# Run model-level clean() so AFSN rules & issued-item validation fire.
		# 'group' is excluded because the model field no longer carries choices;
		# form-level validation (DB-backed ChoiceField) is the authority.
		try:
			obj.full_clean(exclude=['Personnel_ID', 'qr_code', 'qr_code_image', 'group'])
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
		# Run model-level clean() so AFSN rules & issued-item validation fire.
		# 'group' is excluded because the model field no longer carries choices;
		# form-level validation (DB-backed ChoiceField) is the authority.
		try:
			obj.full_clean(exclude=['Personnel_ID', 'qr_code', 'qr_code_image', 'group'])
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

class PersonnelCardPreviewView(LoginRequiredMixin, UserPassesTestMixin, View):
	"""
	POST form fields + optional photo → returns a front or back card PNG.
	Used by the real-time flip-card preview on the create/edit form.
	"""
	def test_func(self):
		return _can_view_personnel(self.request.user)


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

# ── Bulk Import helpers ────────────────────────────────────────────────────────

def _extract_drive_file_id(url: str) -> str:
	"""Return the Drive file ID from a share URL, or '' if not found."""
	import re
	m = re.search(r'/d/([a-zA-Z0-9_-]{10,})', url)
	return m.group(1) if m else ''


def _download_drive_photo(file_id: str) -> bytes | None:
	"""Download a publicly-shared Drive file and return its bytes, or None."""
	import urllib.request
	dl_url = f'https://drive.google.com/uc?id={file_id}&export=download'
	try:
		req = urllib.request.Request(dl_url, headers={'User-Agent': 'ArmGuardRDS/1.0'})
		with urllib.request.urlopen(req, timeout=10) as resp:
			data = resp.read()
		# Drive returns an HTML confirm page for large files — detect it
		if data[:5] in (b'<!DOC', b'<html'):
			return None
		return data
	except Exception:
		return None


def _save_personnel_photo(p: 'Personnel', photo_bytes: bytes) -> None:
	"""Write photo_bytes to a media path and set p.personnel_image."""
	import uuid
	rel = f'personnel_id_cards/{p.AFSN}_{uuid.uuid4().hex[:8]}.jpg'
	abs_path = os.path.join(settings.MEDIA_ROOT, rel)
	os.makedirs(os.path.dirname(abs_path), exist_ok=True)
	with open(abs_path, 'wb') as fh:
		fh.write(photo_bytes)
	p.personnel_image = rel


def _import_rows(request, data_rows, group_override='', upsert=False):
	"""
	Process a list of dicts (header keys already normalised to lowercase_underscore).
	Returns (created_count, updated_count, skipped_list).
	data_rows  – list of dicts, one per data row (header row already stripped)
	"""
	valid_ranks  = {r for r, _ in Personnel.ALL_RANKS}
	valid_groups = PersonnelGroup.get_names_set()
	valid_status = {s for s, _ in Personnel.STATUS_CHOICES}

	created_count = 0
	updated_count = 0
	skipped = []

	def g(row, key, default=''):
		return str(row.get(key) or '').strip() or default

	for i, row in enumerate(data_rows, start=2):
		rank           = g(row, 'rank')
		first_name     = g(row, 'first_name')
		last_name      = g(row, 'last_name')
		middle_initial = g(row, 'middle_initial')
		afsn           = g(row, 'afsn')
		group          = group_override or g(row, 'group')
		squadron       = g(row, 'squadron')
		tel            = g(row, 'tel')
		status         = g(row, 'status', 'Active')
		photo_url      = g(row, 'photo')   # optional Drive share link

		if status not in valid_status:
			status = 'Active'

		# ── Validation ────────────────────────────────────────────────────────
		row_errors = []
		if rank not in valid_ranks:
			row_errors.append(f'invalid rank "{rank}"')
		if not first_name:
			row_errors.append('first_name required')
		if not last_name:
			row_errors.append('last_name required')
		if not middle_initial:
			row_errors.append('middle_initial required')
		if not afsn:
			row_errors.append('afsn required')
		if group not in valid_groups:
			row_errors.append(f'invalid group "{group}" (valid: {", ".join(sorted(valid_groups))})')
		if not squadron:
			row_errors.append('squadron required')
		if row_errors:
			skipped.append(f'Row {i}: {"; ".join(row_errors)}')
			continue

		existing = Personnel.objects.filter(AFSN=afsn).first()

		if existing and upsert:
			if tel and Personnel.objects.filter(tel=tel).exclude(pk=existing.pk).exists():
				skipped.append(f'Row {i}: tel {tel} already registered to another person')
				continue
			try:
				existing.rank           = rank
				existing.first_name     = first_name
				existing.last_name      = last_name
				existing.middle_initial = middle_initial[:1]
				existing.group          = group
				existing.squadron       = squadron
				if tel:
					existing.tel        = tel
				existing.status         = status
				existing.updated_by     = request.user.username
				if photo_url:
					fid = _extract_drive_file_id(photo_url)
					if fid:
						photo_bytes = _download_drive_photo(fid)
						if photo_bytes:
							_save_personnel_photo(existing, photo_bytes)
				existing.save(user=request.user)
				updated_count += 1
			except Exception as exc:
				skipped.append(f'Row {i}: {exc}')

		elif existing and not upsert:
			skipped.append(f'Row {i}: AFSN {afsn} already registered (use "Update existing" to overwrite)')

		else:
			if not tel:
				skipped.append(f'Row {i}: tel required')
				continue
			if Personnel.objects.filter(tel=tel).exists():
				skipped.append(f'Row {i}: tel {tel} already registered')
				continue
			try:
				p = Personnel(
					rank           = rank,
					first_name     = first_name,
					last_name      = last_name,
					middle_initial = middle_initial[:1],
					AFSN           = afsn,
					group          = group,
					squadron       = squadron,
					tel            = tel or None,
					status         = status,
					created_by     = request.user.username,
					updated_by     = request.user.username,
				)
				if photo_url:
					fid = _extract_drive_file_id(photo_url)
					if fid:
						photo_bytes = _download_drive_photo(fid)
						if photo_bytes:
							_save_personnel_photo(p, photo_bytes)
				p.save(user=request.user)
				created_count += 1
			except Exception as exc:
				skipped.append(f'Row {i}: {exc}')

	return created_count, updated_count, skipped


def _flash_import_results(request, created_count, updated_count, skipped):
	if created_count:
		messages.success(request, f'Created {created_count} new personnel record(s).')
	if updated_count:
		messages.success(request, f'Updated {updated_count} existing personnel record(s).')
	if skipped:
		for msg in skipped[:20]:
			messages.warning(request, msg)
		if len(skipped) > 20:
			messages.warning(request, f'…and {len(skipped) - 20} more skipped rows.')
	if not created_count and not updated_count and not skipped:
		messages.info(request, 'No data rows found.')


# ── Bulk Import View ───────────────────────────────────────────────────────────
class PersonnelImportView(LoginRequiredMixin, UserPassesTestMixin, View):
	"""Bulk-create/update Personnel records from an .xlsx file or Google Sheet.
	Required columns (case-insensitive, order doesn't matter):
	  rank, first_name, last_name, middle_initial, afsn, group, squadron, tel
	Optional columns:
	  status, photo  (Google Drive share URL for a 2x2 photo)
	"""
	template_name = 'personnel/personnel_import.html'

	def test_func(self):
		return self.request.user.is_superuser

	def _ctx(self):
		from django.conf import settings as dj_settings
		return {
			'group_choices': PersonnelGroup.get_choices(),
			'gsheets_enabled': bool(getattr(dj_settings, 'GOOGLE_SA_JSON', '')),
		}

	def get(self, request):
		return render(request, self.template_name, self._ctx())

	# ── Excel upload ──────────────────────────────────────────────────────────
	def post(self, request):
		# Route to Google Sheet handler if that tab was submitted
		if request.POST.get('source') == 'gsheet':
			return self._post_gsheet(request)

		xlsx_file = request.FILES.get('xlsx_file')
		if not xlsx_file:
			messages.error(request, 'Please upload an Excel (.xlsx) file.')
			return render(request, self.template_name, self._ctx())
		if not xlsx_file.name.endswith('.xlsx'):
			messages.error(request, 'Only .xlsx files are accepted.')
			return render(request, self.template_name, self._ctx())

		valid_groups_set = PersonnelGroup.get_names_set()
		group_override = request.POST.get('group_override', '').strip()
		if group_override not in valid_groups_set:
			group_override = ''
		upsert = request.POST.get('upsert') == '1'

		try:
			import openpyxl
			wb = openpyxl.load_workbook(xlsx_file, read_only=True, data_only=True)
			ws = wb.active
		except Exception as exc:
			messages.error(request, f'Could not read Excel file: {exc}')
			return render(request, self.template_name, self._ctx())

		rows = list(ws.iter_rows(values_only=True))
		if not rows:
			messages.error(request, 'The Excel file is empty.')
			return render(request, self.template_name, self._ctx())

		headers = [str(h).strip().lower().replace(' ', '_') if h is not None else '' for h in rows[0]]
		required = {'rank', 'first_name', 'last_name', 'middle_initial', 'afsn', 'squadron'}
		if not group_override:
			required.add('group')
		missing = required - set(headers)
		if missing:
			messages.error(request, f'Missing required columns: {", ".join(sorted(missing))}')
			return render(request, self.template_name, self._ctx())

		# Convert rows to list-of-dicts for _import_rows
		data_rows = [dict(zip(headers, row)) for row in rows[1:]]
		# Skip completely blank rows
		data_rows = [r for r in data_rows if any(v is not None and str(v).strip() for v in r.values())]

		created, updated, skipped = _import_rows(request, data_rows, group_override=group_override, upsert=upsert)
		_flash_import_results(request, created, updated, skipped)
		return redirect('personnel-list')

	# ── Google Sheet import ───────────────────────────────────────────────────
	def _post_gsheet(self, request):
		from django.conf import settings as dj_settings

		sa_json = getattr(dj_settings, 'GOOGLE_SA_JSON', '')
		if not sa_json:
			messages.error(request, 'Google Sheets import is not configured on this server.')
			return render(request, self.template_name, self._ctx())

		sheet_url = request.POST.get('sheet_url', '').strip()
		if not sheet_url:
			messages.error(request, 'Please enter a Google Sheet URL.')
			return render(request, self.template_name, self._ctx())

		valid_groups_set = PersonnelGroup.get_names_set()
		group_override = request.POST.get('group_override_gs', '').strip()
		if group_override not in valid_groups_set:
			group_override = ''
		upsert = request.POST.get('upsert_gs') == '1'

		try:
			import gspread
			from google.oauth2.service_account import Credentials
			SCOPES = [
				'https://www.googleapis.com/auth/spreadsheets.readonly',
				'https://www.googleapis.com/auth/drive.readonly',
			]
			creds = Credentials.from_service_account_file(sa_json, scopes=SCOPES)
			gc = gspread.authorize(creds)
			sh = gc.open_by_url(sheet_url)
			ws = sh.sheet1
			all_records = ws.get_all_records(default_blank='')
		except Exception as exc:
			messages.error(request, f'Could not read Google Sheet: {exc}')
			return render(request, self.template_name, self._ctx())

		if not all_records:
			messages.info(request, 'The Google Sheet has no data rows.')
			return redirect('personnel-list')

		# Normalise keys to lowercase_underscore
		def norm_key(k):
			return str(k).strip().lower().replace(' ', '_')
		data_rows = [{norm_key(k): v for k, v in row.items()} for row in all_records]

		required = {'rank', 'first_name', 'last_name', 'middle_initial', 'afsn', 'squadron'}
		if not group_override:
			required.add('group')
		sample_keys = set(data_rows[0].keys()) if data_rows else set()
		missing = required - sample_keys
		if missing:
			messages.error(request, f'Missing required columns in sheet: {", ".join(sorted(missing))}')
			return render(request, self.template_name, self._ctx())

		created, updated, skipped = _import_rows(request, data_rows, group_override=group_override, upsert=upsert)
		_flash_import_results(request, created, updated, skipped)
		return redirect('personnel-list')