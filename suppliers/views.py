from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from .models import Supplier
from .forms import SupplierForm

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
            form.save()
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