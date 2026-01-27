from django import forms
from django.forms import inlineformset_factory
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
        # Jeśli zamówienie jest NOWE (nie ma jeszcze id), usuwamy pole statusu
        if not self.instance or not self.instance.pk:
            if 'status' in self.fields:
                del self.fields['status']
        else:
            # Przy edycji: blokujemy zmianę dostawcy, żeby nie zepsuć listy produktów
            self.fields['supplier'].disabled = True


# --- NOWA KLASA FORMULARZA POZYCJI ---
class OrderItemForm(forms.ModelForm):
    class Meta:
        model = OrderItem
        fields = ['product', 'quantity']

    def __init__(self, *args, **kwargs):
        # Wyciągamy dostawcę przekazanego z widoku
        supplier = kwargs.pop('supplier', None)
        super().__init__(*args, **kwargs)

        # Filtrowanie produktów tylko od wybranego dostawcy
        if supplier:
            self.fields['product'].queryset = Product.objects.filter(suppliers=supplier)
            self.fields['product'].widget.attrs.update({'class': 'form-select'})

        self.fields['quantity'].widget.attrs.update({'class': 'form-control', 'min': 1})


# --- AKTUALIZACJA FORMSETU ---
OrderItemFormSet = inlineformset_factory(
    Order,
    OrderItem,
    form=OrderItemForm,  # Używamy naszej nowej klasy z filtrowaniem
    extra=0,
    can_delete=True
)