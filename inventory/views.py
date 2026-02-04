from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden
from django.core.paginator import Paginator
from django.db.models import Q, F
from django.db import transaction

from orders.models import Order, OrderItem
from .forms import ProductForm
from .models import Product, ActivityLog
import json


# --- WIDOKI LISTY I STRONY GŁÓWNEJ ---

@login_required
def product_list(request):
    # Prefetch_related dla dostawców, aby uniknąć N+1
    products = Product.objects.filter(tenant=request.user.tenant).prefetch_related('suppliers').order_by('-is_favourite', 'name')

    if request.headers.get('HX-Request'):
        return render(request, 'inventory/partials/product_table.html', {'products': products})
    return render(request, 'inventory/product_list.html', {'products': products})


def home_redirect(request):
    if request.user.is_authenticated:
        return redirect('product_list')
    return redirect('login')


# --- CRUD PRODUKTU ---

@login_required
def product_create(request):
    if request.method == "POST":
        form = ProductForm(request.POST)
        if form.is_valid():
            product = form.save(commit=False)
            # Tutaj dzieje się magia Multi-tenancy:
            product.tenant = request.user.tenant
            product.save()

            # Zapisujemy też relacje Many-to-Many (np. dostawców)
            form.save_m2m()

            ActivityLog.objects.create(
                tenant=request.user.tenant,
                user=request.user,
                product_name=product.name,
                action_type='CREATE',
                description=f"Dodano produkt: {product.name}"
            )
            response = HttpResponse("")
            response['HX-Trigger'] = 'productChanged'
            return response
    else:
        form = ProductForm()
    return render(request, 'inventory/partials/product_form.html', {'form': form})


@login_required
def product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk, tenant=request.user.tenant)
    if request.method == "POST":
        old_stock = product.current_stock
        form = ProductForm(request.POST, instance=product)
        if form.is_valid():
            product = form.save()

            desc = f"Edycja produktu: {product.name}."
            if old_stock != product.current_stock:
                desc += f" Zmiana stanu: {old_stock} -> {product.current_stock}."

            ActivityLog.objects.create(
                tenant=request.user.tenant,
                user=request.user,
                product_name=product.name,
                action_type='UPDATE',
                previous_stock=old_stock,
                current_stock=product.current_stock,
                description=desc
            )
            response = HttpResponse("")
            response['HX-Trigger'] = 'productChanged'
            return response
    else:
        form = ProductForm(instance=product)
    return render(request, 'inventory/partials/product_form.html', {'form': form, 'product': product})


@login_required
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk, tenant=request.user.tenant)
    if request.method == "POST":
        product_name = product.name
        product.delete()
        ActivityLog.objects.create(
            tenant=request.user.tenant,
            user=request.user,
            product_name=product_name,
            action_type='DELETE',
            description=f"Usunięto produkt: {product_name}"
        )
        response = HttpResponse("")
        response['HX-Trigger'] = 'productChanged'
        return response
    return render(request, 'inventory/partials/confirm_delete.html', {'product': product})


# --- FUNKCJE POMOCNICZE TABELI ---

@login_required
def quick_update_stock(request, pk):
    product = get_object_or_404(Product, pk=pk, tenant=request.user.tenant)
    if request.method == "POST":
        old_stock = product.current_stock
        new_stock_raw = request.POST.get('new_stock')
        if new_stock_raw is not None:
            product.current_stock = int(new_stock_raw)
            product.save()
            ActivityLog.objects.create(
                tenant=request.user.tenant,
                user=request.user,
                product_name=product.name,
                action_type='UPDATE',
                previous_stock=old_stock,
                current_stock=product.current_stock,
                description=f"Szybka aktualizacja stanu: {product.name}. Zmiana: {old_stock} -> {product.current_stock}."
            )
    products = Product.objects.filter(tenant=request.user.tenant).prefetch_related('suppliers').order_by('-is_favourite', 'name')
    return render(request, 'inventory/partials/product_table.html', {'products': products})


@login_required
def toggle_favourite(request, pk):
    product = get_object_or_404(Product, pk=pk, tenant=request.user.tenant)
    product.is_favourite = not product.is_favourite
    product.save()
    products = Product.objects.filter(tenant=request.user.tenant).prefetch_related('suppliers').order_by('-is_favourite', 'name')
    return render(request, 'inventory/partials/product_table.html', {'products': products})


@login_required
def activity_logs(request):
    if not request.user.is_tenant_admin():
        return HttpResponseForbidden("Tylko administrator może przeglądać logi.")
    logs_list = ActivityLog.objects.filter(tenant=request.user.tenant).order_by('-timestamp')
    paginator = Paginator(logs_list, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'inventory/activity_logs.html', {'page_obj': page_obj})


# --- LOGIKA ZAMÓWIEŃ (POJEDYNCZE I MASOWE) ---

@login_required
def add_to_order_modal(request, pk):
    product = get_object_or_404(Product, pk=pk, tenant=request.user.tenant)
    product_suppliers = product.suppliers.filter(tenant=request.user.tenant)
    open_orders = Order.objects.filter(
        status='OPEN',
        supplier__in=product_suppliers
    ).select_related('supplier')

    return render(request, 'inventory/partials/add_to_order_form.html', {
        'product': product,
        'open_orders': open_orders,
        'product_suppliers': product_suppliers
    })


@login_required
def add_to_order_save(request, pk):
    if request.method == "POST":
        product = get_object_or_404(Product, pk=pk, tenant=request.user.tenant)
        order_id = request.POST.get('order_id')
        quantity = int(request.POST.get('quantity', 1))

        with transaction.atomic():
            if order_id.startswith("new_"):
                supplier_id = order_id.split("_")[1]
                order = Order.objects.create(supplier_id=supplier_id, status='OPEN', tenant=request.user.tenant)
            else:
                order = get_object_or_404(Order, id=order_id, tenant=request.user.tenant)

            # Sumowanie ilości jeśli produkt już jest w zamówieniu
            item, created = OrderItem.objects.get_or_create(
                order=order,
                product=product,
                defaults={'quantity': quantity}
            )
            if not created:
                item.quantity += quantity
                item.save()

        return HttpResponse(status=204, headers={'HX-Trigger': 'ordersChanged'})


@login_required
def bulk_add_to_order_modal(request):
    product_ids = request.POST.getlist('product_ids')
    if not product_ids:
        return HttpResponse("<div class='modal-body'>Nie wybrano żadnych produktów.</div>")

    products = Product.objects.filter(id__in=product_ids).prefetch_related('suppliers')

    common_suppliers = None
    for p in products:
        p_suppliers = set(p.suppliers.all())
        if common_suppliers is None:
            common_suppliers = p_suppliers
        else:
            common_suppliers &= p_suppliers

    if not common_suppliers:
        return render(request, 'inventory/partials/bulk_error.html', {
            'message': 'Wybrane produkty nie mają wspólnego dostawcy!'
        })

    open_orders = Order.objects.filter(status='OPEN', supplier__in=common_suppliers).select_related('supplier')

    return render(request, 'inventory/partials/bulk_add_form.html', {
        'products': products,
        'common_suppliers': common_suppliers,
        'open_orders': open_orders,
        'product_ids': ",".join(map(str, product_ids))
    })


@login_required
def bulk_add_to_order_save(request):
    if request.method == "POST":
        raw_ids = request.POST.get('product_ids', '')
        product_ids = [pid for pid in raw_ids.split(',') if pid]
        order_id = request.POST.get('order_id')

        with transaction.atomic():
            if order_id.startswith("new_"):
                supplier_id = order_id.split("_")[1]
                order = Order.objects.create(supplier_id=supplier_id, status='OPEN', tenant=request.user.tenant)
            else:
                order = get_object_or_404(Order, id=order_id, tenant=request.user.tenant)

            for p_id in product_ids:
                # Sumowanie dla każdego produktu z listy masowej
                item, created = OrderItem.objects.get_or_create(
                    order=order,
                    product_id=p_id,
                    defaults={'quantity': 1}
                )
                if not created:
                    item.quantity += 1
                    item.save()

        # Tworzymy słownik sygnałów dla HTMX
        trigger_data = {
            "ordersChanged": None,  # To zamknie modal (dzięki Twojemu JS w base.html)
            "clearProductChecks": None,  # To odznaczy checkboxy
            "showToast": f"Dodano {len(product_ids)} produktów do zamówienia."  # Treść dymka
        }

        return HttpResponse(
            status=204,
            headers={'HX-Trigger': json.dumps(trigger_data)}
        )