from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import HttpResponse
from decimal import Decimal
from django.db import transaction
from django.db.models import Q
from django.contrib import messages

from .models import WorkOrder, WorkOrderProduct, WorkOrderService
from inventory.models import ProductBatch
from services.models import Service
from .forms import WorkOrderForm


@login_required
def work_order_list(request):
    search_query = request.GET.get('search', '')
    orders = WorkOrder.objects.filter(tenant=request.user.tenant)

    if search_query:
        orders = orders.filter(Q(name__icontains=search_query) | Q(client__icontains=search_query))

    context = {'orders': orders}

    if request.headers.get('HX-Request'):
        return render(request, 'work_orders/partials/order_table.html', context)
    return render(request, 'work_orders/order_list.html', context)


@login_required
def work_order_create(request):
    if request.method == "POST":
        form = WorkOrderForm(request.POST)
        if form.is_valid():
            order = form.save(commit=False)
            order.tenant = request.user.tenant
            order.save()
            return HttpResponse("", headers={'HX-Trigger': 'ordersChanged'})
    else:
        form = WorkOrderForm()

    return render(request, 'work_orders/partials/work_order_form.html', {
        'form': form,
        'title': 'Nowe zlecenie'
    })


@login_required
def work_order_detail(request, pk):
    """Główny widok edycji zlecenia - tutaj dodajemy produkty i usługi"""
    order = get_object_or_404(WorkOrder, pk=pk, tenant=request.user.tenant)
    can_edit = (order.status == 'IN_PROGRESS')
    all_batches = ProductBatch.objects.filter(
        tenant=request.user.tenant,
        current_stock__gt=0
    ).select_related('product')
    all_services = Service.objects.filter(tenant=request.user.tenant)

    context = {
        'order': order,
        'can_edit': can_edit,
        'batches': all_batches,
        'services': all_services,
    }
    return render(request, 'work_orders/work_order_detail.html', context)


@login_required
@require_POST
def work_order_complete(request, pk):
    """Szybka zmiana statusu na Zakończone"""
    order = get_object_or_404(WorkOrder, pk=pk, tenant=request.user.tenant)
    order.status = 'COMPLETED'
    order.save()
    return HttpResponse("", headers={'HX-Trigger': 'ordersChanged'})


@login_required
@require_POST
def add_product_item(request, pk):
    """Dodaje produkt do zlecenia, robi snapshot i zdejmuje ze stanu"""
    order = get_object_or_404(WorkOrder, pk=pk, tenant=request.user.tenant)
    if order.status != 'IN_PROGRESS':
        return HttpResponse("Zlecenie zamknięte", status=403)

    batch_id = request.POST.get('batch_id')
    try:
        quantity = int(request.POST.get('quantity', 1))
    except (ValueError, TypeError):
        quantity = 1

    if quantity <= 0:
        return HttpResponse("Nieprawidłowa ilość", status=400)

    batch = get_object_or_404(ProductBatch, id=batch_id, tenant=request.user.tenant)

    with transaction.atomic():
        if batch.current_stock >= quantity:
            vat = batch.product.vat_rate if batch.product else Decimal('23.00')
            WorkOrderProduct.objects.create(
                order=order,
                product_batch=batch,
                name_snapshot=batch.product.name,
                unit_price_net=batch.net_price,
                vat_rate=vat,
                quantity=quantity
            )
            batch.current_stock -= quantity
            batch.save()

    return HttpResponse("", headers={'HX-Trigger': 'orderUpdated'})


@login_required
@require_POST
def remove_product_item(request, item_id):
    """Usuwa produkt ze zlecenia i ZWRACA go na stan"""
    item = get_object_or_404(WorkOrderProduct, id=item_id, order__tenant=request.user.tenant)
    if item.order.status != 'IN_PROGRESS':
        return HttpResponse("Zlecenie zamknięte", status=403)

    with transaction.atomic():
        batch = item.product_batch
        if batch:
            batch.current_stock += item.quantity
            batch.save()
        item.delete()

    return HttpResponse("", headers={'HX-Trigger': 'orderUpdated'})


@login_required
@require_POST
def add_service_item(request, pk):
    """Dodaje usługę do zlecenia i robi snapshot"""
    order = get_object_or_404(WorkOrder, pk=pk, tenant=request.user.tenant)
    if order.status != 'IN_PROGRESS':
        return HttpResponse("Zlecenie zamknięte", status=403)

    service_id = request.POST.get('service_id')
    service_obj = get_object_or_404(Service, id=service_id, tenant=request.user.tenant)

    WorkOrderService.objects.create(
        order=order,
        service=service_obj,
        name_snapshot=service_obj.name,
        unit_price_net=service_obj.net_price,
        vat_rate=service_obj.vat_rate
    )
    return HttpResponse("", headers={'HX-Trigger': 'orderUpdated'})


@login_required
def get_product_picker(request, pk):
    """Zwraca listę produktów do modala"""
    order = get_object_or_404(WorkOrder, pk=pk, tenant=request.user.tenant)
    batches = ProductBatch.objects.filter(
        tenant=request.user.tenant,
        current_stock__gt=0
    ).select_related('product')
    return render(request, 'work_orders/partials/product_picker.html', {
        'order': order,
        'batches': batches
    })


@login_required
def get_service_picker(request, pk):
    """Zwraca listę usług do modala"""
    order = get_object_or_404(WorkOrder, pk=pk, tenant=request.user.tenant)
    services = Service.objects.filter(tenant=request.user.tenant)
    return render(request, 'work_orders/partials/service_picker.html', {
        'order': order,
        'services': services
    })


@login_required
@require_POST
def add_multiple_products(request, pk):
    order = get_object_or_404(WorkOrder, pk=pk, tenant=request.user.tenant)
    if order.status != 'IN_PROGRESS':
        return HttpResponse("Zlecenie zamknięte", status=403)

    batch_ids = request.POST.getlist('batch_ids')
    with transaction.atomic():
        for b_id in batch_ids:
            qty_str = request.POST.get(f'qty_{b_id}', '0')
            quantity = int(qty_str) if qty_str.isdigit() else 0

            if quantity > 0:
                batch = get_object_or_404(ProductBatch, id=b_id, tenant=request.user.tenant)

                if batch.current_stock >= quantity:
                    existing_item = WorkOrderProduct.objects.filter(order=order, product_batch=batch).first()
                    if existing_item:
                        existing_item.quantity += quantity
                        existing_item.save()
                    else:
                        vat = batch.product.vat_rate if batch.product else Decimal('23.00')
                        WorkOrderProduct.objects.create(
                            order=order,
                            product_batch=batch,
                            name_snapshot=batch.product.name,
                            unit_price_net=batch.net_price,
                            vat_rate=vat,
                            quantity=quantity
                        )
                    batch.current_stock -= quantity
                    batch.save()
    return HttpResponse("", headers={'HX-Trigger': 'orderUpdated'})


@login_required
@require_POST
def add_multiple_services(request, pk):
    order = get_object_or_404(WorkOrder, pk=pk, tenant=request.user.tenant)
    if order.status != 'IN_PROGRESS':
        return HttpResponse("Zlecenie zamknięte", status=403)

    service_ids = request.POST.getlist('service_ids')

    with transaction.atomic():
        for s_id in service_ids:
            qty_str = request.POST.get(f'qty_{s_id}', '0')
            quantity = int(qty_str) if qty_str.isdigit() else 0

            if quantity > 0:
                service_obj = get_object_or_404(Service, id=s_id, tenant=request.user.tenant)
                existing_item = WorkOrderService.objects.filter(
                    order=order,
                    service=service_obj,
                    unit_price_net=service_obj.net_price
                ).first()

                if existing_item:
                    existing_item.quantity += quantity
                    existing_item.save()
                else:
                    WorkOrderService.objects.create(
                        order=order,
                        service=service_obj,
                        name_snapshot=service_obj.name,
                        unit_price_net=service_obj.net_price,
                        vat_rate=service_obj.vat_rate,
                        quantity=quantity
                    )
    return HttpResponse("", headers={'HX-Trigger': 'orderUpdated'})


@login_required
@require_POST
def update_product_quantity(request, item_id):
    item = get_object_or_404(WorkOrderProduct, id=item_id, order__tenant=request.user.tenant)
    if item.order.status != 'IN_PROGRESS':
        return HttpResponse("Zlecenie zamknięte", status=403)

    batch = item.product_batch
    old_qty = item.quantity

    try:
        new_qty = int(request.POST.get('quantity', old_qty))
    except (ValueError, TypeError):
        new_qty = old_qty

    if new_qty <= 0:
        return HttpResponse(str(old_qty), status=400)

    if not batch:
        item.quantity = new_qty
        item.save()
        return HttpResponse(str(item.quantity), headers={'HX-Trigger': 'orderUpdated'})

    diff = new_qty - old_qty

    if diff > 0 and batch.current_stock < diff:
        response = HttpResponse(str(old_qty), status=400)
        response['HX-Trigger'] = 'qtyError'
        return response

    with transaction.atomic():
        if diff > 0:
            batch.current_stock -= diff
        else:
            batch.current_stock += abs(diff)

        item.quantity = new_qty
        batch.save()
        item.save()

    return HttpResponse(str(item.quantity), headers={'HX-Trigger': 'orderUpdated'})


@login_required
@require_POST
def update_service_quantity(request, item_id):
    item = get_object_or_404(WorkOrderService, id=item_id, order__tenant=request.user.tenant)
    if item.order.status != 'IN_PROGRESS':
        return HttpResponse("Zlecenie zamknięte", status=403)

    try:
        new_qty = int(request.POST.get('quantity', item.quantity))
    except (ValueError, TypeError):
        new_qty = item.quantity

    if new_qty <= 0:
        return HttpResponse(status=400)

    item.quantity = new_qty
    item.save()
    return HttpResponse("", headers={'HX-Trigger': 'orderUpdated'})


@login_required
@require_POST
def remove_service_item(request, item_id):
    """Usuwa usługę ze zlecenia (bez wpływu na magazyn)"""
    item = get_object_or_404(WorkOrderService, id=item_id, order__tenant=request.user.tenant)
    if item.order.status != 'IN_PROGRESS':
        return HttpResponse("Zlecenie zamknięte", status=403)
    item.delete()
    return HttpResponse("", headers={'HX-Trigger': 'orderUpdated'})


@login_required
def work_order_delete(request, pk):
    order = get_object_or_404(WorkOrder, pk=pk, tenant=request.user.tenant)

    if request.method == 'POST':
        with transaction.atomic():
            # Zwrot towarów na magazyn tylko gdy zlecenie było aktywne
            if order.status == 'IN_PROGRESS':
                for item in order.items.all():
                    batch = item.product_batch
                    if batch:
                        batch.current_stock += item.quantity
                        batch.save()

            order.delete()

        if request.headers.get('HX-Request'):
            return HttpResponse("", status=200)

        messages.success(request, "Zlecenie usunięte.")
        return redirect('work_order_list')

    return HttpResponse(status=405)


@login_required
@require_POST
def update_order_description(request, pk):
    order = get_object_or_404(WorkOrder, pk=pk, tenant=request.user.tenant)
    if order.status == 'IN_PROGRESS':
        order.description = request.POST.get('description', '')
        order.save()
    return HttpResponse(order.description)
