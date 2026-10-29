from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden
from django.db import transaction
from django.db.models import Q, Sum, F, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from decimal import Decimal

from .models import Product, ProductBatch, ProductSupplier, ActivityLog, Location, Stocktake, StocktakeItem
from .forms import (
    ProductForm, SupplierFormSet, BatchFormSet,
    LocationForm, StocktakeForm, StocktakeItemForm
)
from orders.models import Order
from suppliers.models import Supplier
from orders.utils import process_auto_order_logic


@login_required
def activity_log_list(request):
    """Widok globalnej historii aktywności."""
    logs = ActivityLog.objects.filter(tenant=request.user.tenant).select_related('product', 'product_batch', 'user')

    # Proste filtrowanie po produkcie
    product_id = request.GET.get('product')
    if product_id:
        logs = logs.filter(product_id=product_id)

    context = {
        'logs': logs,
        'products': Product.objects.filter(tenant=request.user.tenant).order_by('name'),
    }
    return render(request, 'inventory/activity_logs.html', context)


@login_required
def product_list(request):
    # 1. Pobieramy bazowy QuerySet z wyliczonym stanem (używając Coalesce dla produktów bez partii)
    location_id = request.GET.get('location', '')
    
    products = Product.objects.filter(tenant=request.user.tenant)

    if location_id:
        products = products.annotate(
            computed_total_stock=Coalesce(
                Sum('batches__current_stock', filter=Q(batches__location_id=location_id)),
                Value(0)
            )
        )
    else:
        products = products.annotate(
            computed_total_stock=Coalesce(Sum('batches__current_stock'), Value(0))
        )

    products = products.prefetch_related('batches__location', 'supplier_mappings__supplier')

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

    products = products.order_by('-is_favourite', order_field).distinct()

    # 5. PRZYGOTOWANIE KONTEKSTU (zachowanie filtrów dla linków sortowania)
    qd = request.GET.copy()
    if 'sort' in qd: del qd['sort']
    if 'direction' in qd: del qd['direction']

    context = {
        'products': products,
        'suppliers': Supplier.objects.filter(tenant=request.user.tenant),
        'locations': Location.objects.filter(tenant=request.user.tenant),
        'selected_location': location_id,
        'current_sort': sort_by,
        'current_direction': direction,
        'current_filters_params': qd.urlencode(),
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
        supp_formset = SupplierFormSet(request.POST, prefix='suppliers', tenant=request.user.tenant)
        batch_formset = BatchFormSet(request.POST, prefix='batches', tenant=request.user.tenant)

        if form.is_valid() and supp_formset.is_valid() and batch_formset.is_valid():
            with transaction.atomic():
                # 1. Zapisujemy produkt (z flagą _skip_signal, żeby nie tworzyć zamówienia przed zapisaniem partii)
                product = form.save(commit=False)
                product.tenant = request.user.tenant
                product._skip_signal = True
                product.save()

                # 2. Zapisujemy dostawców
                supp_formset.instance = product
                suppliers = supp_formset.save(commit=False)
                for s in suppliers:
                    s.tenant = request.user.tenant
                    s.save()
                supp_formset.save_m2m()

                # 3. Zapisujemy partie (z flagą _skip_signal)
                batch_formset.instance = product
                batches = batch_formset.save(commit=False)
                for b in batches:
                    b.tenant = request.user.tenant
                    b._skip_signal = True
                    b.save()
                batch_formset.save_m2m()

            # 4. Sprawdzamy stan magazynowy i ewentualne zamówienie automatyczne dopiero po zapisaniu całego formularza
            product.refresh_from_db()
            process_auto_order_logic(product)

            return HttpResponse(status=204, headers={'HX-Trigger': 'productChanged'})
    else:
        form = ProductForm()
        supp_formset = SupplierFormSet(prefix='suppliers', tenant=request.user.tenant)
        batch_formset = BatchFormSet(prefix='batches', tenant=request.user.tenant)

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
        supp_formset = SupplierFormSet(request.POST, instance=product, prefix='suppliers', tenant=request.user.tenant)
        batch_formset = BatchFormSet(request.POST, instance=product, prefix='batches', tenant=request.user.tenant)

        if form.is_valid() and supp_formset.is_valid() and batch_formset.is_valid():
            with transaction.atomic():
                product = form.save(commit=False)
                product._skip_signal = True
                product.save()

                supp_instances = supp_formset.save(commit=False)
                # Usuwamy powiązania zaznaczone do skasowania
                for obj in supp_formset.deleted_objects:
                    obj.delete()

                for instance in supp_instances:
                    instance.tenant = request.user.tenant
                    instance.save()
                supp_formset.save_m2m()

                batch_instances = batch_formset.save(commit=False)
                # Partie zaznaczone do skasowania
                for obj in batch_formset.deleted_objects:
                    obj.delete()

                for instance in batch_instances:
                    instance.tenant = request.user.tenant
                    instance._skip_signal = True
                    instance.save()
                batch_formset.save_m2m()

            # Po edycji przeliczamy zapotrzebowanie
            product.refresh_from_db()
            process_auto_order_logic(product)

            return HttpResponse(status=204, headers={'HX-Trigger': 'productChanged'})
    else:
        form = ProductForm(instance=product)
        supp_formset = SupplierFormSet(instance=product, prefix='suppliers', tenant=request.user.tenant)
        batch_formset = BatchFormSet(instance=product, prefix='batches', tenant=request.user.tenant)

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
    return render(request, 'inventory/partials/confirm_delete.html', {'product': product})\


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
    """Szybka edycja stanu partii bezpośrednio z listy"""
    batch = get_object_or_404(ProductBatch, id=batch_id, tenant=request.user.tenant)
    if request.method == "POST":
        new_stock = request.POST.get('new_stock')
        if new_stock is not None:
            try:
                batch.current_stock = max(0, int(new_stock))
                batch.save()
            except (ValueError, TypeError):
                pass

    # Pobieramy produkt z adnotacją, aby suma była dostępna w szablonie
    product = Product.objects.filter(pk=batch.product.pk).annotate(
        computed_total_stock=Coalesce(Sum('batches__current_stock'), Value(0))
    ).prefetch_related('batches').first()

    return render(request, 'inventory/partials/product_row.html', {'p': product})


# --- POMOCNICZE ---

@login_required
def toggle_favourite(request, pk):
    product = get_object_or_404(Product, pk=pk, tenant=request.user.tenant)
    product.is_favourite = not product.is_favourite
    product.save()

    products = Product.objects.filter(tenant=request.user.tenant).annotate(
        computed_total_stock=Coalesce(Sum('batches__current_stock'), Value(0))
    ).prefetch_related('batches', 'supplier_mappings__supplier').order_by('-is_favourite', 'name')
    return render(request, 'inventory/partials/product_table.html', {'products': products})


# --- ZAMÓWIENIA ---

@login_required
def add_to_order_modal(request, pk):
    product = get_object_or_404(Product, pk=pk, tenant=request.user.tenant)

    last_order = product.orders.filter(status='COMPLETED').order_by('-created_at').first()

    default_supplier = None
    if last_order:
        default_supplier = last_order.supplier
    else:
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

        supplier = None
        if supplier_id:
            supplier = get_object_or_404(Supplier, id=supplier_id, tenant=request.user.tenant)

        try:
            quantity = int(request.POST.get('quantity', 1))
            if quantity < 1:
                quantity = 1
        except (ValueError, TypeError):
            quantity = 1

        try:
            net_raw = str(request.POST.get('net_price', '0')).replace(',', '.')
            net_price = Decimal(net_raw) if net_raw else Decimal('0.00')
        except Exception:
            net_price = Decimal('0.00')

        try:
            gross_raw = str(request.POST.get('gross_price', '')).replace(',', '.')
            gross_price = Decimal(gross_raw) if gross_raw else None
        except Exception:
            gross_price = None

        Order.objects.create(
            product=product,
            tenant=request.user.tenant,
            supplier=supplier,
            quantity=quantity,
            net_price=net_price,
            gross_price=gross_price,
            order_type='MANUAL',
            status='CREATED'
        )
        return HttpResponse("", headers={'HX-Trigger': 'productChanged'})


def add_supplier_row(request):
    tenant = getattr(request.user, 'tenant', None) if request.user.is_authenticated else None
    formset = SupplierFormSet(queryset=ProductSupplier.objects.none(), prefix='suppliers', tenant=tenant)
    form = formset.empty_form

    if tenant:
        form.initial['tenant'] = tenant.id

    return render(request, 'inventory/partials/formset_row.html', {
        'form': form,
        'prefix': 'suppliers'
    })


def add_batch_row(request):
    tenant = getattr(request.user, 'tenant', None) if request.user.is_authenticated else None
    formset = BatchFormSet(queryset=ProductBatch.objects.none(), prefix='batches', tenant=tenant)
    form = formset.empty_form

    if tenant:
        form.initial['tenant'] = tenant.id

    return render(request, 'inventory/partials/formset_row.html', {
        'form': form,
        'prefix': 'batches'
    })


# --- MODUŁ LOKALIZACJI (MAGAZYNY) ---

@login_required
def location_list(request):
    locations = Location.objects.filter(tenant=request.user.tenant).annotate(
        batches_count=Sum('batches__current_stock')
    )
    return render(request, 'inventory/location_list.html', {
        'locations': locations
    })


@login_required
def location_create(request):
    if request.method == "POST":
        form = LocationForm(request.POST)
        if form.is_valid():
            loc = form.save(commit=False)
            loc.tenant = request.user.tenant
            loc.save()
            return redirect('location_list')
    else:
        form = LocationForm()

    return render(request, 'inventory/partials/location_form.html', {
        'form': form,
        'title': 'Dodaj magazyn'
    })


@login_required
def location_edit(request, pk):
    loc = get_object_or_404(Location, pk=pk, tenant=request.user.tenant)
    if request.method == "POST":
        form = LocationForm(request.POST, instance=loc)
        if form.is_valid():
            form.save()
            return redirect('location_list')
    else:
        form = LocationForm(instance=loc)

    return render(request, 'inventory/partials/location_form.html', {
        'form': form,
        'location': loc,
        'title': f'Edytuj magazyn: {loc.name}'
    })


@login_required
def location_delete(request, pk):
    loc = get_object_or_404(Location, pk=pk, tenant=request.user.tenant)
    # Sprawdzenie czy magazyn nie ma powiązanych partii ze stanem
    has_active_batches = loc.batches.filter(current_stock__gt=0).exists()
    if request.method == "POST":
        if has_active_batches:
            return HttpResponseForbidden("Nie można usunąć magazynu z aktywnymi stanami magazynowymi.")
        loc.delete()
        return redirect('location_list')

    return render(request, 'inventory/partials/confirm_delete_location.html', {
        'location': loc,
        'has_active_batches': has_active_batches
    })


# --- MODUŁ INWENTARYZACJI (STOCKTAKES) ---

@login_required
def stocktake_list(request):
    stocktakes = Stocktake.objects.filter(tenant=request.user.tenant).select_related('location', 'created_by')
    return render(request, 'inventory/stocktake_list.html', {
        'stocktakes': stocktakes
    })


@login_required
def stocktake_create(request):
    if request.method == "POST":
        form = StocktakeForm(request.POST, tenant=request.user.tenant)
        if form.is_valid():
            with transaction.atomic():
                stocktake = form.save(commit=False)
                stocktake.tenant = request.user.tenant
                stocktake.created_by = request.user
                stocktake.save()

                # Generowanie pozycji arkusza ze wszystkich produktów / partii wybranego magazynu (lub wszystkich)
                batches_qs = ProductBatch.objects.filter(tenant=request.user.tenant)
                if stocktake.location:
                    batches_qs = batches_qs.filter(location=stocktake.location)

                for batch in batches_qs.select_related('product'):
                    StocktakeItem.objects.create(
                        stocktake=stocktake,
                        product=batch.product,
                        batch=batch,
                        system_quantity=batch.current_stock or 0,
                        counted_quantity=batch.current_stock or 0
                    )

                # Dla produktów bez partii w danej lokalizacji
                products_without_batches = Product.objects.filter(tenant=request.user.tenant).exclude(
                    id__in=batches_qs.values_list('product_id', flat=True)
                )
                for prod in products_without_batches:
                    StocktakeItem.objects.create(
                        stocktake=stocktake,
                        product=prod,
                        batch=None,
                        system_quantity=0,
                        counted_quantity=0
                    )

            return redirect('stocktake_detail', pk=stocktake.pk)
    else:
        form = StocktakeForm(tenant=request.user.tenant)

    return render(request, 'inventory/partials/stocktake_form.html', {
        'form': form,
        'title': 'Nowa inwentaryzacja'
    })


@login_required
def stocktake_detail(request, pk):
    stocktake = get_object_or_404(Stocktake, pk=pk, tenant=request.user.tenant)
    items = stocktake.items.select_related('product', 'batch', 'batch__location').order_by('product__name')

    total_system = sum(item.system_quantity for item in items)
    total_counted = sum(item.counted_quantity for item in items)
    total_difference = total_counted - total_system

    context = {
        'stocktake': stocktake,
        'items': items,
        'total_system': total_system,
        'total_counted': total_counted,
        'total_difference': total_difference,
    }
    return render(request, 'inventory/stocktake_detail.html', context)


@login_required
def stocktake_item_update(request, item_id):
    item = get_object_or_404(StocktakeItem, pk=item_id, stocktake__tenant=request.user.tenant)
    if item.stocktake.status != 'DRAFT':
        return HttpResponseForbidden("Nie można edytować zamkniętej inwentaryzacji.")

    if request.method == "POST":
        counted_qty = request.POST.get('counted_quantity')
        notes = request.POST.get('notes', '')
        if counted_qty is not None:
            try:
                item.counted_quantity = max(0, int(counted_qty))
                item.notes = notes
                item.save()
            except (ValueError, TypeError):
                pass

    return render(request, 'inventory/partials/stocktake_item_row.html', {'item': item})


@login_required
def stocktake_complete(request, pk):
    stocktake = get_object_or_404(Stocktake, pk=pk, tenant=request.user.tenant)
    if stocktake.status != 'DRAFT':
        return HttpResponseForbidden("Inwentaryzacja została już przetworzona.")

    if request.method == "POST":
        with transaction.atomic():
            for item in stocktake.items.select_related('batch', 'product'):
                diff = item.difference
                if diff != 0:
                    if item.batch:
                        old_stock = item.batch.current_stock or 0
                        new_stock = item.counted_quantity
                        item.batch.current_stock = new_stock
                        item.batch.save()

                        ActivityLog.objects.create(
                            tenant=request.user.tenant,
                            user=request.user,
                            product=item.product,
                            product_batch=item.batch,
                            action='STOCKTAKE_ADJUSTMENT',
                            description=f"Korekta inwentaryzacyjna ({stocktake.title}): {old_stock} -> {new_stock} (Różnica: {diff:+d})",
                            old_value=str(old_stock),
                            new_value=str(new_stock)
                        )
                    else:
                        # Produkt bez partii - tworzymy nową partię w magazynie inwentaryzacji
                        loc = stocktake.location or Location.get_default_location(request.user.tenant)
                        new_batch = ProductBatch.objects.create(
                            tenant=request.user.tenant,
                            product=item.product,
                            location=loc,
                            current_stock=item.counted_quantity,
                            net_price=Decimal('0.00'),
                            gross_price=Decimal('0.00')
                        )
                        item.batch = new_batch
                        item.save()

                        ActivityLog.objects.create(
                            tenant=request.user.tenant,
                            user=request.user,
                            product=item.product,
                            product_batch=new_batch,
                            action='STOCKTAKE_ADJUSTMENT',
                            description=f"Utworzono partię z inwentaryzacji ({stocktake.title}): stan {item.counted_quantity}",
                            old_value='0',
                            new_value=str(item.counted_quantity)
                        )

            stocktake.status = 'COMPLETED'
            stocktake.completed_at = timezone.now()
            stocktake.save()

        return redirect('stocktake_detail', pk=stocktake.pk)

    return render(request, 'inventory/partials/confirm_stocktake_complete.html', {'stocktake': stocktake})


@login_required
def stocktake_cancel(request, pk):
    stocktake = get_object_or_404(Stocktake, pk=pk, tenant=request.user.tenant)
    if stocktake.status != 'DRAFT':
        return HttpResponseForbidden("Nie można anulować zatwierdzonej inwentaryzacji.")

    if request.method == "POST":
        stocktake.status = 'CANCELLED'
        stocktake.save()
        return redirect('stocktake_detail', pk=stocktake.pk)

    return render(request, 'inventory/partials/confirm_stocktake_cancel.html', {'stocktake': stocktake})
