from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.db import transaction
from django.db.models import Q, Sum, F

from .models import Product, ProductBatch, ProductSupplier
from .forms import ProductForm, SupplierFormSet, BatchFormSet
from orders.models import Order
from suppliers.models import Supplier
from orders.utils import process_auto_order_logic
import json

@login_required
def product_list(request):
    # 1. Pobieramy bazowy QuerySet z wyliczonym stanem (do sortowania)
    products = Product.objects.filter(tenant=request.user.tenant).annotate(
        computed_total_stock=Sum('batches__current_stock')
    )

    # 2. POBIERANIE PARAMETRÓW
    query = request.GET.get('q', '').strip()
    supplier_id = request.GET.get('supplier', '')
    stock_filter = request.GET.get('stock', '')
    sort_by = request.GET.get('sort', 'name')
    direction = request.GET.get('direction', 'asc')

    # 3. FILTROWANIE
    if len(query) >= 3:
        products = products.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(supplier_mappings__supplier_sku__icontains=query)
        )

    if supplier_id:
        products = products.filter(supplier_mappings__supplier_id=supplier_id)

    if stock_filter == 'low':
        products = products.filter(computed_total_stock__lt=F('min_threshold'))
    elif stock_filter == 'out':
        products = products.filter(computed_total_stock__lte=0)

    # 4. SORTOWANIE
    sort_dict = {
        'name': 'name',
        'stock': 'computed_total_stock',
        'threshold': 'min_threshold'
    }
    order_field = sort_dict.get(sort_by, 'name')
    if direction == 'desc':
        order_field = f"-{order_field}"

    products = products.order_by(order_field).distinct()

    # 5. PRZYGOTOWANIE KONTEKSTU (zachowanie filtrów dla linków sortowania)
    qd = request.GET.copy()
    if 'sort' in qd: del qd['sort']
    if 'direction' in qd: del qd['direction']

    context = {
        'products': products,
        'suppliers': Supplier.objects.filter(tenant=request.user.tenant),
        'current_sort': sort_by,
        'current_direction': direction,
        'current_filters_params': qd.urlencode(),  # parametry bez sortowania
    }

    if request.headers.get('HX-Request'):
        return render(request, 'inventory/partials/product_table.html', context)
    return render(request, 'inventory/product_list.html', context)


@login_required
def home_redirect(request):
    return redirect('product_list')


# --- CRUD PRODUKTU ---
@login_required
def product_create(request):
    if request.method == "POST":
        form = ProductForm(request.POST)
        # Inicjalizujemy bez instance, bo produkt jeszcze nie istnieje
        supp_formset = SupplierFormSet(request.POST, prefix='suppliers')
        batch_formset = BatchFormSet(request.POST, prefix='batches')

        if form.is_valid() and supp_formset.is_valid() and batch_formset.is_valid():
            # 1. Zapisujemy produkt
            product = form.save(commit=False)
            product.tenant = request.user.tenant
            product.save()

            # 2. Zapisujemy dostawców
            # Ustawiamy instance ręcznie, żeby powiązać z nowym produktem
            supp_formset.instance = product
            suppliers = supp_formset.save(commit=False)
            for s in suppliers:
                s.tenant = request.user.tenant
                s.save()
            # To ważne dla usuniętych wierszy:
            supp_formset.save_m2m()

            # 3. Zapisujemy partie
            batch_formset.instance = product
            batches = batch_formset.save(commit=False)
            for b in batches:
                b.tenant = request.user.tenant
                b.save()
            batch_formset.save_m2m()

            return HttpResponse(status=204, headers={'HX-Trigger': 'productChanged'})
        else:
            # Jeśli są błędy, wyświetlamy je w konsoli do debugowania
            print("Błędy Formularza:", form.errors)
            print("Błędy Dostawców:", supp_formset.errors)
            print("Błędy Partii:", batch_formset.errors)
    else:
        form = ProductForm()
        supp_formset = SupplierFormSet(prefix='suppliers')
        batch_formset = BatchFormSet(prefix='batches')

    return render(request, 'inventory/partials/product_form.html', {
        'form': form,
        'supp_formset': supp_formset,
        'batch_formset': batch_formset,
        'title': 'Dodaj produkt'
    })


@login_required
def product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk, tenant=request.user.tenant)

    if request.method == "POST":
        form = ProductForm(request.POST, instance=product)
        supp_formset = SupplierFormSet(request.POST, instance=product, prefix='suppliers')
        batch_formset = BatchFormSet(request.POST, instance=product, prefix='batches')

        if form.is_valid() and supp_formset.is_valid() and batch_formset.is_valid():
            # 1. Zapisujemy produkt
            product = form.save()

            # 2. Zapisujemy dostawców
            # Używamy commit=True (domyślne), aby Django samo obsłużyło usuwanie rekordów
            # które mają zaznaczony checkbox DELETE.
            supp_instances = supp_formset.save(commit=False)

            # Ręcznie usuwamy obiekty zaznaczone do skasowania
            for obj in supp_formset.deleted_objects:
                obj.delete()

            for instance in supp_instances:
                instance.tenant = request.user.tenant
                instance.save()

            # 3. Zapisujemy partie (Batche)
            batch_instances = batch_formset.save(commit=False)

            # Ręcznie usuwamy partie zaznaczone do skasowania
            for obj in batch_formset.deleted_objects:
                obj.delete()

            for instance in batch_instances:
                instance.tenant = request.user.tenant
                instance.save()

            # --- KLUCZ: ODŚWIEŻENIE I LOGIKA AUTO ---
            # Po usunięciu batchy musimy wymusić przeliczenie stanu w bazie
            product.refresh_from_db()

            # Wywołujemy Twoją logikę z orders/utils.py
            process_auto_order_logic(product)

            return HttpResponse(status=204, headers={'HX-Trigger': 'productChanged'})
    else:
        form = ProductForm(instance=product)
        supp_formset = SupplierFormSet(instance=product, prefix='suppliers')
        batch_formset = BatchFormSet(instance=product, prefix='batches')

    return render(request, 'inventory/partials/product_form.html', {
        'form': form,
        'supp_formset': supp_formset,
        'batch_formset': batch_formset,
        'product': product,
        'title': f'Edytuj: {product.name}'
    })


@login_required
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk, tenant=request.user.tenant)
    if request.method == "POST":
        product.delete()
        response = HttpResponse("")
        response['HX-Trigger'] = 'productChanged'
        return response
    return render(request, 'inventory/partials/confirm_delete.html', {'product': product})


# --- AKCJE MASOWE (BULK) ---
@login_required
def product_bulk_delete(request):
    if request.method == "POST":
        ids = request.POST.getlist('product_ids')
        if ids:
            Product.objects.filter(id__in=ids, tenant=request.user.tenant).delete()
        return HttpResponse(status=204, headers={'HX-Trigger': 'productChanged'})
    return HttpResponse(status=400)





# --- LOGIKA STANÓW (BATCHES) ---

@login_required
def quick_update_batch_stock(request, batch_id):
    """Zmienione: zwraca 'p' zamiast 'product' dla zgodności z row.html"""
    batch = get_object_or_404(ProductBatch, id=batch_id, tenant=request.user.tenant)
    if request.method == "POST":
        new_stock = request.POST.get('new_stock')
        if new_stock is not None:
            batch.current_stock = int(new_stock)
            batch.save()

    # Przekazujemy 'p', bo w product_row.html używasz {{ p.name }} itp.
    return render(request, 'inventory/partials/product_row.html', {'p': batch.product})


# --- POMOCNICZE ---

@login_required
def toggle_favourite(request, pk):
    product = get_object_or_404(Product, pk=pk, tenant=request.user.tenant)
    product.is_favourite = not product.is_favourite
    product.save()

    # Przeładowuje całą tabelę (można też zoptymalizować do samego wiersza)
    products = Product.objects.filter(tenant=request.user.tenant).order_by('-is_favourite', 'name')
    return render(request, 'inventory/partials/product_table.html', {'products': products})

# --- ZAMÓWIENIA ---

@login_required
def add_to_order_modal(request, pk):
    product = get_object_or_404(Product, pk=pk, tenant=request.user.tenant)

    # Pobieramy ostatnie zamówienie, żeby podpowiedzieć dostawcę i cenę
    last_order = product.orders.filter(status='COMPLETED').order_by('-created_at').first()

    # Jeśli nie ma historii, bierzemy pierwszego przypisanego dostawcę (opcjonalnie)
    default_supplier = None
    if last_order:
        default_supplier = last_order.supplier
    else:
        # Zakładam, że relacja to product.supplier_mappings
        first_mapping = product.supplier_mappings.first()
        if first_mapping:
            default_supplier = first_mapping.supplier

    return render(request, 'inventory/partials/add_to_order_form.html', {
        'product': product,
        'last_order': last_order,
        'default_supplier': default_supplier,
        'suppliers': [m.supplier for m in product.supplier_mappings.all()]
    })

@login_required
def add_to_order_save(request, pk):
    if request.method == "POST":
        product = get_object_or_404(Product, id=pk, tenant=request.user.tenant)
        supplier_id = request.POST.get('supplier_id')

        # Tworzymy nowe, czyste zamówienie MANUAL
        Order.objects.create(
            product=product,
            tenant=request.user.tenant,
            supplier_id=supplier_id,
            quantity=request.POST.get('quantity'),
            net_price=request.POST.get('net_price'),
            gross_price=request.POST.get('gross_price'),
            order_type='MANUAL',
            status='CREATED'
        )
        return HttpResponse("", headers={'HX-Trigger': 'ordersChanged'})

def add_supplier_row(request):
    # Tworzymy formset - prefix musi zgadzać się z tym w widoku głównym
    formset = SupplierFormSet(queryset=ProductSupplier.objects.none(), prefix='suppliers')
    # Używamy empty_form zamiast forms[0] - to usuwa IndexError
    form = formset.empty_form

    # Przekazujemy tenant_id do początkowych danych formularza
    if hasattr(request.user, 'tenant') and request.user.tenant:
        form.initial['tenant'] = request.user.tenant.id

    return render(request, 'inventory/partials/formset_row.html', {
        'form': form,
        'prefix': 'suppliers'
    })


def add_batch_row(request):
    formset = BatchFormSet(queryset=ProductBatch.objects.none(), prefix='batches')
    form = formset.empty_form

    if hasattr(request.user, 'tenant') and request.user.tenant:
        form.initial['tenant'] = request.user.tenant.id

    return render(request, 'inventory/partials/formset_row.html', {
        'form': form,
        'prefix': 'batches'
    })