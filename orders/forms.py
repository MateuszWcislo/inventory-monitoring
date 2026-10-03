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
        error_messages = {
            'product': {
                'invalid_choice': 'Wybierz poprawny produkt.',
                'required': 'To pole jest wymagane.',
            },
            'supplier': {
                'invalid_choice': 'Wybrany dostawca jest nieprawidłowy lub nie przypisany do produktu.',
                'required': 'To pole jest wymagane.',
            },
            'quantity': {
                'required': 'Podaj ilość.',
                'min_value': 'Ilość musi być większa od zera.',
            },
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # 1. Atrybuty HTMX dla Produktu
        self.fields['product'].widget = forms.Select(attrs={
            'class': 'form-select',
            'id': 'id_product',
            'hx-get': reverse('get_filtered_suppliers'),
            'hx-target': '#id_supplier',
            'hx-trigger': 'change',
            'onchange': 'if(typeof updateVatRate === "function") { updateVatRate(); }'
        })

        # 2. Stylizacja pola Dostawcy
        self.fields['supplier'].widget.attrs.update({'class': 'form-select', 'id': 'id_supplier'})

        # 3. Rozróżnienie nowego rekordu od istniejącego (z uwzględnieniem UUIDField)
        is_persisted = bool(self.instance.pk and not self.instance._state.adding)
        is_product_removed = is_persisted and not self.instance.product

        for name, field in self.fields.items():
            if name not in ['product', 'supplier', 'order_type', 'status']:
                field.widget.attrs.update({'class': 'form-control'})

            # Jeśli produkt został usunięty w istniejącym zamówieniu, blokujemy edycję pól
            if is_product_removed and name != 'status':
                field.disabled = True
                if name == 'product':
                    field.help_text = f"Oryginalny produkt: {self.instance.product_name_snapshot} (USUNIĘTY)"

        # 4. Querysety i dane dla Tenanta
        if self.user:
            tenant = self.user.tenant

            tenant_products = Product.objects.filter(tenant=tenant)
            self.fields['product'].queryset = tenant_products

            if is_persisted and self.instance.product:
                # Zamówienie istniejące: pokazujemy powiązanych dostawców
                self.fields['supplier'].queryset = Supplier.objects.filter(
                    tenant=tenant,
                    product_mappings__product=self.instance.product
                ).distinct()
            elif is_product_removed:
                self.fields['supplier'].queryset = Supplier.objects.none()
            else:
                # Nowe zamówienie lub POST:
                # Jeśli to POST, musimy zezwolić na wszystkich dostawców tenanta,
                # aby walidacja przepuściła wartość wybraną dynamicznie przez HTMX.
                # Właściwa walidacja powiązania produktu z dostawcą dzieje się w clean().
                if args or kwargs.get('data'):
                    self.fields['supplier'].queryset = Supplier.objects.filter(tenant=tenant)
                else:
                    self.fields['supplier'].queryset = Supplier.objects.none()

            self.product_vats = {str(p.id): float(p.vat_rate) for p in tenant_products}
            import json
            self.product_vats_json = json.dumps(self.product_vats)
        else:
            self.product_vats = {}
            self.product_vats_json = "{}"

        if not is_persisted:
            self.fields['order_type'].initial = 'MANUAL'

    def clean(self):
        cleaned_data = super().clean()
        is_persisted = bool(self.instance.pk and not self.instance._state.adding)
        order_type = cleaned_data.get('order_type') or 'MANUAL'
        product = cleaned_data.get('product')
        supplier = cleaned_data.get('supplier')
        tenant = self.user.tenant if self.user else None

        # 1. Blokada edycji osieroconego zamówienia
        if is_persisted and not self.instance.product:
            new_status = cleaned_data.get('status')
            if new_status != 'CANCELLED':
                self.add_error('status', 'Dla zamówień bez powiązanego produktu jedyną opcją jest anulowanie.')
            return cleaned_data

        # 2. Bezpieczeństwo Tenantów: produkt
        if product and tenant and product.tenant != tenant:
            raise forms.ValidationError("Nieprawidłowy produkt.")

        # 3. Walidacja powiązania dostawcy
        if product and supplier:
            if tenant and supplier.tenant != tenant:
                self.add_error('supplier', 'Nieprawidłowy dostawca (inny tenant).')

            is_valid = product.supplier_mappings.filter(supplier=supplier).exists()
            if not is_valid:
                self.add_error('supplier', 'Ten dostawca nie jest przypisany do wybranego produktu.')

        # 4. Automatyczne podpowiadanie cen dla AUTO (nowe)
        if order_type == 'AUTO' and product and not is_persisted and tenant:
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

        # 5. Walidacja ceny dla zamówień ręcznych
        if order_type == 'MANUAL':
            if not cleaned_data.get('net_price') and not cleaned_data.get('gross_price'):
                if not is_persisted or self.instance.product:
                    self.add_error('net_price', 'Dla zamówienia ręcznego podaj cenę.')

        return cleaned_data
