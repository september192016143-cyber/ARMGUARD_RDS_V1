from django import forms
from django.core.validators import RegexValidator
from .models import Personnel, PersonnelGroup, PersonnelSquadron

# ── Rank sets (used by the form and by PersonnelListView queryset filtering) ──
_RANKS_ENLISTED = {'AM', 'AW', 'A2C', 'AW2C', 'A1C', 'AW1C', 'SGT', 'SSGT', 'TSGT', 'MSGT', 'SMSGT', 'CMSGT'}
_RANKS_OFFICER  = {'2LT', '1LT', 'CPT', 'MAJ', 'LTCOL', 'COL', 'BGEN', 'MGEN', 'LTGEN', 'GEN'}


def _simulate_personnel_id(rank: str, afsn: str) -> str | None:
	"""Return a simulated Personnel_ID identical in format to what the model generates.
	Returns None if rank or AFSN is empty (preview not ready yet)."""
	if not rank or not afsn:
		return None
	from django.utils import timezone
	dt     = timezone.now()
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

	# Declare squadron explicitly as a plain ChoiceField populated from the
	# DB-backed PersonnelSquadron table in __init__.
	squadron = forms.ChoiceField(choices=[], required=True)

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
		# Build squadron choices from DB; no static fallback needed
		sq_choices = PersonnelSquadron.get_choices()
		self.fields['squadron'].choices = [('', '---------')] + list(sq_choices)

	def clean_tel(self):
		"""Convert empty string to None to avoid unique=True collisions on blank tel."""
		val = self.cleaned_data.get('tel', '').strip()
		return val if val else None
