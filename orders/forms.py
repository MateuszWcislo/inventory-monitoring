from django import forms
from django.forms import inlineformset_factory, BaseInlineFormSet
from .models import Order, OrderItem
from inventory.models import Product
from suppliers.models import Supplier  # Pamiętaj o imporcie!


class OrderForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ['supplier', 'status']
        widgets = {
            'supplier': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        # Wyciągamy użytkownika, aby przefiltrować dostawców
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if user:
            # FILTR: Tylko dostawcy z tej samej firmy
            self.fields['supplier'].queryset = Supplier.objects.filter(tenant=user.tenant).order_by('name')

        is_new = not self.instance or self.instance._state.adding

        if is_new:
            if 'status' in self.fields:
                del self.fields['status']
        else:
            if 'supplier' in self.fields:
                self.fields['supplier'].disabled = True


class ProductChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.name} (Stan: {obj.current_stock})"


class OrderItemForm(forms.ModelForm):
    product = ProductChoiceField(
        queryset=Product.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = OrderItem
        fields = ['product', 'quantity']

    def __init__(self, *args, **kwargs):
        # Formsety przekazują dodatkowe dane przez form_kwargs
        supplier = kwargs.pop('supplier', None)
        tenant = kwargs.pop('tenant', None)
        super().__init__(*args, **kwargs)

        # Pobieramy queryset produktów
        qs = Product.objects.none()
        if tenant:
            qs = Product.objects.filter(tenant=tenant)
            if supplier:
                # FILTR: Tylko produkty przypisane do wybranego dostawcy
                qs = qs.filter(suppliers=supplier)

        self.fields['product'].queryset = qs.order_by('name')

        self.fields['quantity'].widget.attrs.update({
            'class': 'form-control',
            'min': 1,
        })

    def clean_quantity(self):
        quantity = self.cleaned_data.get('quantity')
        if quantity is None or quantity <= 0:
            raise forms.ValidationError("Ilość musi być większa od 0.")
        return quantity


class BaseOrderItemFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return

        completed_forms = 0
        for form in self.forms:
            if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
                completed_forms += 1

        if completed_forms < 1:
            raise forms.ValidationError("Zamówienie musi zawierać co najmniej jeden produkt.")


# Fabryka formsetu
OrderItemFormSet = inlineformset_factory(
    Order,
    OrderItem,
    form=OrderItemForm,
    formset=BaseOrderItemFormSet,
    extra=1,  # Zmienione na 1, aby przy nowym zamówieniu był od razu jeden pusty wiersz
    can_delete=True
)