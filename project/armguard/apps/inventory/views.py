import json
from django.views.generic import ListView, View
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib import messages
from django.shortcuts import redirect
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
        qs = Pistol.objects.select_related('item_issued_to', 'item_assigned_to').order_by('model', 'serial_number')
        q = self.request.GET.get('q', '').strip()
        status = self.request.GET.get('status', '').strip()
        if q:
            qs = qs.filter(Q(serial_number__icontains=q) | Q(model__icontains=q) | Q(item_id__icontains=q))
        if status:
            qs = qs.filter(item_status=status)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['q'] = self.request.GET.get('q', '')
        ctx['selected_status'] = self.request.GET.get('status', '')
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

    def get_queryset(self):
        qs = Rifle.objects.select_related('item_issued_to', 'item_assigned_to').order_by('model', 'serial_number')
        q = self.request.GET.get('q', '').strip()
        status = self.request.GET.get('status', '').strip()
        if q:
            qs = qs.filter(Q(serial_number__icontains=q) | Q(model__icontains=q) | Q(item_id__icontains=q))
        if status:
            qs = qs.filter(item_status=status)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['q'] = self.request.GET.get('q', '')
        ctx['selected_status'] = self.request.GET.get('status', '')
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
    """POST {item_type, model, serial_number} → returns a live preview PNG of the item tag."""
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
            item.item_number = None
            item.qr_code_image = None
            item.get_item_type_display = lambda: {'pistol': 'Pistol', 'rifle': 'Rifle'}.get(item.item_type, 'Item')

            img = _build_tag(item)
            buf = io.BytesIO()
            img.save(buf, 'PNG')
            buf.seek(0)
            return HttpResponse(buf.read(), content_type='image/png')
        except Exception as exc:
            _log.exception('ItemTagPreviewView failed: %s', exc)
            return HttpResponse(f'Preview error: {exc}', content_type='text/plain', status=500)


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

