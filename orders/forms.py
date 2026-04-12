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
        self.fields['product'].widget = forms.Select(attrs={
            'class': 'form-select',
            'hx-get': reverse('get_filtered_suppliers'),
            'hx-target': '#id_supplier',
            'hx-trigger': 'change',
            'onchange': 'updateVatRate(this)'
        })

        # 2. Stylizacja pola Dostawcy
        self.fields['supplier'].widget.attrs.update({'class': 'form-select'})

        # 3. Stylizacja pozostałych pól i obsługa stanu "Produkt usunięty"
        is_product_removed = self.instance.pk and not self.instance.product

        for name, field in self.fields.items():
            if name not in ['product', 'supplier', 'order_type', 'status']:
                field.widget.attrs.update({'class': 'form-control'})

            # Jeśli produkt został usunięty, blokujemy większość pól (zostawiamy status)
            if is_product_removed and name != 'status':
                field.disabled = True
                if name == 'product':
                    field.help_text = f"Oryginalny produkt: {self.instance.product_name_snapshot} (USUNIĘTY)"

        # 4. Querysety i dane dla Tenanta
        if self.user:
            tenant = self.user.tenant

            # Produkty tylko aktywne dla tego tenanta
            tenant_products = Product.objects.filter(tenant=tenant)
            self.fields['product'].queryset = tenant_products

            # Logika filtrowania dostawców
            if self.instance and self.instance.product:
                # Jeśli produkt istnieje, pokazujemy tylko powiązanych dostawców
                self.fields['supplier'].queryset = Supplier.objects.filter(
                    tenant=tenant,
                    product_mappings__product=self.instance.product
                ).distinct()
            elif is_product_removed:
                # Jeśli produkt usunięty, lista dostawców jest pusta (nie ma z czym wiązać)
                self.fields['supplier'].queryset = Supplier.objects.none()
            else:
                # Nowe zamówienie - czekamy na wybór produktu przez HTMX
                self.fields['supplier'].queryset = Supplier.objects.none()

            # Słownik VAT dla JS (tylko jeśli produkt istnieje)
            self.product_vats = {str(p.id): float(p.vat_rate) for p in tenant_products}

        if not self.instance.pk:
            self.fields['order_type'].initial = 'MANUAL'


    def clean(self):
        cleaned_data = super().clean()
        order_type = cleaned_data.get('order_type')
        product = cleaned_data.get('product')
        supplier = cleaned_data.get('supplier')
        tenant = self.user.tenant

        # 1. Blokada edycji osieroconego zamówienia (Twoja logika - zostaje)
        if self.instance.pk and not self.instance.product:
            new_status = cleaned_data.get('status')
            if new_status != 'CANCELLED':
                self.add_error('status', 'Dla zamówień bez powiązanego produktu jedyną opcją jest anulowanie.')
            return cleaned_data

        # 2. BEZPIECZEŃSTWO: Sprawdź czy produkt należy do Tenanta (Cross-tenant prevention)
        if product and product.tenant != tenant:
            raise forms.ValidationError("Nieprawidłowy produkt.")

        # 3. Walidacja powiązania dostawcy
        if product and supplier:
            # Upewnij się, że dostawca też należy do tego samego Tenanta
            if supplier.tenant != tenant:
                self.add_error('supplier', 'Nieprawidłowy dostawca.')

            is_valid = product.supplier_mappings.filter(supplier=supplier).exists()
            if not is_valid:
                self.add_error('supplier', 'Ten dostawca nie jest przypisany do wybranego produktu.')

        # 4. Automatyczne podpowiadanie cen (Twoja logika - zostaje)
        if order_type == 'AUTO' and product and not self.instance.pk:
            last_order = Order.objects.filter(
                product=product,
                tenant=tenant,
                status='COMPLETED'
            ).order_by('-created_at').first()

            if last_order:
                if not cleaned_data.get('net_price'):
                    cleaned_data['net_price'] = last_order.net_price
                    cleaned_data['gross_price'] = last_order.gross_price
                if not cleaned_data.get('supplier'):
                    if product.supplier_mappings.filter(supplier=last_order.supplier).exists():
                        cleaned_data['supplier'] = last_order.supplier

        # 5. Walidacja ceny dla zamówień ręcznych (Twoja logika - zostaje)
        if order_type == 'MANUAL':
            if not cleaned_data.get('net_price') and not cleaned_data.get('gross_price'):
                if not self.instance.pk or self.instance.product:
                    self.add_error('net_price', 'Dla zamówienia ręcznego podaj cenę.')

        return cleaned_data