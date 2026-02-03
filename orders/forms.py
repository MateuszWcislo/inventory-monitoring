from django import forms
from django.forms import inlineformset_factory, BaseInlineFormSet
from .models import Order, OrderItem
from inventory.models import Product



class OrderForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ['supplier', 'status']
        widgets = {
            'supplier': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Sprawdzamy czy to NOWE zamówienie
        is_new = not self.instance or self.instance._state.adding

        if is_new:
            if 'status' in self.fields:
                # Opcja rygorystyczna: usuwamy pole z formularza
                del self.fields['status']
        else:
            # Przy edycji: status zostaje, ale blokujemy dostawcę
            if 'supplier' in self.fields:
                self.fields['supplier'].disabled = True


# Klasa pomocnicza do ładnego wyświetlania produktu w select
class ProductChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        # Tutaj definiujesz co widzi użytkownik: Nazwa (Stan: X)
        return f"{obj.name} (Stan: {obj.current_stock})"


class OrderItemForm(forms.ModelForm):
    # Nadpisujemy pole product, używając naszej nowej klasy
    product = ProductChoiceField(
        queryset=Product.objects.none(),  # Zostanie uzupełnione w __init__
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = OrderItem
        fields = ['product', 'quantity']

        error_messages = {
            'quantity': {
                'required': 'Podaj liczbę sztuk.',
                'invalid': 'Wprowadź poprawną liczbę.',
            }
        }

    def __init__(self, *args, **kwargs):
        supplier = kwargs.pop('supplier', None)
        tenant = kwargs.pop('tenant', None)
        super().__init__(*args, **kwargs)

        if tenant:
            qs = Product.objects.filter(tenant=tenant)
            if supplier:
                qs = qs.filter(suppliers=supplier)

            # Przypisujemy przefiltrowany queryset do naszego pola
            self.fields['product'].queryset = qs.order_by('name')

        self.fields['quantity'].widget.attrs.update({
            'class': 'form-control',
            'min': 1,
            'oninvalid': "this.setCustomValidity('Wprowadź liczbę większą od zera')",
            'oninput': "this.setCustomValidity('')"
        })

    def clean_quantity(self):
        quantity = self.cleaned_data.get('quantity')
        if quantity is None or quantity <= 0:
            raise forms.ValidationError("Ilość musi być większa od 0.")
        return quantity


class BaseOrderItemFormSet(BaseInlineFormSet):
    def clean(self):
        """Sprawdza, czy dodano przynajmniej jeden produkt i czy nie jest zaznaczony do usunięcia."""
        super().clean()

        # Jeśli pojawiły się już błędy w poszczególnych formularzach, nie idziemy dalej
        if any(self.errors):
            return

        completed_forms = 0
        for form in self.forms:
            # Sprawdzamy, czy formularz ma dane i czy nie jest zaznaczony do usunięcia
            if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
                completed_forms += 1

        if completed_forms < 1:
            raise forms.ValidationError("Zamówienie musi zawierać co najmniej jeden produkt.")


# --- AKTUALIZACJA FABRYKI FORMSETU ---
OrderItemFormSet = inlineformset_factory(
    Order,
    OrderItem,
    form=OrderItemForm,
    formset=BaseOrderItemFormSet,  # <--- Dodajemy naszą nową klasę bazową
    extra=0,
    can_delete=True
)