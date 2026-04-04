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
            'order_type': forms.HiddenInput(),  # Ukryte pole
            'product': forms.Select(attrs={'class': 'form-select', 'onchange': 'updateVatRate(this)'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'supplier': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # Atrybuty HTMX dla Produktu (aktualizuje Dostawcę)
        self.fields['product'].widget.attrs.update({
            'hx-get': reverse('get_filtered_options'),
            'hx-target': '#id_supplier',
            'hx-trigger': 'change',
            'onchange': 'updateVatRate(this)'  # Twoja funkcja od VAT
        })

        # Atrybuty HTMX dla Dostawcy (aktualizuje Produkt)
        self.fields['supplier'].widget.attrs.update({
            'hx-get': reverse('get_filtered_options'),
            'hx-target': '#id_product',
            'hx-trigger': 'change'
        })

        # Stylizacja i Querysety
        for name, field in self.fields.items():
            field.widget.attrs.update({'class': 'form-control' if name not in ['product', 'supplier', 'order_type',
                                                                               'status'] else 'form-select'})

        if self.user:
            self.fields['product'].queryset = Product.objects.filter(tenant=self.user.tenant)
            self.fields['supplier'].queryset = Supplier.objects.filter(tenant=self.user.tenant)
            # Słownik VAT dla JS
            self.product_vats = {str(p.id): float(p.vat_rate) for p in Product.objects.filter(tenant=self.user.tenant)}


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
                # Jeśli użytkownik zostawił puste, dociągamy z historii
                if not cleaned_data.get('net_price'):
                    cleaned_data['net_price'] = last_order.net_price
                if not cleaned_data.get('gross_price'):
                    cleaned_data['gross_price'] = last_order.gross_price
                if not cleaned_data.get('supplier'):
                    cleaned_data['supplier'] = last_order.supplier
            # Jeśli last_order nie istnieje, zostawiamy puste zgodnie z Twoją prośbą

        # Walidacja dla MANUAL - tutaj cena i ilość muszą być
        if order_type == 'MANUAL':
            if not cleaned_data.get('net_price') and not cleaned_data.get('gross_price'):
                self.add_error('net_price', 'Dla zamówienia ręcznego podaj cenę.')

        return cleaned_data