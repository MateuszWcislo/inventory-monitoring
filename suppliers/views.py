from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from .models import Supplier
from .forms import SupplierForm
from inventory.models import Product

@login_required
def supplier_list(request):
    suppliers = Supplier.objects.filter(tenant=request.user.tenant).order_by('name')
    if request.headers.get('HX-Request'):
        return render(request, 'suppliers/partials/supplier_table.html', {'suppliers': suppliers})
    return render(request, 'suppliers/supplier_list.html', {'suppliers': suppliers})


@login_required
def supplier_create(request):
    if request.method == "POST":
        form = SupplierForm(request.POST)
        if form.is_valid():
            # 1. Tworzymy obiekt dostawcy, ale nie zapisujemy jeszcze w bazie
            supplier = form.save(commit=False)
            supplier.tenant = request.user.tenant
            # 2. Teraz zapisujemy dostawcę, żeby dostał ID
            supplier.save()

            # 3. RĘCZNE zapisanie produktów (relacja M2M od strony Product)
            # Pobieramy ID produktów z wysłanego formularza
            product_ids = request.POST.getlist('products')
            if product_ids:
                # Filtrujemy produkty po tenancie (bezpieczeństwo!)
                products = Product.objects.filter(id__in=product_ids, tenant=request.user.tenant)
                # Używamy related_name 'products' z modelu Product
                supplier.products.set(products)

            return HttpResponse("", headers={'HX-Trigger': 'suppliersChanged'})
    else:
        form = SupplierForm()
    return render(request, 'suppliers/partials/supplier_form.html', {'form': form})

@login_required
def supplier_edit(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk, tenant=request.user.tenant)
    if request.method == "POST":
        form = SupplierForm(request.POST, instance=supplier)
        if form.is_valid():
            form.save()
            return HttpResponse("", headers={'HX-Trigger': 'suppliersChanged'})
    else:
        form = SupplierForm(instance=supplier)
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
    # Używamy zdefiniowanego przez Ciebie related_name='products'
    supplier = get_object_or_404(Supplier.objects.prefetch_related('products'), pk=pk, tenant=request.user.tenant)
    return render(request, 'suppliers/partials/supplier_detail.html', {'supplier': supplier})


@login_required
def supplier_edit_products(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk, tenant=request.user.tenant)

    if request.method == "POST":
        product_ids = request.POST.getlist('products')
        # Filtrujemy produkty po TENANCIE, żeby nie przypisać cudzych towarów
        valid_products = Product.objects.filter(id__in=product_ids, tenant=request.user.tenant)
        supplier.products.set(valid_products)
        return render(request, 'suppliers/partials/supplier_detail.html', {'supplier': supplier})

    # Tutaj też MUSI być filtracja
    all_products = Product.objects.filter(tenant=request.user.tenant).order_by('name')
    current_product_ids = supplier.products.values_list('id', flat=True)

    return render(request, 'suppliers/partials/supplier_products_form.html', {
        'supplier': supplier,
        'all_products': all_products,
        'current_product_ids': current_product_ids
    })