from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from .models import Supplier
from .forms import SupplierForm
from inventory.models import Product

@login_required
def supplier_list(request):
    suppliers = Supplier.objects.all().order_by('name')
    if request.headers.get('HX-Request'):
        return render(request, 'suppliers/partials/supplier_table.html', {'suppliers': suppliers})
    return render(request, 'suppliers/supplier_list.html', {'suppliers': suppliers})


@login_required
def supplier_create(request):
    if request.method == "POST":
        form = SupplierForm(request.POST)
        if form.is_valid():
            form.save() # To wywoła naszą nową metodę save z formularza
            return HttpResponse("", headers={'HX-Trigger': 'suppliersChanged'})
    else:
        form = SupplierForm()
    return render(request, 'suppliers/partials/supplier_form.html', {'form': form})

@login_required
def supplier_edit(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
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
    supplier = get_object_or_404(Supplier, pk=pk)
    if request.method == "POST":
        supplier.delete()
        return HttpResponse("", headers={'HX-Trigger': 'suppliersChanged'})
    return render(request, 'suppliers/partials/confirm_delete_supplier.html', {'supplier': supplier})


@login_required
def supplier_preview(request, pk):
    # Używamy zdefiniowanego przez Ciebie related_name='products'
    supplier = get_object_or_404(Supplier.objects.prefetch_related('products'), pk=pk)
    return render(request, 'suppliers/partials/supplier_detail.html', {'supplier': supplier})


@login_required
def supplier_edit_products(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)

    if request.method == "POST":
        product_ids = request.POST.getlist('products')
        # set() przyjmuje listę ID i aktualizuje relację Many-to-Many
        supplier.products.set(Product.objects.filter(id__in=product_ids))

        # Odświeżamy obiekt z nowymi produktami do podglądu
        return render(request, 'suppliers/partials/supplier_detail.html', {'supplier': supplier})

    all_products = Product.objects.all().order_by('name')
    # Pobieramy ID produktów aktualnie przypisanych do tego dostawcy
    current_product_ids = supplier.products.values_list('id', flat=True)

    return render(request, 'suppliers/partials/supplier_products_form.html', {
        'supplier': supplier,
        'all_products': all_products,
        'current_product_ids': current_product_ids
    })