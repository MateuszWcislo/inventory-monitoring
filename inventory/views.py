from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.db import transaction
from django.db.models import Q, Sum, F

from .models import Product, ProductBatch, ProductSupplier
from .forms import ProductForm, SupplierFormSet, BatchFormSet
from orders.models import Order
from suppliers.models import Supplier
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
# inventory/views.py

def product_create(request):
    if request.method == "POST":
        form = ProductForm(request.POST)
        supp_formset = SupplierFormSet(request.POST, prefix='suppliers')
        batch_formset = BatchFormSet(request.POST, prefix='batches')

        if form.is_valid() and supp_formset.is_valid() and batch_formset.is_valid():
            # 1. Najpierw zapisujemy produkt, ale bez commit, by dodać tenant
            product = form.save(commit=False)
            product.tenant = request.user.tenant
            product.save()

            # 2. Powiązujemy formset dostawców z nowym produktem
            suppliers = supp_formset.save(commit=False)
            for instance in suppliers:
                instance.product = product  # Kluczowe powiązanie!
                instance.tenant = request.user.tenant
                instance.save()

            # Ważne: jeśli używamy commit=False, musimy ręcznie obsłużyć usuwanie (jeśli dotyczy create)
            supp_formset.save_m2m()

            # 3. Powiązujemy formset partii (batches) z nowym produktem
            batches = batch_formset.save(commit=False)
            for instance in batches:
                instance.product = product  # Kluczowe powiązanie!
                instance.tenant = request.user.tenant
                instance.save()

            batch_formset.save_m2m()

            return HttpResponse(status=204, headers={'HX-Trigger': 'productChanged'})
        else:
            print("BŁĘDY FORMULARZA:", form.errors)
            print("BŁĘDY DOSTAWCÓW:", supp_formset.errors)  # To pokaże "This field is required" dla tenanta
            print("BŁĘDY PARTII:", batch_formset.errors)
    else:
        form = ProductForm()
        supp_formset = SupplierFormSet(prefix='suppliers')
        batch_formset = BatchFormSet(prefix='batches')

    return render(request, 'inventory/partials/product_form.html', {
        'form': form,
        'supp_formset': supp_formset,
        'batch_formset': batch_formset,
        'title': 'Dodaj nowy produkt'
    })

@login_required
def product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk, tenant=request.user.tenant)
    if request.method == "POST":
        form = ProductForm(request.POST, instance=product)
        supp_formset = SupplierFormSet(request.POST, instance=product, prefix='suppliers')
        batch_formset = BatchFormSet(request.POST, instance=product, prefix='batches')

        if form.is_valid() and supp_formset.is_valid() and batch_formset.is_valid():
            form.save()
            # Zapisanie formsetów z wymuszeniem tenanta dla nowych wpisów
            for fs in [supp_formset, batch_formset]:
                instances = fs.save(commit=False)
                for obj in instances:
                    obj.tenant = request.user.tenant
                    obj.save()
                for obj in fs.deleted_objects:
                    obj.delete()

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

# @login_required
# def product_delete(request, pk):
#     product = get_object_or_404(Product, pk=pk, tenant=request.user.tenant)
#
#     if request.method == "POST":
#         product.delete()
#         # Zwracamy pustą odpowiedź z triggerem do HTMX, aby odświeżyć listę
#         return HttpResponse(status=204, headers={'HX-Trigger': 'productChanged'})
#
#     # Renderujemy mały formularz potwierdzenia do modala
#     return render(request, 'inventory/partials/confirm_delete.html', {
#         'product': product
#     })

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


# --- DODAWANIE DO ZAMÓWIENIA (LOGIKA) ---
@login_required
def add_to_order_modal(request, pk):
    product = get_object_or_404(Product, pk=pk, tenant=request.user.tenant)
    # Pobieramy dostępnych dostawców dla tego produktu
    mappings = product.supplier_mappings.all()

    return render(request, 'inventory/partials/add_to_order_form.html', {
        'product': product,
        'mappings': mappings,
    })


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
    mappings = product.supplier_mappings.select_related('supplier')
    return render(request, 'inventory/partials/add_to_order_form.html', {
        'product': product,
        'mappings': mappings
    })


@login_required
def add_to_order_save(request, pk):
    if request.method == "POST":
        product = get_object_or_404(Product, pk=pk, tenant=request.user.tenant)
        supplier_id = request.POST.get('supplier_id')
        quantity = int(request.POST.get('quantity', 1))

        last_batch = product.batches.last()
        suggested_price = last_batch.net_price if last_batch else 0

        with transaction.atomic():
            Order.objects.create(
                tenant=request.user.tenant,
                product=product,
                supplier_id=supplier_id,
                quantity=quantity,
                net_price=suggested_price,
                order_type='MANUAL',
                status='CREATED'
            )
        return HttpResponse(status=204, headers={'HX-Trigger': 'ordersChanged'})


@login_required
def bulk_add_to_order_save(request):
    if request.method == "POST":
        raw_ids = request.POST.get('product_ids', '')
        product_ids = [pid for pid in raw_ids.split(',') if pid]

        # UWAGA: W wersji zbiorczej upewnij się, że formularz wysyła supplier_id
        supplier_id = request.POST.get('supplier_id')

        with transaction.atomic():
            for p_id in product_ids:
                product = Product.objects.get(id=p_id, tenant=request.user.tenant)
                needed_qty = max(1, product.min_threshold - product.total_stock)
                last_price = Order.objects.filter(product=product, status='COMPLETED').last()
                price = last_price.net_price if last_price else 0

                Order.objects.create(
                    tenant=request.user.tenant,
                    product=product,
                    supplier_id=supplier_id,
                    quantity=needed_qty,
                    net_price=price,
                    order_type='MANUAL',
                    status='CREATED'
                )

        trigger_data = {"ordersChanged": None, "clearProductChecks": None, "showToast": "Utworzono zamówienia."}
        return HttpResponse(status=204, headers={'HX-Trigger': json.dumps(trigger_data)})


@login_required
def bulk_add_to_order_modal(request):
    """Potrzebne, bo masz to w urls.py"""
    product_ids = request.POST.getlist('product_ids')
    products = Product.objects.filter(id__in=product_ids, tenant=request.user.tenant)
    # Prosta logika: bierzemy wszystkich dostawców z systemu dla wyboru
    suppliers = Supplier.objects.filter(tenant=request.user.tenant)

    return render(request, 'inventory/partials/bulk_add_form.html', {
        'products': products,
        'suppliers': suppliers,
        'product_ids': ",".join(map(str, product_ids))
    })

@login_required
def add_supplier_row(request):
    # Tworzymy formę z domyślnym tenantem
    formset = SupplierFormSet(queryset=ProductSupplier.objects.none(), prefix='suppliers')
    empty_form = formset.empty_form
    empty_form.fields['tenant'].initial = request.user.tenant  # Ustawienie tenanta

    return render(request, 'inventory/partials/formset_row.html', {
        'form': empty_form,
        'prefix': 'suppliers'
    })

@login_required
def add_batch_row(request):
    formset = BatchFormSet(queryset=ProductBatch.objects.none(), prefix='batches')
    empty_form = formset.empty_form
    empty_form.fields['tenant'].initial = request.user.tenant  # Ustawienie tenanta

    return render(request, 'inventory/partials/formset_row.html', {
        'form': empty_form,
        'prefix': 'batches'
    })