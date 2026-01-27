from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.db import transaction
from .models import Order, OrderItem
from .forms import OrderForm, OrderItemFormSet
from django.urls import reverse
import json

@login_required
def order_list(request):
    orders = Order.objects.all().select_related('supplier').order_by('-status','-id')
    if request.headers.get('HX-Request'):
        return render(request, 'orders/partials/order_table.html', {'orders': orders})
    return render(request, 'orders/order_list.html', {'orders': orders})


@login_required
def order_create(request):
    if request.method == "POST":
        form = OrderForm(request.POST)
        formset = OrderItemFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                # Tworzymy obiekt, ale jeszcze nie zapisujemy w bazie
                order = form.save(commit=False)
                # Wymuszamy status OPEN, niezależnie od tego co wysłał formularz 🛡️
                order.status = 'OPEN'
                order.save()

                formset.instance = order
                formset.save()
            return HttpResponse("", headers={'HX-Trigger': 'ordersChanged'})
    else:
        form = OrderForm()
        formset = OrderItemFormSet()

    return render(request, 'orders/partials/order_form.html', {
        'form': form,
        'formset': formset,
        'order': None
    })


@login_required
def order_edit(request, pk):
    # Pobieramy zamówienie wraz z produktami (dla wydajności prefetch_related)
    order = get_object_or_404(Order.objects.prefetch_related('items__product'), pk=pk)

    # 1. Sprawdzamy status. Jeśli nie jest OTWARTY, przekierowujemy na podgląd 👁️
    if order.status != 'OPEN':
        return render(request, 'orders/partials/order_detail.html', {'order': order})

    # 2. Logika dla zamówień OTWARTYCH (bez zmian)
    if request.method == "POST":
        form = OrderForm(request.POST, instance=order)
        formset = OrderItemFormSet(request.POST, instance=order)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                updated_order = form.save()
                formset.save()
                if updated_order.status == 'CLOSED':
                    update_stock_on_closure(updated_order)
            return HttpResponse("", headers={'HX-Trigger': 'ordersChanged'})
    else:
        form = OrderForm(instance=order)
        formset = OrderItemFormSet(instance=order)

    return render(request, 'orders/partials/order_form.html', {
        'form': form,
        'formset': formset,
        'order': order
    })


@login_required
def order_preview(request, pk):
    order = get_object_or_404(Order.objects.prefetch_related('items__product'), pk=pk)
    return render(request, 'orders/partials/order_detail.html', {'order': order})


@login_required
def order_delete(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if request.method == "POST":
        order.delete()
        return HttpResponse("", headers={'HX-Trigger': 'ordersChanged'})
    return render(request, 'orders/partials/confirm_delete_order.html', {'order': order})


def update_stock_on_closure(order):
    for item in order.items.all():
        product = item.product
        product.current_stock += item.quantity
        product.save()


@login_required
def order_copy(request, pk):
    original_order = get_object_or_404(Order, id=pk)
    original_id = original_order.id

    with transaction.atomic():
        # Tworzymy kopię
        new_order = original_order
        new_order.id = None
        new_order.status = 'OPEN'
        new_order.completed_at = None
        new_order.save()

        # Kopiujemy pozycje
        items_to_copy = OrderItem.objects.filter(order_id=original_id)
        for item in items_to_copy:
            OrderItem.objects.create(
                order=new_order,
                product=item.product,
                quantity=item.quantity
            )

    # Zamiast redirect(), tworzymy odpowiedź sterowaną przez HTMX
    response = HttpResponse(status=200)

    # 1. Mówimy HTMX, gdzie ma przejść i co podmienić (modal)
    response['HX-Location'] = json.dumps({
        'path': reverse('order_list'),  # Kierujemy na /orders
        'target': '#order-table-container'  # Opcjonalnie: cel odświeżenia
    })

    # 2. Wysyłamy sygnał do odświeżenia listy i licznika w tle
    response['HX-Trigger'] = 'ordersChanged'

    return response


def order_count(request):
    # Liczymy tylko zamówienia o statusie 'OPEN'
    count = Order.objects.filter(status='OPEN').count()
    return render(request, 'orders/partials/order_count.html', {'orders_count': count})


@login_required
def order_bulk_delete(request):
    if request.method == "POST":
        # Pobieramy listę ID z checkboxów 📥
        order_ids = request.POST.getlist('order_ids')

        if order_ids:
            with transaction.atomic():
                # Usuwamy wybrane zamówienia 🗑️
                Order.objects.filter(id__in=order_ids).delete()

            # Zwracamy pustą odpowiedź z wyzwalaczem dla HTMX 🔔
            return HttpResponse("", headers={'HX-Trigger': 'ordersChanged'})

    # Jeśli coś pójdzie nie tak lub brak ID, po prostu odświeżamy tabelę
    return redirect('order_list')