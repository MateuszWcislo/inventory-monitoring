from django import forms
from .models import Order
from django.urls import reverse
from inventory.models import Product
from suppliers.models import Supplier


class OrderForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ['product', 'supplier', 'quantity', 'net_price', 'gross_price', 'order_type', 'status']
        widgets = {
            'order_type': forms.HiddenInput(),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # 1. Atrybuty HTMX dla Produktu
        # Dodajemy 'hx-include': '#id_supplier', aby nie zgubić wybranego dostawcy
        self.fields['product'].widget = forms.Select(attrs={
            'class': 'form-select',
            'hx-get': reverse('get_filtered_options'),
            'hx-target': '#id_supplier',
            'hx-include': '#id_supplier',  # KLUCZOWE: dołącza wartość dostawcy do requesta
            'hx-trigger': 'change',
            'onchange': 'updateVatRate(this)'
        })

        # 2. Atrybuty HTMX dla Dostawcy
        # Dodajemy 'hx-include': '#id_product', aby nie zgubić wybranego produktu
        self.fields['supplier'].widget = forms.Select(attrs={
            'class': 'form-select',
            'hx-get': reverse('get_filtered_options'),
            'hx-target': '#id_product',
            'hx-include': '#id_product',  # KLUCZOWE: dołącza wartość produktu do requesta
            'hx-trigger': 'change'
        })

        # 3. Stylizacja pozostałych pól
        for name, field in self.fields.items():
            if name not in ['product', 'supplier', 'order_type', 'status']:
                field.widget.attrs.update({'class': 'form-control'})

        # 4. Querysety i dane dla Tenanta
        if self.user:
            tenant_products = Product.objects.filter(tenant=self.user.tenant)
            self.fields['product'].queryset = tenant_products
            self.fields['supplier'].queryset = Supplier.objects.filter(tenant=self.user.tenant)

            # Słownik VAT dla JS
            self.product_vats = {str(p.id): float(p.vat_rate) for p in tenant_products}

        # Domyślny typ dla nowych zamówień ręcznych
        if not self.instance.pk:
            self.fields['order_type'].initial = 'MANUAL'

    def clean(self):
        cleaned_data = super().clean()
        order_type = cleaned_data.get('order_type')
        product = cleaned_data.get('product')

        if order_type == 'AUTO' and product:
            last_order = Order.objects.filter(
                product=product,
                tenant=self.user.tenant
            ).order_by('-created_at').first()

            if last_order:
                if not cleaned_data.get('net_price'):
                    cleaned_data['net_price'] = last_order.net_price
                if not cleaned_data.get('gross_price'):
                    cleaned_data['gross_price'] = last_order.gross_price
                if not cleaned_data.get('supplier'):
                    cleaned_data['supplier'] = last_order.supplier

        if order_type == 'MANUAL':
            if not cleaned_data.get('net_price') and not cleaned_data.get('gross_price'):
                self.add_error('net_price', 'Dla zamówienia ręcznego podaj cenę.')

        return cleaned_data