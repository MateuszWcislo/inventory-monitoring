from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from .models import Service
from .forms import ServiceForm
from django.views.decorators.http import require_POST


@login_required
def service_list(request):
    search_query = request.GET.get('search', '')
    sort_by = request.GET.get('sort', 'name')

    services = Service.objects.filter(tenant=request.user.tenant)

    if search_query:
        services = services.filter(name__icontains=search_query)

    services = services.order_by(sort_by)

    context = {
        'services': services,
        'search_query': search_query,
        'current_sort': sort_by
    }

    if request.headers.get('HX-Request'):
        return render(request, 'services/partials/service_table.html', context)
    return render(request, 'services/service_list.html', context)


@login_required
def service_create(request):
    if request.method == "POST":
        form = ServiceForm(request.POST)
        if form.is_valid():
            service = form.save(commit=False)
            service.tenant = request.user.tenant
            service.save()
            return HttpResponse("", headers={'HX-Trigger': 'servicesChanged'})
    else:
        form = ServiceForm()
    return render(request, 'services/partials/service_form.html', {'form': form, 'title': 'Dodaj usługę'})


@login_required
def service_edit(request, pk):
    service = get_object_or_404(Service, pk=pk, tenant=request.user.tenant)
    if request.method == "POST":
        form = ServiceForm(request.POST, instance=service)
        if form.is_valid():
            form.save()
            return HttpResponse("", headers={'HX-Trigger': 'servicesChanged'})
    else:
        form = ServiceForm(instance=service)
    return render(request, 'services/partials/service_form.html',
                  {'form': form, 'title': 'Edytuj usługę', 'service': service})


@login_required
@require_POST
def service_delete(request, pk):
    service = get_object_or_404(Service, pk=pk, tenant=request.user.tenant)
    service.delete()
    return HttpResponse("", headers={'HX-Trigger': 'servicesChanged'})