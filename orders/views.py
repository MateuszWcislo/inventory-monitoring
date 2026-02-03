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
    orders = Order.objects.filter(tenant=request.user.tenant).select_related('supplier').order_by('-status','-number')
    if request.headers.get('HX-Request'):
        return render(request, 'orders/partials/order_table.html', {'orders': orders})
    return render(request, 'orders/order_list.html', {'orders': orders})


@login_required
def order_create(request):
    supplier_id = request.POST.get('supplier') or request.GET.get('supplier')
    supplier = Supplier.objects.filter(id=supplier_id, tenant=request.user.tenant).first() if supplier_id else None

    if request.method == "POST" and not request.GET.get('refresh'):
        form = OrderForm(request.POST)
        # KLUCZOWE: Musisz przekazać tenant i supplier również tutaj!
        formset = OrderItemFormSet(
            request.POST,
            form_kwargs={'supplier': supplier, 'tenant': request.user.tenant}
        )

        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                order = form.save(commit=False)
                order.tenant = request.user.tenant
                order.status = 'OPEN'
                order.save()

                formset.instance = order
                formset.save()

            return HttpResponse("", headers={'HX-Trigger': 'ordersChanged'})

    else:
        form = OrderForm(initial={'supplier': supplier})
        formset = OrderItemFormSet(
            form_kwargs={'supplier': supplier, 'tenant': request.user.tenant}
        )

    return render(request, 'orders/partials/order_form.html', {
        'form': form,
        'formset': formset,
        'supplier_id': str(supplier.id) if supplier else None,
    })


@login_required
@require_http_methods(["GET", "POST", "DELETE"])
def order_edit(request, pk):
    order = get_object_or_404(Order, pk=pk, tenant=request.user.tenant)

    if request.method == "DELETE":
        order.delete()
        return HttpResponse("", headers={'HX-Trigger': 'ordersChanged'})

    # Jeśli zamówienie nie jest otwarte, pokazujemy tylko podgląd (szczegóły)
    if order.status != 'OPEN':
        return render(request, 'orders/partials/order_detail.html', {'order': order})

    if request.method == "POST":
        # 1. PRZECHWYTUJEMY STATUS PRZED ZAPISZEM
        old_status = order.status

        form = OrderForm(request.POST, instance=order)
        formset = OrderItemFormSet(
            request.POST,
            instance=order,
            form_kwargs={
                'supplier': order.supplier,
                'tenant': request.user.tenant
            }
        )

        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                updated_order = form.save()
                formset.save()

                # 2. LOGIKA ZAMYKANIA: Porównujemy stary status z nowym
                if old_status == 'OPEN' and updated_order.status == 'CLOSED':
                    if updated_order.items.exists():
                        update_stock_on_closure(request.user, updated_order)

            return HttpResponse("", headers={'HX-Trigger': 'ordersChanged'})

        return render(request, 'orders/partials/order_form.html', {
            'form': form, 'formset': formset, 'order': order
        })

    # GET
    form = OrderForm(instance=order)
    formset = OrderItemFormSet(
        instance=order,
        form_kwargs={
            'supplier': order.supplier,
            'tenant': request.user.tenant  # <--- To naprawi puste linie w edycji
        }
    )
    return render(request, 'orders/partials/order_form.html', {
        'form': form, 'formset': formset, 'order': order
    })


@login_required
def order_preview(request, pk):
    # 1. Pobieramy zamówienie (już tutaj sprawdzamy tenanta)
    order_instance = get_object_or_404(Order, pk=pk, tenant=request.user.tenant)

    # 2. Prefetch: Wyciągamy tylko te pozycje, które należą do produktów
    #    przypisanych do tego dostawcy ORAZ należą do firmy użytkownika.
    items_prefetch = Prefetch(
        'items',
        queryset=OrderItem.objects.filter(
            product__in=order_instance.supplier.products.all(), # Twoja logika biznesowa
            product__tenant=request.user.tenant                 # Twoje bezpieczeństwo
        ).select_related('product')
    )

    # 3. Odświeżamy obiekt z nałożonym prefetchem
    order = Order.objects.prefetch_related(items_prefetch).get(pk=pk, tenant=request.user.tenant)

    return render(request, 'orders/partials/order_detail.html', {'order': order})

@login_required
def order_delete(request, pk):
    order = get_object_or_404(Order, pk=pk, tenant=request.user.tenant)
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
            tenant=user.tenant,
            user=user,
            product_name=product.name,
            action_type='UPDATE',
            previous_stock=old_stock,
            current_stock=product.current_stock,
            description=desc
        )


@login_required
def order_copy(request, pk):
    original_order = get_object_or_404(Order, id=pk, tenant=request.user.tenant)

    with transaction.atomic():
        # Tworzymy zupełnie nowy obiekt na bazie danych starego
        new_order = Order.objects.create(
            tenant=request.user.tenant,
            supplier=original_order.supplier,
            status='OPEN'
            # number nada się automatycznie dzięki naszej metodzie save()
        )

        # Kopiujemy pozycje (OrderItem nie ma pola tenant, filtrujemy po order)
        items_to_copy = OrderItem.objects.filter(order=original_order)
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
    count = Order.objects.filter(status='OPEN', tenant=request.user.tenant).count()
    return render(request, 'orders/partials/order_count.html', {'orders_count': count})


@login_required
def order_bulk_delete(request):
    if request.method == "POST":
        # Pobieramy listę ID z checkboxów 📥
        order_ids = request.POST.getlist('order_ids')

        if order_ids:
            with transaction.atomic():
                # Usuwamy wybrane zamówienia 🗑️
                Order.objects.filter(id__in=order_ids, tenant=request.user.tenant).delete()

            # Zwracamy pustą odpowiedź z wyzwalaczem dla HTMX 🔔
            return HttpResponse("", headers={'HX-Trigger': 'ordersChanged'})

    # Jeśli coś pójdzie nie tak lub brak ID, po prostu odświeżamy tabelę
    return redirect('order_list')