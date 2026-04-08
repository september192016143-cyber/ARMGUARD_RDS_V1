import json
from django.views.generic import ListView, View
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse_lazy, reverse
from django.db.models import Q, Sum, OuterRef, Subquery, IntegerField, Value, Case, When, Count, F, ExpressionWrapper
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Pistol, Rifle, Magazine, Ammunition, Accessory, AMMUNITION_TYPES, FirearmDiscrepancy
from .pistol_rifle_discrepancy_model import DISCREPANCY_TYPE_CHOICES, DISCREPANCY_STATUS_CHOICES
from .forms import (PistolForm, RifleForm, MagazineForm,
                    AmmunitionForm, AccessoryForm)
# H1 FIX: Import per-module permission helpers.
from armguard.utils.permissions import (
    can_view_inventory, can_add_inventory, can_edit_inventory, can_delete_inventory,
    # Legacy aliases used in context-data dicts; these resolve to the per-module helpers.
    can_manage_inventory, can_edit_delete_inventory, can_add, can_edit, can_delete,
)


class _InventoryPermMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Permission check shared by all inventory CRUD views."""
    def test_func(self):
        return can_view_inventory(self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['item_label'] = self.item_label
        ctx['item_type']  = self.item_type
        ctx['back_url']   = self.success_url
        return ctx


class _InventorySaveMixin(_InventoryPermMixin):
    """Adds user-aware save() for Create/Update views."""
    edit_url_name = None  # Set on CreateView subclasses to redirect to edit after create

    def form_valid(self, form):
        obj = form.save(commit=False)
        is_new = not self.object
        action = 'updated' if self.object else 'added'
        obj.save(user=self.request.user)
        self.object = obj
        messages.success(self.request, f'{self.item_label} {action} successfully.')
        if is_new and self.edit_url_name:
            return redirect(reverse(self.edit_url_name, args=[obj.pk]))
        return redirect(self.get_success_url())


# --- Pistol ------------------------------------------------------------------
class PistolListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = Pistol
    template_name = 'inventory/pistol_list.html'
    context_object_name = 'pistols'
    paginate_by = 10

    def test_func(self):
        return can_view_inventory(self.request.user)

    def get_queryset(self):
        qs = Pistol.objects.select_related('item_issued_to', 'item_assigned_to').order_by('model', 'item_number')
        q = self.request.GET.get('q', '').strip()
        status = self.request.GET.get('status', '').strip()
        model = self.request.GET.get('model', '').strip()
        if q:
            qs = qs.filter(Q(serial_number__icontains=q) | Q(model__icontains=q) | Q(item_id__icontains=q) | Q(property_number__icontains=q))
        if status:
            qs = qs.filter(item_status=status)
        if model:
            qs = qs.filter(model=model)
        return qs

    def get_context_data(self, **kwargs):
        from .models import PISTOL_MODELS
        ctx = super().get_context_data(**kwargs)
        ctx['q'] = self.request.GET.get('q', '')
        ctx['selected_status'] = self.request.GET.get('status', '')
        ctx['selected_model'] = self.request.GET.get('model', '')
        ctx['pistol_model_choices'] = PISTOL_MODELS
        # M2 FIX: One aggregated query instead of 3 separate COUNT queries.
        stats = Pistol.objects.aggregate(
            total=Count('pk'),
            available=Count('pk', filter=Q(item_status='Available')),
            issued=Count('pk', filter=Q(item_status='Issued')),
        )
        ctx.update(stats)
        ctx['can_manage'] = can_manage_inventory(self.request.user)
        ctx['can_edit_delete'] = can_edit_delete_inventory(self.request.user)
        ctx['can_add'] = can_add(self.request.user)
        ctx['can_edit'] = can_edit(self.request.user)
        ctx['can_delete'] = can_delete(self.request.user)
        return ctx

    def render_to_response(self, context, **response_kwargs):
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            from django.shortcuts import render as _render
            return _render(self.request, 'inventory/pistol_rows.html', context)
        return super().render_to_response(context, **response_kwargs)


class PistolCreateView(_InventorySaveMixin, CreateView):
    model = Pistol
    form_class = PistolForm
    template_name = 'inventory/item_form.html'
    success_url = reverse_lazy('pistol-list')
    edit_url_name = 'pistol-edit'
    item_label = 'Pistol'
    item_type = 'pistol'

    def test_func(self):
        return can_add_inventory(self.request.user)


class PistolUpdateView(_InventorySaveMixin, UpdateView):
    model = Pistol
    form_class = PistolForm
    template_name = 'inventory/item_form.html'
    success_url = reverse_lazy('pistol-list')
    item_label = 'Pistol'
    item_type = 'pistol'

    def test_func(self):
        return can_edit_inventory(self.request.user)


class PistolDeleteView(_InventoryPermMixin, DeleteView):
    model = Pistol
    template_name = 'inventory/confirm_delete.html'
    success_url = reverse_lazy('pistol-list')
    item_label = 'Pistol'
    item_type = 'pistol'

    def test_func(self):
        return can_delete_inventory(self.request.user)

    def form_valid(self, form):
        messages.success(self.request, 'Pistol deleted.')
        return super().form_valid(form)


# --- Rifle -------------------------------------------------------------------
class RifleListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = Rifle
    template_name = 'inventory/rifle_list.html'
    context_object_name = 'rifles'
    paginate_by = 10

    def test_func(self):
        return can_view_inventory(self.request.user)

    _SORT_FIELDS = {
        'item_number': 'item_number',
        'property':    'property_number',
        'model':       'model',
        'serial':      'serial_number',
        'status':      'item_status',
    }

    def get_queryset(self):
        sort_key   = self.request.GET.get('sort', 'model')
        sort_dir   = self.request.GET.get('dir',  'asc')
        sort_field = self._SORT_FIELDS.get(sort_key, 'model')
        prefix     = '-' if sort_dir == 'desc' else ''
        qs = Rifle.objects.select_related('item_issued_to', 'item_assigned_to').order_by(prefix + sort_field)
        q = self.request.GET.get('q', '').strip()
        status = self.request.GET.get('status', '').strip()
        model = self.request.GET.get('model', '').strip()
        if q:
            qs = qs.filter(Q(serial_number__icontains=q) | Q(model__icontains=q) | Q(item_id__icontains=q) | Q(property_number__icontains=q))
        if status:
            qs = qs.filter(item_status=status)
        if model:
            qs = qs.filter(model=model)
        return qs

    def get_context_data(self, **kwargs):
        from .models import RIFLE_MODELS
        ctx = super().get_context_data(**kwargs)
        ctx['q'] = self.request.GET.get('q', '')
        ctx['selected_status'] = self.request.GET.get('status', '')
        ctx['selected_model'] = self.request.GET.get('model', '')
        ctx['sort']     = self.request.GET.get('sort', 'model')
        ctx['sort_dir'] = self.request.GET.get('dir',  'asc')
        ctx['rifle_model_choices'] = RIFLE_MODELS
        # M2 FIX: One aggregated query instead of 3 separate COUNT queries.
        stats = Rifle.objects.aggregate(
            total=Count('pk'),
            available=Count('pk', filter=Q(item_status='Available')),
            issued=Count('pk', filter=Q(item_status='Issued')),
        )
        ctx.update(stats)
        ctx['can_manage'] = can_manage_inventory(self.request.user)
        ctx['can_edit_delete'] = can_edit_delete_inventory(self.request.user)
        ctx['can_add'] = can_add(self.request.user)
        ctx['can_edit'] = can_edit(self.request.user)
        ctx['can_delete'] = can_delete(self.request.user)
        return ctx

    def render_to_response(self, context, **response_kwargs):
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            from django.shortcuts import render as _render
            return _render(self.request, 'inventory/rifle_rows.html', context)
        return super().render_to_response(context, **response_kwargs)


class RifleCreateView(_InventorySaveMixin, CreateView):
    model = Rifle
    form_class = RifleForm
    template_name = 'inventory/item_form.html'
    success_url = reverse_lazy('rifle-list')
    edit_url_name = 'rifle-edit'
    item_label = 'Rifle'
    item_type = 'rifle'

    def test_func(self):
        return can_add_inventory(self.request.user)


class RifleUpdateView(_InventorySaveMixin, UpdateView):
    model = Rifle
    form_class = RifleForm
    template_name = 'inventory/item_form.html'
    success_url = reverse_lazy('rifle-list')
    item_label = 'Rifle'
    item_type = 'rifle'

    def test_func(self):
        return can_edit_inventory(self.request.user)


class RifleDeleteView(_InventoryPermMixin, DeleteView):
    model = Rifle
    template_name = 'inventory/confirm_delete.html'
    success_url = reverse_lazy('rifle-list')
    item_label = 'Rifle'
    item_type = 'rifle'

    def test_func(self):
        return can_delete_inventory(self.request.user)

    def form_valid(self, form):
        messages.success(self.request, 'Rifle deleted.')
        return super().form_valid(form)


# --- Magazine ----------------------------------------------------------------
class MagazineListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = Magazine
    template_name = 'inventory/magazine_list.html'
    context_object_name = 'magazines'
    paginate_by = 25

    def test_func(self):
        return can_view_inventory(self.request.user)

    def get_queryset(self):
        qs = Magazine.objects.order_by('weapon_type', 'type')
        q = self.request.GET.get('q', '').strip()
        weapon_type = self.request.GET.get('weapon_type', '').strip()
        if q:
            qs = qs.filter(Q(type__icontains=q) | Q(weapon_type__icontains=q))
        if weapon_type:
            qs = qs.filter(weapon_type=weapon_type)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['total_qty'] = Magazine.objects.aggregate(t=Sum('quantity'))['t'] or 0
        ctx['can_manage'] = can_manage_inventory(self.request.user)
        ctx['can_edit_delete'] = can_edit_delete_inventory(self.request.user)
        ctx['can_add'] = can_add(self.request.user)
        ctx['can_edit'] = can_edit(self.request.user)
        ctx['can_delete'] = can_delete(self.request.user)
        return ctx


class MagazineCreateView(_InventorySaveMixin, CreateView):
    model = Magazine
    form_class = MagazineForm
    template_name = 'inventory/item_form.html'
    success_url = reverse_lazy('magazine-list')
    item_label = 'Magazine Pool'
    item_type = 'magazine'

    def test_func(self):
        return can_add_inventory(self.request.user)


class MagazineUpdateView(_InventorySaveMixin, UpdateView):
    model = Magazine
    form_class = MagazineForm
    template_name = 'inventory/item_form.html'
    success_url = reverse_lazy('magazine-list')
    item_label = 'Magazine Pool'
    item_type = 'magazine'

    def test_func(self):
        return can_edit_inventory(self.request.user)


class MagazineDeleteView(_InventoryPermMixin, DeleteView):
    model = Magazine
    template_name = 'inventory/confirm_delete.html'
    success_url = reverse_lazy('magazine-list')
    item_label = 'Magazine Pool'
    item_type = 'magazine'

    def test_func(self):
        return can_delete_inventory(self.request.user)

    def form_valid(self, form):
        messages.success(self.request, 'Magazine pool deleted.')
        return super().form_valid(form)


# --- Ammunition --------------------------------------------------------------
def _ammo_issued_subqueries():
    """Return (pistol_sub, rifle_sub, pistol_par, rifle_par, pistol_tr, rifle_tr) Subquery annotations."""
    from armguard.apps.transactions.models import TransactionLogs
    pistol_sub = TransactionLogs.objects.filter(
        withdraw_pistol_ammunition=OuterRef('pk'),
        return_pistol_ammunition__isnull=True,
    ).values('withdraw_pistol_ammunition').annotate(
        s=Sum('withdraw_pistol_ammunition_quantity')
    ).values('s')[:1]
    rifle_sub = TransactionLogs.objects.filter(
        withdraw_rifle_ammunition=OuterRef('pk'),
        return_rifle_ammunition__isnull=True,
    ).values('withdraw_rifle_ammunition').annotate(
        s=Sum('withdraw_rifle_ammunition_quantity')
    ).values('s')[:1]
    pistol_par = TransactionLogs.objects.filter(
        withdraw_pistol_ammunition=OuterRef('pk'),
        return_pistol_ammunition__isnull=True,
        issuance_type__icontains='PAR',
    ).values('withdraw_pistol_ammunition').annotate(
        s=Sum('withdraw_pistol_ammunition_quantity')
    ).values('s')[:1]
    rifle_par = TransactionLogs.objects.filter(
        withdraw_rifle_ammunition=OuterRef('pk'),
        return_rifle_ammunition__isnull=True,
        issuance_type__icontains='PAR',
    ).values('withdraw_rifle_ammunition').annotate(
        s=Sum('withdraw_rifle_ammunition_quantity')
    ).values('s')[:1]
    pistol_tr = TransactionLogs.objects.filter(
        withdraw_pistol_ammunition=OuterRef('pk'),
        return_pistol_ammunition__isnull=True,
        issuance_type__icontains='TR',
    ).values('withdraw_pistol_ammunition').annotate(
        s=Sum('withdraw_pistol_ammunition_quantity')
    ).values('s')[:1]
    rifle_tr = TransactionLogs.objects.filter(
        withdraw_rifle_ammunition=OuterRef('pk'),
        return_rifle_ammunition__isnull=True,
        issuance_type__icontains='TR',
    ).values('withdraw_rifle_ammunition').annotate(
        s=Sum('withdraw_rifle_ammunition_quantity')
    ).values('s')[:1]
    return pistol_sub, rifle_sub, pistol_par, rifle_par, pistol_tr, rifle_tr


class AmmunitionListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = Ammunition
    template_name = 'inventory/ammunition_list.html'
    context_object_name = 'ammunition'
    paginate_by = 25

    def test_func(self):
        return can_view_inventory(self.request.user)

    def get_queryset(self):
        pistol_sub, rifle_sub, pistol_par, rifle_par, pistol_tr, rifle_tr = _ammo_issued_subqueries()
        type_order = Case(
            *[When(type=value, then=Value(i)) for i, (value, _) in enumerate(AMMUNITION_TYPES)],
            default=Value(len(AMMUNITION_TYPES)),
            output_field=IntegerField(),
        )
        qs = Ammunition.objects.annotate(
            pistol_issued=Coalesce(Subquery(pistol_sub, output_field=IntegerField()), Value(0)),
            rifle_issued=Coalesce(Subquery(rifle_sub, output_field=IntegerField()), Value(0)),
            pistol_issued_par=Coalesce(Subquery(pistol_par, output_field=IntegerField()), Value(0)),
            rifle_issued_par=Coalesce(Subquery(rifle_par, output_field=IntegerField()), Value(0)),
            pistol_issued_tr=Coalesce(Subquery(pistol_tr, output_field=IntegerField()), Value(0)),
            rifle_issued_tr=Coalesce(Subquery(rifle_tr, output_field=IntegerField()), Value(0)),
            type_order=type_order,
        ).annotate(
            on_stock=ExpressionWrapper(
                F('quantity') - F('pistol_issued') - F('rifle_issued'),
                output_field=IntegerField()
            )
        ).order_by('type_order', 'lot_number')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(type__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        agg = Ammunition.objects.aggregate(t=Sum('quantity'))
        ctx['total_qty'] = agg['t'] or 0
        ctx['can_manage'] = can_manage_inventory(self.request.user)
        ctx['can_edit_delete'] = can_edit_delete_inventory(self.request.user)
        ctx['can_add'] = can_add(self.request.user)
        ctx['can_edit'] = can_edit(self.request.user)
        ctx['can_delete'] = can_delete(self.request.user)
        # Group all lots by ammo type
        type_map = {}
        for a in self.object_list:
            if a.type not in type_map:
                type_map[a.type] = {
                    'type': a.type, '_order': a.type_order,
                    '_qty': 0, '_pi': 0, '_ri': 0,
                    '_pp': 0, '_rp': 0, '_pt': 0, '_rt': 0, '_os': 0,
                }
            g = type_map[a.type]
            g['_qty'] += a.quantity
            g['_pi'] += a.pistol_issued
            g['_ri'] += a.rifle_issued
            g['_pp'] += a.pistol_issued_par
            g['_rp'] += a.rifle_issued_par
            g['_pt'] += a.pistol_issued_tr
            g['_rt'] += a.rifle_issued_tr
            g['_os'] += a.on_stock
        ctx['grouped_ammo'] = [
            {
                'type': g['type'],
                'possessed': g['_qty'] + g['_pi'] + g['_ri'],
                'on_stock': g['_os'],
                'issued_par': g['_pp'] + g['_rp'],
                'issued_tr': g['_pt'] + g['_rt'],
            }
            for g in sorted(type_map.values(), key=lambda x: x['_order'])
        ]
        # Build per-type lot breakdown for drill-down modal
        lots_by_type = {}
        for a in self.object_list:
            lots_by_type.setdefault(a.type, []).append({
                'lot': a.lot_number,
                'possessed': a.quantity + a.pistol_issued + a.rifle_issued,
                'on_stock': a.on_stock,
                'issued_par': a.pistol_issued_par + a.rifle_issued_par,
                'issued_tr': a.pistol_issued_tr + a.rifle_issued_tr,
            })
        ctx['lots_by_type_json'] = json.dumps(lots_by_type)
        totals = self.object_list.aggregate(
            total_on_stock=Sum('quantity'),
            total_pistol_issued=Sum('pistol_issued'),
            total_rifle_issued=Sum('rifle_issued'),
            total_pistol_par=Sum('pistol_issued_par'),
            total_rifle_par=Sum('rifle_issued_par'),
            total_pistol_tr=Sum('pistol_issued_tr'),
            total_rifle_tr=Sum('rifle_issued_tr'),
        )
        total_issued = (totals['total_pistol_issued'] or 0) + (totals['total_rifle_issued'] or 0)
        total_on_stock = totals['total_on_stock'] or 0
        ctx['total_on_stock'] = total_on_stock
        ctx['total_possessed'] = total_on_stock + total_issued
        ctx['total_issued'] = total_issued
        ctx['total_issued_par'] = (totals['total_pistol_par'] or 0) + (totals['total_rifle_par'] or 0)
        ctx['total_issued_tr'] = (totals['total_pistol_tr'] or 0) + (totals['total_rifle_tr'] or 0)
        return ctx


@login_required
def ammunition_stock_json(request):
    pistol_sub, rifle_sub, pistol_par, rifle_par, pistol_tr, rifle_tr = _ammo_issued_subqueries()
    rows = Ammunition.objects.annotate(
        pistol_issued=Coalesce(Subquery(pistol_sub, output_field=IntegerField()), Value(0)),
        rifle_issued=Coalesce(Subquery(rifle_sub, output_field=IntegerField()), Value(0)),
        pistol_issued_par=Coalesce(Subquery(pistol_par, output_field=IntegerField()), Value(0)),
        rifle_issued_par=Coalesce(Subquery(rifle_par, output_field=IntegerField()), Value(0)),
        pistol_issued_tr=Coalesce(Subquery(pistol_tr, output_field=IntegerField()), Value(0)),
        rifle_issued_tr=Coalesce(Subquery(rifle_tr, output_field=IntegerField()), Value(0)),
    ).values('type', 'quantity', 'pistol_issued', 'rifle_issued',
             'pistol_issued_par', 'rifle_issued_par', 'pistol_issued_tr', 'rifle_issued_tr')
    groups = {}
    for r in rows:
        t = r['type']
        if t not in groups:
            groups[t] = {'type': t, 'possessed': 0, 'on_stock': 0, 'issued_par': 0, 'issued_tr': 0}
        g = groups[t]
        issued = r['pistol_issued'] + r['rifle_issued']
        g['possessed'] += r['quantity'] + issued
        g['on_stock'] += r['quantity'] - issued
        g['issued_par'] += r['pistol_issued_par'] + r['rifle_issued_par']
        g['issued_tr'] += r['pistol_issued_tr'] + r['rifle_issued_tr']
    return JsonResponse({'items': list(groups.values())})


class AmmunitionLotsByTypeView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = Ammunition
    template_name = 'inventory/ammunition_lots_by_type.html'
    context_object_name = 'lots'
    paginate_by = 25

    def test_func(self):
        return can_view_inventory(self.request.user)

    def get_queryset(self):
        pistol_sub, rifle_sub, pistol_par, rifle_par, pistol_tr, rifle_tr = _ammo_issued_subqueries()
        qs = Ammunition.objects.filter(type=self.kwargs['ammo_type']).annotate(
            pistol_issued=Coalesce(Subquery(pistol_sub, output_field=IntegerField()), Value(0)),
            rifle_issued=Coalesce(Subquery(rifle_sub, output_field=IntegerField()), Value(0)),
            pistol_issued_par=Coalesce(Subquery(pistol_par, output_field=IntegerField()), Value(0)),
            rifle_issued_par=Coalesce(Subquery(rifle_par, output_field=IntegerField()), Value(0)),
            pistol_issued_tr=Coalesce(Subquery(pistol_tr, output_field=IntegerField()), Value(0)),
            rifle_issued_tr=Coalesce(Subquery(rifle_tr, output_field=IntegerField()), Value(0)),
        ).annotate(
            on_stock=ExpressionWrapper(
                F('quantity') - F('pistol_issued') - F('rifle_issued'),
                output_field=IntegerField()
            )
        ).order_by('lot_number')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(lot_number__icontains=q)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['ammo_type'] = self.kwargs['ammo_type']
        ctx['can_add'] = can_add(self.request.user)
        ctx['can_edit'] = can_edit(self.request.user)
        ctx['can_delete'] = can_delete(self.request.user)
        ctx['q'] = self.request.GET.get('q', '')
        # Totals across ALL lots of this type (unfiltered)
        ps, rs, pp, rp, pt, rt = _ammo_issued_subqueries()
        totals = Ammunition.objects.filter(type=self.kwargs['ammo_type']).annotate(
            pistol_issued=Coalesce(Subquery(ps, output_field=IntegerField()), Value(0)),
            rifle_issued=Coalesce(Subquery(rs, output_field=IntegerField()), Value(0)),
            pistol_issued_par=Coalesce(Subquery(pp, output_field=IntegerField()), Value(0)),
            rifle_issued_par=Coalesce(Subquery(rp, output_field=IntegerField()), Value(0)),
            pistol_issued_tr=Coalesce(Subquery(pt, output_field=IntegerField()), Value(0)),
            rifle_issued_tr=Coalesce(Subquery(rt, output_field=IntegerField()), Value(0)),
        ).annotate(
            on_stock=ExpressionWrapper(
                F('quantity') - F('pistol_issued') - F('rifle_issued'),
                output_field=IntegerField()
            )
        ).aggregate(
            total_qty=Sum('quantity'),
            total_pi=Sum('pistol_issued'),
            total_ri=Sum('rifle_issued'),
            total_pp=Sum('pistol_issued_par'),
            total_rp=Sum('rifle_issued_par'),
            total_pt=Sum('pistol_issued_tr'),
            total_rt=Sum('rifle_issued_tr'),
            total_os=Sum('on_stock'),
        )
        issued = (totals['total_pi'] or 0) + (totals['total_ri'] or 0)
        ctx['total_possessed'] = (totals['total_qty'] or 0) + issued
        ctx['total_on_stock'] = totals['total_os'] or 0
        ctx['total_issued_par'] = (totals['total_pp'] or 0) + (totals['total_rp'] or 0)
        ctx['total_issued_tr'] = (totals['total_pt'] or 0) + (totals['total_rt'] or 0)
        return ctx


class AmmunitionCreateView(_InventorySaveMixin, CreateView):
    model = Ammunition
    form_class = AmmunitionForm
    template_name = 'inventory/item_form.html'
    success_url = reverse_lazy('ammunition-list')
    item_label = 'Ammunition Lot'
    item_type = 'ammunition'

    def test_func(self):
        return can_add_inventory(self.request.user)


class AmmunitionUpdateView(_InventorySaveMixin, UpdateView):
    model = Ammunition
    form_class = AmmunitionForm
    template_name = 'inventory/item_form.html'
    success_url = reverse_lazy('ammunition-list')
    item_label = 'Ammunition Lot'
    item_type = 'ammunition'

    def test_func(self):
        return can_edit_inventory(self.request.user)


class AmmunitionDeleteView(_InventoryPermMixin, DeleteView):
    model = Ammunition
    template_name = 'inventory/confirm_delete.html'
    success_url = reverse_lazy('ammunition-list')
    item_label = 'Ammunition Lot'
    item_type = 'ammunition'

    def test_func(self):
        return can_delete_inventory(self.request.user)

    def form_valid(self, form):
        messages.success(self.request, 'Ammunition lot deleted.')
        return super().form_valid(form)


# --- Accessory ---------------------------------------------------------------
class AccessoryListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = Accessory
    template_name = 'inventory/accessory_list.html'
    context_object_name = 'accessories'
    paginate_by = 25

    def test_func(self):
        return can_view_inventory(self.request.user)

    def get_queryset(self):
        qs = Accessory.objects.order_by('type')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(type__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['total'] = Accessory.objects.count()
        ctx['can_manage'] = can_manage_inventory(self.request.user)
        ctx['can_edit_delete'] = can_edit_delete_inventory(self.request.user)
        ctx['can_add'] = can_add(self.request.user)
        ctx['can_edit'] = can_edit(self.request.user)
        ctx['can_delete'] = can_delete(self.request.user)
        return ctx


class AccessoryCreateView(_InventorySaveMixin, CreateView):
    model = Accessory
    form_class = AccessoryForm
    template_name = 'inventory/item_form.html'
    success_url = reverse_lazy('accessory-list')
    item_label = 'Accessory Pool'
    item_type = 'accessory'

    def test_func(self):
        return can_add_inventory(self.request.user)


class AccessoryUpdateView(_InventorySaveMixin, UpdateView):
    model = Accessory
    form_class = AccessoryForm
    template_name = 'inventory/item_form.html'
    success_url = reverse_lazy('accessory-list')
    item_label = 'Accessory Pool'
    item_type = 'accessory'

    def test_func(self):
        return can_edit_inventory(self.request.user)


class AccessoryDeleteView(_InventoryPermMixin, DeleteView):
    model = Accessory
    template_name = 'inventory/confirm_delete.html'
    success_url = reverse_lazy('accessory-list')
    item_label = 'Accessory Pool'
    item_type = 'accessory'

    def test_func(self):
        return can_delete_inventory(self.request.user)

    def form_valid(self, form):
        messages.success(self.request, 'Accessory pool deleted.')
        return super().form_valid(form)


class ItemTagPreviewView(LoginRequiredMixin, View):
    """POST {item_type, model, serial_number, item_number} → returns a live preview PNG of the item tag."""
    def post(self, request, *args, **kwargs):
        import io, logging
        from types import SimpleNamespace
        from django.http import HttpResponse
        _log = logging.getLogger(__name__)
        try:
            from utils.item_tag_generator import _build_tag

            item = SimpleNamespace()
            item.item_type = request.POST.get('item_type', 'pistol')
            item.model = request.POST.get('model', '')
            item.serial = request.POST.get('serial_number', '') or '\u2014'
            item.item_number = request.POST.get('item_number', '').strip() or None
            item.qr_code_image = None
            item.get_item_type_display = lambda: {'pistol': 'Pistol', 'rifle': 'Rifle'}.get(item.item_type, 'Item')
            # Compute the same QR data string that models.py would generate on save,
            # then render a live QR image in-memory so the tag preview is never "NO QR".
            import re as _re
            from utils.qr_generator import generate_qr_code_to_buffer
            from PIL import Image as _PILImage
            serial_val = request.POST.get('serial_number', '').strip()
            if serial_val:
                if item.item_type == 'pistol':
                    _PISTOL_CODE_MAP = {
                        'Glock 17 9mm':           'GL17',
                        'M1911 Cal.45':           'M1911',
                        'Armscor Hi Cap Cal.45':  'ARMSCOR',
                        'RIA Hi Cap Cal.45':      'RIA',
                        'M1911 Customized Cal.45':'M1911C',
                    }
                    _mc = _PISTOL_CODE_MAP.get(item.model) or _re.sub(r'[^A-Z0-9]', '_', item.model.upper())
                    _qr_data = f'IP-{_mc}-{serial_val}'
                else:  # rifle
                    _factory_qr = request.POST.get('factory_qr', '').strip()
                    if item.model == 'M4 Carbine DSAR-15 5.56mm' and _factory_qr:
                        _qr_data = _factory_qr
                    else:
                        _RIFLE_CODE_MAP = {
                            'M4 Carbine DSAR-15 5.56mm':  'M4',
                            'M4 14.5" DGIS EMTAN 5.56mm': 'M4E',
                            'M16A1 Rifle 5.56mm':         'M16',
                            'M14 Rifle 7.62mm':           'M14',
                            'M653 Carbine 5.56mm':        'M653',
                        }
                        _mc = _RIFLE_CODE_MAP.get(item.model) or _re.sub(r'[^A-Z0-9]', '_', item.model.upper())
                        _qr_data = f'IR-{_mc}-{serial_val}'
                try:
                    _qr_buf = generate_qr_code_to_buffer(_qr_data)
                    item._qr_pil_img = _PILImage.open(_qr_buf)
                except Exception:
                    item._qr_pil_img = None
            else:
                item._qr_pil_img = None
            img = _build_tag(item)
            buf = io.BytesIO()
            img.save(buf, 'PNG')
            buf.seek(0)
            return HttpResponse(buf.read(), content_type='image/png')
        except Exception as exc:
            _log.exception('ItemTagPreviewView failed: %s', exc)
            return HttpResponse(f'Preview error: {exc}', content_type='text/plain', status=500)


class FieldValidateView(LoginRequiredMixin, View):
    """
    GET ?item_type=pistol&field=serial_number&value=X&model=Y&exclude_pk=Z
    Returns JSON {ok: bool, msg: str} — used for real-time field availability checks.
    Fields: serial_number (global unique), item_number (unique per model), property_number (global unique).
    """
    def get(self, request, *args, **kwargs):
        item_type   = request.GET.get('item_type', 'pistol')
        field       = request.GET.get('field', '')
        value       = request.GET.get('value', '').strip()
        model       = request.GET.get('model', '').strip()
        exclude_pk  = request.GET.get('exclude_pk', '').strip()
        Model       = Pistol if item_type == 'pistol' else Rifle
        if not value:
            return JsonResponse({'ok': True, 'msg': ''})
        if field == 'serial_number':
            qs = Model.objects.filter(serial_number=value)
            if exclude_pk:
                qs = qs.exclude(pk=exclude_pk)
            if qs.exists():
                return JsonResponse({'ok': False, 'msg': 'Serial number already registered.'})
        elif field == 'item_number':
            padded = f'{int(value):04d}' if value.isdigit() else value
            qs = Model.objects.filter(model=model, item_number=padded)
            if exclude_pk:
                qs = qs.exclude(pk=exclude_pk)
            if qs.exists():
                return JsonResponse({'ok': False, 'msg': f'Item number {padded} already used for this model.'})
        elif field == 'property_number':
            qs = Model.objects.filter(property_number=value)
            if exclude_pk:
                qs = qs.exclude(pk=exclude_pk)
            if qs.exists():
                return JsonResponse({'ok': False, 'msg': 'Property number already registered.'})
        else:
            return JsonResponse({'ok': True, 'msg': ''})
        return JsonResponse({'ok': True, 'msg': 'Available'})


# ── Serial Image Phone Capture ───────────────────────────────────────────────

from django.contrib.auth.decorators import login_required  # noqa: E402
from django.views.decorators.http import require_POST       # noqa: E402
from django.views.decorators.csrf import csrf_exempt        # noqa: E402
from django.conf import settings as _settings               # noqa: E402


@login_required
@require_POST
def serial_capture_init(request):
    """
    Admin POSTs here to start a phone-capture session for a serial image.

    If the logged-in user has an active paired camera device (the phone already
    open on /camera/), sets a pending task on that device — no QR needed.
    Returns JSON: {token, mode: 'device', device_name} or {token, mode: 'qr', qr_b64, phone_url}.

    Purges stale sessions (> 30 min old) on every call.
    """
    import io, base64, qrcode
    from datetime import timedelta
    from django.utils import timezone
    from .models import SerialImageCapture

    SerialImageCapture.objects.filter(
        created_at__lt=timezone.now() - timedelta(minutes=30)
    ).delete()

    session = SerialImageCapture.objects.create()

    # ── Paired camera device path (zero-QR) ───────────────────────────────────
    try:
        from armguard.apps.camera.models import CameraDevice
        paired_device = CameraDevice.objects.filter(
            user=request.user,
            is_active=True,
            revoked_at__isnull=True,
        ).first()

        if paired_device:
            CameraDevice.objects.filter(pk=paired_device.pk).update(
                pending_serial_task=session.token
            )
            return JsonResponse({
                'token':       str(session.token),
                'mode':        'device',
                'device_name': paired_device.device_name or 'unnamed',
            })

        # No active device — send user to register/pair their phone instead of showing a QR.
        pair_url = request.build_absolute_uri(reverse('camera:my_device') + '?setup=1')
        return JsonResponse({
            'token':    str(session.token),
            'mode':     'pair_needed',
            'pair_url': pair_url,
        })
    except Exception:
        pass  # camera app not installed — fall through to QR

    # ── QR fallback (camera app unavailable) ────────────────────────────────────────
    phone_url = request.build_absolute_uri(
        reverse('serial-capture-phone', kwargs={'token': str(session.token)})
    )

    qr = qrcode.QRCode(box_size=6, border=2,
                       error_correction=qrcode.constants.ERROR_CORRECT_H)
    qr.add_data(phone_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color='#0f172a', back_color='white')
    buf = io.BytesIO()
    qr_img.save(buf, format='PNG')
    qr_b64 = base64.b64encode(buf.getvalue()).decode()

    return JsonResponse({
        'token':     str(session.token),
        'mode':      'qr',
        'qr_b64':    qr_b64,
        'phone_url': phone_url,
    })


def serial_capture_phone(request, token):
    """
    Phone-facing HTML page — no Django auth required, token is the credential.
    GET: renders the capture UI.
    """
    from datetime import timedelta
    from django.utils import timezone
    from django.shortcuts import render
    from .models import SerialImageCapture

    try:
        session = SerialImageCapture.objects.get(token=token)
    except SerialImageCapture.DoesNotExist:
        return render(request, 'inventory/serial_capture_phone.html', {'expired': True})

    if session.created_at < timezone.now() - timedelta(minutes=30):
        session.delete()
        return render(request, 'inventory/serial_capture_phone.html', {'expired': True})

    upload_url = request.build_absolute_uri(
        reverse('serial-capture-upload', kwargs={'token': str(token)})
    )
    return render(request, 'inventory/serial_capture_phone.html', {
        'token':      str(token),
        'upload_url': upload_url,
        'has_image':  bool(session.image),
    })


@csrf_exempt
@require_POST
def serial_capture_upload(request, token):
    """
    Phone POSTs the captured image file here.
    No Django auth — the UUID token is the credential.
    """
    import os
    from datetime import timedelta
    from django.utils import timezone
    from .models import SerialImageCapture

    try:
        session = SerialImageCapture.objects.get(token=token)
    except SerialImageCapture.DoesNotExist:
        return JsonResponse({'error': 'Session expired or not found.'}, status=404)

    if session.created_at < timezone.now() - timedelta(minutes=30):
        session.delete()
        return JsonResponse({'error': 'Session expired.'}, status=410)

    file = request.FILES.get('image')
    if not file:
        return JsonResponse({'error': 'No image uploaded.'}, status=400)

    allowed_types = {
        'image/jpeg', 'image/jpg', 'image/png', 'image/webp',
        'image/heic', 'image/heif',
    }
    if file.content_type not in allowed_types:
        return JsonResponse({'error': 'Invalid file type.'}, status=400)

    if file.size > 20 * 1024 * 1024:
        return JsonResponse({'error': 'File too large (max 20 MB).'}, status=400)

    if session.image:
        try:
            session.image.delete(save=False)
        except Exception:
            pass

    ext = os.path.splitext(file.name)[1].lower() or '.jpg'
    session.image.save(f'{token}{ext}', file, save=True)
    return JsonResponse({'success': True})


@login_required
def serial_capture_poll(request, token):
    """
    Admin polls this (GET) every 2 s while waiting for the phone to upload.
    Returns JSON: {ready: bool, image_url?: str, expired?: bool}.
    """
    from .models import SerialImageCapture

    try:
        session = SerialImageCapture.objects.get(token=token)
    except SerialImageCapture.DoesNotExist:
        return JsonResponse({'ready': False, 'expired': True})

    if session.image and session.image.name:
        image_url = request.build_absolute_uri(
            _settings.MEDIA_URL + session.image.name
        )
        return JsonResponse({'ready': True, 'image_url': image_url})

    return JsonResponse({'ready': False})


# ── Firearm Discrepancy views ────────────────────────────────────────────────

class FirearmDiscrepancyListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model               = FirearmDiscrepancy
    template_name       = 'inventory/discrepancy_list.html'
    context_object_name = 'discrepancies'
    paginate_by         = 25

    def test_func(self):
        return can_view_inventory(self.request.user)

    def get_queryset(self):
        qs = FirearmDiscrepancy.objects.select_related(
            'pistol', 'rifle', 'issuer', 'withdrawer', 'reported_by'
        )
        q      = self.request.GET.get('q', '').strip()
        status = self.request.GET.get('status', '').strip()
        dtype  = self.request.GET.get('type', '').strip()
        if q:
            qs = qs.filter(
                Q(pistol__serial_number__icontains=q) |
                Q(rifle__serial_number__icontains=q)  |
                Q(description__icontains=q)           |
                Q(reported_by__username__icontains=q)
            )
        if status:
            qs = qs.filter(status=status)
        if dtype:
            qs = qs.filter(discrepancy_type=dtype)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['status_choices'] = DISCREPANCY_STATUS_CHOICES
        ctx['type_choices']   = DISCREPANCY_TYPE_CHOICES
        ctx['can_add']        = can_add_inventory(self.request.user)
        return ctx


class FirearmDiscrepancyCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model         = FirearmDiscrepancy
    template_name = 'inventory/discrepancy_form.html'
    fields        = [
        'pistol', 'rifle', 'issuer', 'withdrawer', 'related_transaction',
        'discrepancy_type', 'description', 'image', 'image_2', 'image_3', 'image_4', 'image_5', 'status',
    ]
    success_url = reverse_lazy('discrepancy-list')

    def test_func(self):
        return can_add_inventory(self.request.user)

    def form_valid(self, form):
        form.instance.reported_by = self.request.user
        messages.success(self.request, 'Discrepancy recorded.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Log Discrepancy'
        return ctx


class FirearmDiscrepancyUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model         = FirearmDiscrepancy
    template_name = 'inventory/discrepancy_form.html'
    fields        = [
        'pistol', 'rifle', 'issuer', 'withdrawer', 'related_transaction',
        'discrepancy_type', 'description', 'image', 'image_2', 'image_3', 'image_4', 'image_5', 'status',
        'resolved_by', 'resolved_at', 'resolution_notes',
    ]
    success_url = reverse_lazy('discrepancy-list')

    def test_func(self):
        return can_edit_inventory(self.request.user)

    def form_valid(self, form):
        messages.success(self.request, 'Discrepancy updated.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Edit Discrepancy'
        return ctx


# ── Bulk Excel Import ──────────────────────────────────────────────────────────
class InventoryImportView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Upload an .xlsx file to bulk-create Pistol or Rifle records.

    The first row must be a header. Accepted item types: pistol, rifle.

    Pistol required columns:  item_type, model, serial_number, item_number
    Pistol optional columns:  property_number, item_condition, item_status, description

    Rifle required columns:   item_type, model, serial_number, item_number
    Rifle optional columns:   factory_qr (required when model=M4 Carbine DSAR-15 5.56mm),
                              property_number, item_condition, item_status, description

    Use the EXACT model strings defined in PISTOL_MODELS / RIFLE_MODELS.
    One sheet may contain a mix of pistol and rifle rows.
    """
    template_name = 'inventory/inventory_import.html'

    def test_func(self):
        return self.request.user.is_superuser

    def get(self, request):
        from .models import PISTOL_MODELS, RIFLE_MODELS
        return render(request, self.template_name, {
            'pistol_models':        [m for m, _ in PISTOL_MODELS],
            'rifle_models':         [m for m, _ in RIFLE_MODELS],
            'pistol_model_choices': PISTOL_MODELS,
            'rifle_model_choices':  RIFLE_MODELS,
        })

    def post(self, request):
        from .models import PISTOL_MODELS, RIFLE_MODELS, STATUS_CHOICES, CONDITION_CHOICES
        xlsx_file = request.FILES.get('xlsx_file')
        if not xlsx_file:
            messages.error(request, 'Please upload an Excel (.xlsx) file.')
            return redirect('inventory-import')
        if not xlsx_file.name.endswith('.xlsx'):
            messages.error(request, 'Only .xlsx files are accepted.')
            return redirect('inventory-import')

        valid_pistol_models = {m for m, _ in PISTOL_MODELS}
        valid_rifle_models  = {m for m, _ in RIFLE_MODELS}

        # Batch-model override: pre-select both item_type and model for every row.
        model_override = request.POST.get('model_override', '').strip()
        if model_override in valid_pistol_models:
            item_type_override = 'pistol'
        elif model_override in valid_rifle_models:
            item_type_override = 'rifle'
        else:
            model_override    = ''
            item_type_override = ''

        try:
            import openpyxl
            wb = openpyxl.load_workbook(xlsx_file, read_only=True, data_only=True)
            ws = wb.active
        except Exception as exc:
            messages.error(request, f'Could not read Excel file: {exc}')
            return redirect('inventory-import')

        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            messages.error(request, 'The Excel file is empty.')
            return redirect('inventory-import')

        headers = [str(h).strip().lower().replace(' ', '_') if h is not None else '' for h in rows[0]]
        required_cols = {'serial_number', 'item_number'}
        if not model_override:
            required_cols.add('model')
            required_cols.add('item_type')
        missing = required_cols - set(headers)
        if missing:
            messages.error(request, f'Missing required columns: {", ".join(sorted(missing))}')
            return redirect('inventory-import')

        def col(row, name, default=''):
            if name not in headers:
                return default
            val = row[headers.index(name)]
            return str(val).strip() if val is not None else default

        valid_pistol_models = {m for m, _ in PISTOL_MODELS}
        valid_rifle_models  = {m for m, _ in RIFLE_MODELS}
        valid_conditions    = {c for c, _ in CONDITION_CHOICES}
        valid_statuses      = {s for s, _ in STATUS_CHOICES}

        created_count = 0
        skipped = []

        for i, row in enumerate(rows[1:], start=2):
            if all(v is None or str(v).strip() == '' for v in row):
                continue

            item_type     = item_type_override or col(row, 'item_type').lower()
            model         = model_override or col(row, 'model')
            serial_number = col(row, 'serial_number')
            item_number   = col(row, 'item_number')
            property_num  = col(row, 'property_number') or None
            factory_qr    = col(row, 'factory_qr') or None
            condition     = col(row, 'item_condition', 'Serviceable')
            status        = col(row, 'item_status', 'Available')
            description   = col(row, 'description') or None

            row_errors = []

            if item_type not in ('pistol', 'rifle'):
                row_errors.append(f'unknown item_type "{item_type}" (use pistol or rifle)')
            else:
                valid_models = valid_pistol_models if item_type == 'pistol' else valid_rifle_models
                if model not in valid_models:
                    row_errors.append(f'invalid model "{model}"')

            if not serial_number:
                row_errors.append('serial_number required')
            if not item_number:
                row_errors.append('item_number required')
            if condition not in valid_conditions:
                condition = 'Serviceable'
            if status not in valid_statuses:
                status = 'Available'
            # Issued status must come from Transactions, never from bulk import.
            if status == 'Issued':
                status = 'Available'

            # Pad item_number to 4 digits if numeric
            if item_number and item_number.isdigit():
                item_number = f'{int(item_number):04d}'

            # Uniqueness checks (skip if earlier errors already flagged this row)
            if not row_errors:
                if item_type == 'pistol':
                    if Pistol.objects.filter(serial_number=serial_number).exists():
                        row_errors.append(f'serial_number {serial_number} already registered')
                    elif Pistol.objects.filter(model=model, item_number=item_number).exists():
                        row_errors.append(f'item_number {item_number} already used for {model}')
                    elif property_num and Pistol.objects.filter(property_number=property_num).exists():
                        row_errors.append(f'property_number {property_num} already registered')
                else:
                    if Rifle.objects.filter(serial_number=serial_number).exists():
                        row_errors.append(f'serial_number {serial_number} already registered')
                    elif Rifle.objects.filter(model=model, item_number=item_number).exists():
                        row_errors.append(f'item_number {item_number} already used for {model}')
                    elif property_num and Rifle.objects.filter(property_number=property_num).exists():
                        row_errors.append(f'property_number {property_num} already registered')
                    if model == 'M4 Carbine DSAR-15 5.56mm' and not factory_qr:
                        row_errors.append('factory_qr required for M4 Carbine DSAR-15 5.56mm')

            if row_errors:
                skipped.append(f'Row {i}: {"; ".join(row_errors)}')
                continue

            try:
                if item_type == 'pistol':
                    obj = Pistol(
                        model          = model,
                        serial_number  = serial_number,
                        item_number    = item_number,
                        property_number= property_num,
                        item_condition = condition,
                        item_status    = status,
                        description    = description,
                    )
                else:
                    obj = Rifle(
                        model          = model,
                        serial_number  = serial_number,
                        item_number    = item_number,
                        property_number= property_num,
                        factory_qr     = factory_qr,
                        item_condition = condition,
                        item_status    = status,
                        description    = description,
                    )
                obj.save(user=request.user)
                created_count += 1
            except Exception as exc:
                skipped.append(f'Row {i}: {exc}')

        if created_count:
            messages.success(request, f'Successfully imported {created_count} item(s).')
        if skipped:
            for msg in skipped[:20]:
                messages.warning(request, msg)
            if len(skipped) > 20:
                messages.warning(request, f'…and {len(skipped) - 20} more skipped rows.')
        if not created_count and not skipped:
            messages.info(request, 'No data rows found in the file.')
        return redirect('pistol-list')

