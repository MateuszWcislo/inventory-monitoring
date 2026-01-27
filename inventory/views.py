from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.core.paginator import Paginator
from django.db.models import Q, F

from .forms import ProductForm
from .models import Product, ActivityLog


@login_required
def product_list(request):
    # Pobieramy produkty i od razu dane domyślnego dostawcy (JOIN w SQL)
    products = Product.objects.all().select_related('default_supplier').order_by('name')

    # Jeśli to zapytanie HTMX (odświeżanie tabeli), zwróć TYLKO tabelę
    if request.headers.get('HX-Request'):
        return render(request, 'inventory/partials/product_table.html', {'products': products})

    # Jeśli to wejście bezpośrednie, zwróć całą stronę
    return render(request, 'inventory/product_list.html', {'products': products})


def home_redirect(request):
    if request.user.is_authenticated:
        return redirect('product_list')
    return redirect('login')


@login_required
def product_create(request):
    if request.method == "POST":
        form = ProductForm(request.POST)
        if form.is_valid():
            product = form.save()
            # Logowanie
            ActivityLog.objects.create(
                user=request.user,
                product_name=product.name,
                action_type='CREATE',
                description=f"Dodano produkt: {product.name}"
            )
            # Sygnał do zamknięcia modala i odświeżenia tabeli
            response = HttpResponse("")
            response['HX-Trigger'] = 'productChanged'
            return response
    else:
        form = ProductForm()

    return render(request, 'inventory/partials/product_form.html', {'form': form})

@login_required
def product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == "POST":
        old_stock = product.current_stock
        form = ProductForm(request.POST, instance=product)
        if form.is_valid():
            product = form.save()

            # Logowanie edycji
            desc = f"Edycja produktu: {product.name}."
            if old_stock != product.current_stock:
                desc += f" Zmiana stanu: {old_stock} -> {product.current_stock}."

            ActivityLog.objects.create(
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
    product = get_object_or_404(Product, pk=pk)
    if request.method == "POST":
        product_name = product.name
        product.delete()

        # Logowanie usunięcia
        ActivityLog.objects.create(
            user=request.user,
            product_name=product_name,
            action_type='DELETE',
            description=f"Usunięto produkt: {product_name}"
        )

        response = HttpResponse("")
        response['HX-Trigger'] = 'productChanged'
        return response

        # Upewnij się, że ten plik ISTNIEJE w folderze partials
    return render(request, 'inventory/partials/confirm_delete.html', {'product': product})


@login_required
def quick_update_stock(request, pk):
    product = get_object_or_404(Product, pk=pk)

    if request.method == "POST":
        # 1. Zapisujemy starą wartość ZANIM ją zmienimy
        old_stock = product.current_stock
        new_stock_raw = request.POST.get('new_stock')

        if new_stock_raw is not None:
            product.current_stock = int(new_stock_raw)
            product.save()

            # 2. Tworzymy log z poprawnymi danymi
            ActivityLog.objects.create(
                user=request.user,
                product_name=product.name,
                action_type='UPDATE',
                previous_stock=old_stock,
                current_stock=product.current_stock,
                description=f"Szybka aktualizacja stanu: {product.name}. Zmiana: {old_stock} -> {product.current_stock}."
            )

    # 3. Pobieramy listę z optymalizacją (select_related), żeby tabela nie muliła
    products = Product.objects.all().select_related('default_supplier').order_by('name')
    return render(request, 'inventory/partials/product_table.html', {'products': products})


@login_required
def activity_logs(request):
    logs_list = ActivityLog.objects.all().order_by('-timestamp')

    # Tworzymy paginator: 50 logów na stronę
    paginator = Paginator(logs_list, 50)

    # Pobieramy numer strony z adresu URL (np. ?page=2)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'inventory/activity_logs.html', {'page_obj': page_obj})