from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse
from .forms import TenantUserCreateForm, TenantUserUpdateForm
from .models import User

# Funkcja sprawdzająca czy user jest adminem swojego tenanta
def is_admin(user):
    return user.is_authenticated and (user.role == 'ADMIN' or user.is_superuser)


@login_required
@user_passes_test(is_admin)
def user_create(request):
    if request.method == "POST":
        form = TenantUserCreateForm(request.POST)
        if form.is_valid():
            new_user = form.save(commit=False)
            # KLUCZ: Automatyczne przypisanie tenanta od zalogowanego Admina
            new_user.tenant = request.user.tenant
            new_user.save()
            return redirect('user_list')  # Zakładamy, że zrobimy listę
    else:
        form = TenantUserCreateForm()

    return render(request, 'users/user_form.html', {'form': form})

@login_required
@user_passes_test(is_admin)
def user_list(request):
    # Filtrujemy użytkowników: tylko ci z tego samego tenanta
    users = User.objects.filter(tenant=request.user.tenant).exclude(id=request.user.id).order_by('-is_active','last_name')
    return render(request, 'users/user_list.html', {'users': users})


# Edycja użytkownika
@login_required
@user_passes_test(is_admin)
def user_edit(request, pk):
    user_to_edit = get_object_or_404(User, id=pk, tenant=request.user.tenant)

    if request.method == "POST":
        form = TenantUserUpdateForm(request.POST, instance=user_to_edit)
        if form.is_valid():
            form.save()
            # Pusta odpowiedź (204 No Content) z triggerem dla HTMX
            response = HttpResponse(status=204)
            response['HX-Trigger'] = 'usersChanged'
            return response
    else:
        form = TenantUserUpdateForm(instance=user_to_edit)

    return render(request, 'users/user_edit_form.html', {'form': form, 'user_to_edit': user_to_edit})