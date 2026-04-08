from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import HttpResponse
from decimal import Decimal
from django.db import transaction
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
        orders = orders.filter(models.Q(name__icontains=search_query) | models.Q(client__icontains=search_query))

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
            # Wysyłamy sygnał HTMX, żeby tabela na liście się odświeżyła
            return HttpResponse("", headers={'HX-Trigger': 'ordersChanged'})
    else:
        form = WorkOrderForm()

    return render(request, 'work_orders/partials/work_order_form.html', {
        'form': form,
        'title': 'Nowe zlecenie'
    })


@login_required
def work_order_detail(request, pk):
    order = get_object_or_404(WorkOrder, pk=pk, tenant=request.user.tenant)

    # Flaga logiczna: edycja dozwolona tylko gdy status to 'IN_PROGRESS'
    can_edit = (order.status == 'IN_PROGRESS')

    context = {
        'order': order,
        'can_edit': can_edit,
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
def work_order_detail(request, pk):
    """Główny widok edycji zlecenia - tutaj dodajemy produkty i usługi"""
    order = get_object_or_404(WorkOrder, pk=pk, tenant=request.user.tenant)
    all_batches = ProductBatch.objects.filter(tenant=request.user.tenant, current_stock__gt=0)
    all_services = Service.objects.filter(tenant=request.user.tenant)

    context = {
        'order': order,
        'batches': all_batches,
        'services': all_services,
    }
    return render(request, 'work_orders/work_order_detail.html', context)


@login_required
@require_POST
def add_product_item(request, pk):
    """Dodaje produkt do zlecenia, robi snapshot i zdejmuje ze stanu"""
    order = get_object_or_404(WorkOrder, pk=pk, tenant=request.user.tenant)
    batch_id = request.POST.get('batch_id')
    quantity = int(request.POST.get('quantity', 1))

    batch = get_object_or_404(ProductBatch, id=batch_id, tenant=request.user.tenant)

    if batch.current_stock >= quantity:
        # 1. Snapshot i stworzenie pozycji
        WorkOrderProduct.objects.create(
            order=order,
            product_batch=batch,
            name_snapshot=f"{batch.product.name} (Partia: {batch.batch_number})",
            unit_price_net=batch.net_price,
            vat_rate=Decimal('23.00'),  # Możesz tu pobrać VAT z produktu jeśli go dodasz
            quantity=quantity
        )

        # 2. Aktualizacja stanu magazynowego
        batch.current_stock -= quantity
        batch.save()

    return HttpResponse("", headers={'HX-Trigger': 'orderUpdated'})


@login_required
@require_POST
def remove_product_item(request, item_id):
    """Usuwa produkt ze zlecenia i ZWRACA go na stan"""
    item = get_object_or_404(WorkOrderProduct, id=item_id, order__tenant=request.user.tenant)
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
    service_id = request.POST.get('service_id')
    service_obj = get_object_or_404(Service, id=service_id, tenant=request.user.tenant)

    WorkOrderService.objects.create(
        order=order,
        service=service_obj,
        name_snapshot=service_obj.name,
        price_net=service_obj.net_price,
        vat_rate=service_obj.vat_rate
    )
    return HttpResponse("", headers={'HX-Trigger': 'orderUpdated'})


@login_required
def get_product_picker(request, pk):
    """Zwraca listę produktów do modala"""
    order = get_object_or_404(WorkOrder, pk=pk, tenant=request.user.tenant)
    batches = ProductBatch.objects.filter(tenant=request.user.tenant, current_stock__gt=0)
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
        return HttpResponse("Zlecenie jest zamknięte", status=403)

    # Pobieramy słownik id_partii -> ilość z POST
    batch_ids = request.POST.getlist('batch_ids')

    for b_id in batch_ids:
        qty_str = request.POST.get(f'qty_{b_id}', '0')
        quantity = int(qty_str) if qty_str.isdigit() else 0

        if quantity > 0:
            batch = get_object_or_404(ProductBatch, id=b_id, tenant=request.user.tenant)

            if batch.current_stock >= quantity:
                WorkOrderProduct.objects.create(
                    order=order,
                    product_batch=batch,
                    name_snapshot=f"{batch.product.name}",  # Usunąłem batch_number
                    unit_price_net=batch.net_price,
                    vat_rate=Decimal('23.00'),
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
        return HttpResponse("Zlecenie jest zamknięte", status=403)

    service_ids = request.POST.getlist('service_ids')

    for s_id in service_ids:
        # Pobieramy ilość dla danej usługi
        qty_str = request.POST.get(f'qty_{s_id}', '0')
        quantity = int(qty_str) if qty_str.isdigit() else 0

        if quantity > 0:
            service_obj = get_object_or_404(Service, id=s_id, tenant=request.user.tenant)
            WorkOrderService.objects.create(
                order=order,
                service=service_obj,
                name_snapshot=service_obj.name,
                price_net=service_obj.net_price,
                vat_rate=service_obj.vat_rate,
                quantity=quantity  # Zapisujemy ilość
            )
    return HttpResponse("", headers={'HX-Trigger': 'orderUpdated'})


@login_required
@require_POST
def remove_service_item(request, item_id):
    """Usuwa usługę ze zlecenia (bez wpływu na magazyn)"""
    item = get_object_or_404(WorkOrderService, id=item_id, order__tenant=request.user.tenant)
    item.delete()
    return HttpResponse("", headers={'HX-Trigger': 'orderUpdated'})


@login_required
def work_order_delete(request, pk):
    order = get_object_or_404(WorkOrder, pk=pk, tenant=request.user.tenant)

    if request.method == 'POST':
        with transaction.atomic():
            # 1. Logika zwrotu towarów na magazyn
            if order.status == 'IN_PROGRESS':
                for item in order.items.all():
                    batch = item.product_batch
                    if batch:
                        batch.current_stock += item.quantity
                        batch.save()

            # 2. Usunięcie zlecenia
            order.delete()

        # 3. Obsługa HTMX - jeśli to żądanie HTMX, zwróć pusty body
        if request.headers.get('HX-Request'):
            return HttpResponse("", status=200)

        # Dla zwykłych żądań (np. z przycisku wewnątrz edycji)
        messages.success(request, "Zlecenie usunięte.")
        return redirect('work_order_list')

    return HttpResponse(status=405)  # Tylko POST jest dozwolony