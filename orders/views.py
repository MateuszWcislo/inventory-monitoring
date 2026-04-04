from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.db import transaction, models
from django.db.models import Case, When, Value, IntegerField
from django.views.decorators.http import require_POST
from .models import Order
from .forms import OrderForm
from suppliers.models import Supplier
from inventory.models import Product, ProductBatch

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
            # order.order_type jest już ustawione na MANUAL w init formularza
            order.save()
            return HttpResponse("", headers={'HX-Trigger': 'ordersChanged'})
    else:
        form = OrderForm(user=request.user)

    # Dodaj pusty obiekt 'order', aby szablon wiedział, że to tworzenie (id będzie None)
    return render(request, 'orders/partials/order_form.html', {
        'form': form,
        'order': None
    })


@login_required
def order_edit(request, pk):
    order = get_object_or_404(Order, pk=pk, tenant=request.user.tenant)
    old_status = order.status # Zapamiętujemy status sprzed edycji

    if request.method == "POST":
        form = OrderForm(request.POST, instance=order, user=request.user)
        if form.is_valid():
            # Zapisujemy formularz do obiektu, ale jeszcze nie do bazy
            order = form.save(commit=False)

            # Logika magazynowa: sprawdzamy, czy użytkownik właśnie zmienił status na COMPLETED
            if order.status == 'COMPLETED' and old_status != 'COMPLETED':
                update_inventory_stock(order, request.user.tenant)

            order.save()
            return HttpResponse("", headers={'HX-Trigger': 'ordersChanged'})
    else:
        form = OrderForm(instance=order, user=request.user)

    return render(request, 'orders/partials/order_form.html', {'form': form, 'order': order})

@login_required
def order_delete(request, pk):
    order = get_object_or_404(Order, pk=pk, tenant=request.user.tenant)

    if request.method == "POST":
        order.delete()
        # Zwracamy pustą odpowiedź z triggerem do odświeżenia listy
        return HttpResponse("", headers={'HX-Trigger': 'ordersChanged'})

    # Dla GET zwracamy partial z pytaniem o potwierdzenie
    return render(request, 'orders/partials/confirm_delete.html', {'order': order})

@login_required
def get_filtered_options(request):
    product_id = request.GET.get('product')
    supplier_id = request.GET.get('supplier')
    tenant = request.user.tenant

    context = {
        'selected_product': product_id,
        'selected_supplier': supplier_id,
    }

    if product_id:
        # Tutaj sprawdź w modelu Supplier, jak nazywa się relacja do produktów.
        # Jeśli dostajesz błąd, spróbuj 'product_mappings' lub 'productsupplier_set'
        context['suppliers'] = Supplier.objects.filter(
            product_mappings__product_id=product_id, # Upewnij się, że w Supplier jest product_mappings
            tenant=tenant
        ).distinct()

    if supplier_id:
        # POPRAWKA TUTAJ: Zmieniamy na supplier_mappings zgodnie z błędem z konsoli
        context['products'] = Product.objects.filter(
            supplier_mappings__supplier_id=supplier_id,
            tenant=tenant
        ).distinct()

    return render(request, 'orders/partials/filtered_options.html', context)


def update_inventory_stock(order, tenant):
    """
    Aktualizacja stanów: szuka Batcha o tym samym produkcie i cenie.
    Dostawca nie jest brany pod uwagę przy grupowaniu partii.
    """
    if not order.product:
        return

    # Szukamy istniejącego batcha tylko po produkcie i cenach
    batch, created = ProductBatch.objects.get_or_create(
        product=order.product,
        tenant=tenant,
        purchase_price=order.net_price,
        gross_price=order.gross_price,
        defaults={'quantity': order.quantity}
    )

    if not created:
        # Jeśli partia o tej cenie już istnieje, po prostu zwiększamy jej stan
        batch.quantity += order.quantity
        batch.save()

    # Wywołujemy save na produkcie, aby odświeżyć property total_stock
    # i sprawdzić, czy nie trzeba usunąć innych auto-szkiców zamówień
    order.product.save()


@login_required
@require_POST
def order_status_update(request, pk):
    order = get_object_or_404(Order, pk=pk, tenant=request.user.tenant)
    new_status = request.POST.get('status')

    if new_status in dict(Order.STATUS_CHOICES):
        old_status = order.status
        order.status = new_status

        if new_status == 'COMPLETED' and old_status != 'COMPLETED':
            # DOPASOWANIE PÓL: net_price zamiast purchase_price,
            # current_stock zamiast quantity (sprawdź to w swoim modelu!)
            batch, created = ProductBatch.objects.get_or_create(
                product=order.product,
                tenant=request.user.tenant,
                net_price=order.net_price,  # <--- POPRAWKA
                gross_price=order.gross_price,
                defaults={'current_stock': order.quantity}  # <--- POPRAWKA (jeśli to pole trzyma ilość)
            )

            if not created:
                # Jeśli partia istnieje, dodajemy nową ilość do obecnego stanu
                batch.current_stock += order.quantity
                batch.save()

            if order.product:
                order.product.save()  # Wyzwala przeliczenie stanów w produkcie

        order.save()
        return HttpResponse("", headers={'HX-Trigger': 'ordersChanged'})

    return HttpResponse(status=400)