from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.db import transaction
from .models import Supplier
from .forms import SupplierForm
from inventory.models import Product
import json

@login_required
def supplier_list(request):
    suppliers = Supplier.objects.filter(tenant=request.user.tenant).order_by('name')
    if request.headers.get('HX-Request'):
        return render(request, 'suppliers/partials/supplier_table.html', {'suppliers': suppliers})
    return render(request, 'suppliers/supplier_list.html', {'suppliers': suppliers})


@login_required
def supplier_create(request):
    if request.method == "POST":
        form = SupplierForm(request.POST, user=request.user)
        if form.is_valid():
            with transaction.atomic():
                supplier = form.save(commit=False)
                supplier.tenant = request.user.tenant
                supplier.save()

                # Zapisujemy produkty wybrane w formularzu
                assigned_products = form.cleaned_data.get('products_selection')
                # supplier.products to manager relacji wstecznej
                supplier.products.set(assigned_products)

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
                supplier = form.save()
                # Ręcznie pobieramy dane z naszego pola 'products_selection'
                new_products = form.cleaned_data['products_selection']
                # Wykorzystujemy menedżera relacji wstecznej 'products'
                supplier.products.set(new_products)

            return HttpResponse("", headers={'HX-Trigger': 'suppliersChanged'})
    else:
        form = SupplierForm(instance=supplier, user=request.user)
    return render(request, 'suppliers/partials/supplier_form.html', {'form': form, 'supplier': supplier})

@login_required
def supplier_delete(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk, tenant=request.user.tenant)
    if request.method == "POST":
        supplier.delete()
        return HttpResponse("", headers={'HX-Trigger': 'suppliersChanged'})
    return render(request, 'suppliers/partials/confirm_delete_supplier.html', {'supplier': supplier})

@login_required
def supplier_preview(request, pk):
    # Prefetch_related('products') zapewnia, że produkty wyświetlą się w detalu
    supplier = get_object_or_404(
        Supplier.objects.prefetch_related('products'),
        pk=pk,
        tenant=request.user.tenant
    )
    return render(request, 'suppliers/partials/supplier_detail.html', {'supplier': supplier})

@login_required
def supplier_edit_products(request, pk):
    """Szybka edycja produktów przypisanych do dostawcy"""
    supplier = get_object_or_404(Supplier, pk=pk, tenant=request.user.tenant)

    if request.method == "POST":
        product_ids = request.POST.getlist('products')
        # Filtrujemy ID po tenancie, by nikt nie "wstrzyknął" cudzego produktu
        valid_products = Product.objects.filter(id__in=product_ids, tenant=request.user.tenant)
        supplier.products.set(valid_products)

        response = render(request, 'suppliers/partials/supplier_detail.html', {'supplier': supplier})
        response['HX-Trigger'] = 'suppliersChanged'
        return response

    all_products = Product.objects.filter(tenant=request.user.tenant).order_by('name')
    current_product_ids = supplier.products.values_list('id', flat=True)

    return render(request, 'suppliers/partials/supplier_products_form.html', {
        'supplier': supplier,
        'all_products': all_products,
        'current_product_ids': current_product_ids
    })