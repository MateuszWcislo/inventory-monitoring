from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.db import transaction
from .models import Order, OrderItem
from .forms import OrderForm, OrderItemFormSet
from django.urls import reverse
import json
from suppliers.models import Supplier
from inventory.models import ActivityLog
from django.db.models import Prefetch
from django.views.decorators.http import require_http_methods

@login_required
def order_list(request):
    orders = Order.objects.all().select_related('supplier').order_by('-status','-id')
    if request.headers.get('HX-Request'):
        return render(request, 'orders/partials/order_table.html', {'orders': orders})
    return render(request, 'orders/order_list.html', {'orders': orders})


@login_required
def order_create(request):
    # Sprawdzamy dostawcę w POST (przy zapisie) LUB w GET (przy zmianie w select)
    supplier_id = request.POST.get('supplier') or request.GET.get('supplier')

    # Bezpieczne pobranie dostawcy (używamy filter, by uniknąć 404 przy braku wyboru)
    supplier = Supplier.objects.filter(id=supplier_id).first() if supplier_id else None

    if request.method == "POST" and not request.GET.get('refresh'):
        form = OrderForm(request.POST)
        formset = OrderItemFormSet(request.POST, form_kwargs={'supplier': supplier})

        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                order = form.save(commit=False)
                order.status = 'OPEN'
                order.save()
                formset.instance = order
                formset.save()
            return HttpResponse("", headers={'HX-Trigger': 'ordersChanged'})
    else:
        # Ten blok wykona się przy pierwszym wejściu ORAZ przy zmianie dostawcy przez HTMX
        form = OrderForm(initial={'supplier': supplier})
        formset = OrderItemFormSet(form_kwargs={'supplier': supplier})

    return render(request, 'orders/partials/order_form.html', {
        'form': form,
        'formset': formset,
        'order': None
    })


@login_required
@require_http_methods(["GET", "POST", "DELETE"])  # Pozwalamy na DELETE
def order_edit(request, pk):
    order = get_object_or_404(Order, pk=pk)

    # OBSŁUGA ANULOWANIA (USUWANIA)
    if request.method == "DELETE":
        order.delete()
        # Zwracamy pusty response z triggerem do odświeżenia listy za modalem
        return HttpResponse("", headers={'HX-Trigger': 'ordersChanged'})

    if order.status != 'OPEN':
        return render(request, 'orders/partials/order_detail.html', {'order': order})

    if request.method == "POST":
        old_status = order.status
        form = OrderForm(request.POST, instance=order)
        formset = OrderItemFormSet(
            request.POST,
            instance=order,
            form_kwargs={'supplier': order.supplier}
        )

        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                updated_order = form.save()
                formset.save()

                # LOGIKA ZAMYKANIA:
                # Sprawdzamy czy status zmienił się na CLOSED
                if old_status == 'OPEN' and updated_order.status == 'CLOSED':
                    # Wywołujemy aktualizację stanów TYLKO jeśli są produkty
                    if updated_order.items.exists():
                        update_stock_on_closure(request.user, updated_order)

            return HttpResponse("", headers={'HX-Trigger': 'ordersChanged'})

        # Jeśli walidacja nie przeszła, renderujemy formularz z błędami
        return render(request, 'orders/partials/order_form.html', {
            'form': form, 'formset': formset, 'order': order
        })

    # GET
    form = OrderForm(instance=order)
    formset = OrderItemFormSet(instance=order, form_kwargs={'supplier': order.supplier})
    return render(request, 'orders/partials/order_form.html', {
        'form': form, 'formset': formset, 'order': order
    })


@login_required
def order_preview(request, pk):
    # Pobieramy zamówienie, by poznać dostawcę
    order_instance = get_object_or_404(Order, pk=pk)

    # Tworzymy niestandardowy Prefetch, który filtruje pozycje po aktualnym asortymencie dostawcy
    items_prefetch = Prefetch(
        'items',
        queryset=OrderItem.objects.filter(
            product__in=order_instance.supplier.products.all()
        ).select_related('product')
    )

    # Pobieramy zamówienie ponownie z zastosowaniem filtra
    order = Order.objects.prefetch_related(items_prefetch).get(pk=pk)

    return render(request, 'orders/partials/order_detail.html', {'order': order})

@login_required
def order_delete(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if request.method == "POST":
        order.delete()
        return HttpResponse("", headers={'HX-Trigger': 'ordersChanged'})
    return render(request, 'orders/partials/confirm_delete_order.html', {'order': order})


def update_stock_on_closure(user,order):
    # Pobieramy pozycje bezpośrednio z bazy danych, omijając cache obiektu 'order'
    fresh_items = OrderItem.objects.filter(order=order)

    for item in fresh_items:
        product = item.product
        old_stock = product.current_stock
        product.current_stock += item.quantity
        product.save()

        desc = f"Zamknięcie zamówienia: {old_stock} -> {product.current_stock}."
        ActivityLog.objects.create(
            user=user,
            product_name=product.name,
            action_type='UPDATE',
            previous_stock=old_stock,
            current_stock=product.current_stock,
            description=desc
        )


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