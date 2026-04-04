from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.db import transaction
from .models import Supplier
from .forms import SupplierForm
from inventory.models import Product, ProductSupplier


@login_required
def supplier_list(request):
    search_query = request.GET.get('q', '')
    sort_by = request.GET.get('sort', 'name')  # Domyślnie sortujemy po nazwie

    # Podstawowy QuerySet dla Tenanta
    suppliers = Supplier.objects.filter(tenant=request.user.tenant)

    # Wyszukiwanie po nazwie
    if search_query:
        suppliers = suppliers.filter(name__icontains=search_query)

    # Sortowanie
    # Zabezpieczamy przed nieprawidłowymi polami, sprawdzając czy pole istnieje w modelu
    allowed_sort_fields = ['name', '-name', 'nip', '-nip', 'representative', '-representative', 'created', '-created']
    if sort_by not in allowed_sort_fields:
        sort_by = 'name'

    suppliers = suppliers.order_by(sort_by)

    context = {
        'suppliers': suppliers,
        'q': search_query,
        'sort': sort_by
    }

    if request.headers.get('HX-Request'):
        return render(request, 'suppliers/partials/supplier_table.html', context)
    return render(request, 'suppliers/supplier_list.html', context)


@login_required
def supplier_create(request):
    if request.method == "POST":
        form = SupplierForm(request.POST, user=request.user)
        if form.is_valid():
            with transaction.atomic():
                # 1. Zapisujemy podstawowe dane dostawcy
                supplier = form.save(commit=False)
                supplier.tenant = request.user.tenant
                supplier.save()

                # 2. Pobieramy ID zaznaczonych produktów z checkboxów
                selected_product_ids = request.POST.getlist('products_selection')

                # 3. Tworzymy powiązania i wyciągamy SKU dla każdego zaznaczonego produktu
                for p_id in selected_product_ids:
                    # Szukamy w POST pola o nazwie sku_ID-PRODUKTU
                    sku_value = request.POST.get(f'sku_{p_id}', '').strip()

                    ProductSupplier.objects.create(
                        tenant=request.user.tenant,
                        supplier=supplier,
                        product_id=p_id,
                        supplier_sku=sku_value if sku_value else None
                    )

            return HttpResponse("", headers={'HX-Trigger': 'suppliersChanged'})
    else:
        form = SupplierForm(user=request.user)

    return render(request, 'suppliers/partials/supplier_form.html', {'form': form})


@login_required
def supplier_edit(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk, tenant=request.user.tenant)

    if request.method == "POST":
        form = SupplierForm(request.POST, instance=supplier, user=request.user)
        if form.is_valid():
            with transaction.atomic():
                # 1. Aktualizujemy dane dostawcy
                supplier = form.save()

                # 2. Pobieramy nowe zaznaczenie produktów
                selected_product_ids = request.POST.getlist('products_selection')

                # 3. Usuwamy stare powiązania, aby zapisać nowe (najbezpieczniejsza metoda "sync")
                ProductSupplier.objects.filter(supplier=supplier).delete()

                # 4. Tworzymy nowe powiązania z aktualnymi SKU
                for p_id in selected_product_ids:
                    sku_value = request.POST.get(f'sku_{p_id}', '').strip()

                    ProductSupplier.objects.create(
                        tenant=request.user.tenant,
                        supplier=supplier,
                        product_id=p_id,
                        supplier_sku=sku_value if sku_value else None
                    )

            return HttpResponse("", headers={'HX-Trigger': 'suppliersChanged'})
    else:
        # Prefetchujemy mapowania, aby formularz w HTML mógł łatwo wyciągnąć istniejące SKU
        supplier = Supplier.objects.prefetch_related('product_mappings').get(pk=pk)
        form = SupplierForm(instance=supplier, user=request.user)

    return render(request, 'suppliers/partials/supplier_form.html', {
        'form': form,
        'supplier': supplier
    })

@login_required
def supplier_delete(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk, tenant=request.user.tenant)
    if request.method == "POST":
        supplier.delete()
        return HttpResponse("", headers={'HX-Trigger': 'suppliersChanged'})
    return render(request, 'suppliers/partials/confirm_delete_supplier.html', {'supplier': supplier})


@login_required
def supplier_preview(request, pk):
    # Korzystamy z product_mappings (zdefiniowanego w inventory/models.py)
    supplier = get_object_or_404(
        Supplier.objects.prefetch_related('product_mappings__product'),
        pk=pk,
        tenant=request.user.tenant
    )
    return render(request, 'suppliers/partials/supplier_detail.html', {'supplier': supplier})


@login_required
def supplier_edit_products(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk, tenant=request.user.tenant)

    if request.method == "POST":
        product_ids = request.POST.getlist('products')
        with transaction.atomic():
            # Usuwamy stare
            ProductSupplier.objects.filter(supplier=supplier).delete()
            # Dodajemy nowe
            valid_products = Product.objects.filter(id__in=product_ids, tenant=request.user.tenant)
            for prod in valid_products:
                ProductSupplier.objects.create(
                    tenant=request.user.tenant,
                    product=prod,
                    supplier=supplier
                )

        response = render(request, 'suppliers/partials/supplier_detail.html', {'supplier': supplier})
        response['HX-Trigger'] = 'suppliersChanged'
        return response

    all_products = Product.objects.filter(tenant=request.user.tenant).order_by('name')
    # Ważne: pobieramy ID produktów, które już są przypisane
    current_product_ids = ProductSupplier.objects.filter(
        supplier=supplier
    ).values_list('product_id', flat=True)

    return render(request, 'suppliers/partials/supplier_products_form.html', {
        'supplier': supplier,
        'all_products': all_products,
        'current_product_ids': list(current_product_ids)
    })
