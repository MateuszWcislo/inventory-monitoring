from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.db import transaction, models
from .models import Order
from .forms import OrderForm
from suppliers.models import Supplier


@login_required
def order_list(request):
    status_filter = request.GET.get('status', '')
    search_query = request.GET.get('q', '')

    orders = Order.objects.filter(tenant=request.user.tenant).select_related('product', 'supplier')

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
        # Obsługa opcjonalnego supplier_id z GET (np. przycisk "Zamów u tego dostawcy")
        supplier_id = request.GET.get('supplier_id')
        initial = {'order_type': 'MANUAL'}
        if supplier_id:
            initial['supplier'] = get_object_or_404(Supplier, id=supplier_id, tenant=request.user.tenant)

        form = OrderForm(initial=initial, user=request.user)

    return render(request, 'orders/partials/order_form.html', {'form': form})


@login_required
def order_edit(request, pk):
    order = get_object_or_404(Order, pk=pk, tenant=request.user.tenant)

    if request.method == "POST":
        form = OrderForm(request.POST, instance=order, user=request.user)
        if form.is_valid():
            order = form.save()
            # Tutaj możesz dodać logikę aktualizacji stanu magazynowego,
            # jeśli status zmienił się na COMPLETED
            return HttpResponse("", headers={'HX-Trigger': 'ordersChanged'})
    else:
        form = OrderForm(instance=order, user=request.user)

    return render(request, 'orders/partials/order_form.html', {'form': form, 'order': order})


@login_required
def order_preview(request, pk):
    order = get_object_or_404(Order, pk=pk, tenant=request.user.tenant)
    return render(request, 'orders/partials/order_detail.html', {'order': order})


@login_required
def order_delete(request, pk):
    order = get_object_or_404(Order, pk=pk, tenant=request.user.tenant)
    if request.method == "POST":
        order.delete()
        return HttpResponse("", headers={'HX-Trigger': 'ordersChanged'})
    return render(request, 'orders/partials/confirm_delete_order.html', {'order': order})


@login_required
def order_bulk_delete(request):
    if request.method == "POST":
        order_ids = request.POST.getlist('order_ids')
        if order_ids:
            Order.objects.filter(id__in=order_ids, tenant=request.user.tenant).delete()
            return HttpResponse("", headers={'HX-Trigger': 'ordersChanged'})
    return redirect('order_list')

@login_required
def get_filtered_options(request):
    product_id = request.GET.get('product')
    supplier_id = request.GET.get('supplier')
    tenant = request.user.tenant

    context = {}

    # Jeśli wybrano produkt, filtrujemy dostawców
    if product_id:
        # Pobieramy dostawców powiązanych z produktem przez model ProductSupplier
        suppliers = Supplier.objects.filter(
            product_mappings__product_id=product_id,
            tenant=tenant
        ).distinct()
        context['suppliers'] = suppliers

    # Jeśli wybrano dostawcę, filtrujemy produkty
    if supplier_id:
        products = Product.objects.filter(
            supplier_mappings__supplier_id=supplier_id,
            tenant=tenant
        ).distinct()
        context['products'] = products

    return render(request, 'orders/partials/filtered_options.html', context)