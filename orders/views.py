from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.db import models
from django.db.models import Case, When, Value, IntegerField
from django.views.decorators.http import require_POST
from .models import Order
from .forms import OrderForm
from suppliers.models import Supplier


@login_required
def order_list(request):
    status_filter = request.GET.get('status', '')
    search_query = request.GET.get('q', '')

    orders = Order.objects.filter(tenant=request.user.tenant).annotate(
        status_group=Case(
            When(status__in=['CREATED', 'ORDERED'], then=Value(1)),
            When(status__in=['COMPLETED', 'CANCELLED'], then=Value(2)),
            output_field=IntegerField(),
        )
    ).order_by('status_group', '-created_at').select_related('product', 'supplier')

    if status_filter:
        orders = orders.filter(status=status_filter)

    if search_query:
        orders = orders.filter(
            models.Q(product_name_snapshot__icontains=search_query) |
            models.Q(supplier__name__icontains=search_query)
        )

    context = {
        'orders': orders,
        'status_filter': status_filter,
        'q': search_query,
        'status_choices': Order.STATUS_CHOICES
    }

    if request.headers.get('HX-Request'):
        return render(request, 'orders/partials/order_table.html', context)
    return render(request, 'orders/order_list.html', context)


@login_required
def order_create(request):
    if request.method == "POST":
        form = OrderForm(request.POST, user=request.user)
        if form.is_valid():
            order = form.save(commit=False)
            order.tenant = request.user.tenant
            order.save()
            return HttpResponse("", headers={'HX-Trigger': 'ordersChanged'})
    else:
        form = OrderForm(user=request.user)

    return render(request, 'orders/partials/order_form.html', {
        'form': form,
        'order': None,
        'is_edit': False
    })


@login_required
def order_edit(request, pk):
    order = get_object_or_404(Order, pk=pk, tenant=request.user.tenant)

    if request.method == "POST":
        form = OrderForm(request.POST, instance=order, user=request.user)
        if form.is_valid():
            order = form.save()
            return HttpResponse("", headers={'HX-Trigger': 'ordersChanged'})
    else:
        form = OrderForm(instance=order, user=request.user)

    return render(request, 'orders/partials/order_form.html', {
        'form': form,
        'order': order,
        'is_edit': True
    })


@login_required
def order_delete(request, pk):
    order = get_object_or_404(Order, pk=pk, tenant=request.user.tenant)

    if request.method == "POST":
        order.delete()
        return HttpResponse("", headers={'HX-Trigger': 'ordersChanged'})

    return render(request, 'orders/partials/confirm_delete.html', {'order': order})


@login_required
def get_filtered_suppliers(request):
    product_id = request.GET.get('product')
    tenant = request.user.tenant

    if not product_id:
        return HttpResponse('<option value="">--- Najpierw wybierz produkt ---</option>')

    suppliers = Supplier.objects.filter(
        tenant=tenant,
        product_mappings__product_id=product_id
    ).distinct()

    return render(request, 'orders/partials/supplier_options.html', {
        'suppliers': suppliers
    })


@login_required
@require_POST
def order_status_update(request, pk):
    order = get_object_or_404(Order, pk=pk, tenant=request.user.tenant)
    new_status = request.POST.get('status')

    allowed_transitions = {
        'CREATED': ['ORDERED', 'COMPLETED', 'CANCELLED'],
        'ORDERED': ['COMPLETED', 'CANCELLED'],
        'COMPLETED': [],
        'CANCELLED': ['CREATED'],
    }

    if new_status in allowed_transitions.get(order.status, []):
        order.status = new_status
        order.save()
        return HttpResponse("", headers={'HX-Trigger': 'ordersChanged'})

    return HttpResponse("Niedozwolona zmiana statusu", status=400)


@login_required
@require_POST
def order_reorder(request, pk):
    original_order = get_object_or_404(Order, pk=pk, tenant=request.user.tenant)

    Order.objects.create(
        tenant=original_order.tenant,
        product=original_order.product,
        supplier=original_order.supplier,
        quantity=original_order.quantity,
        net_price=original_order.net_price,
        gross_price=original_order.gross_price,
        order_type='MANUAL',
        status='CREATED'
    )

    return HttpResponse("", headers={'HX-Trigger': 'ordersChanged'})
