from django import forms
from .models import Supplier
from inventory.models import Product

class SupplierForm(forms.ModelForm):

    products_selection = forms.ModelMultipleChoiceField(
        queryset=Product.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        label="Przypisane produkty"
    )

    class Meta:
        model = Supplier
        fields = ['name', 'nip', 'address', 'phone']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nazwa firmy'}),
            'nip': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'NIP'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Pełny adres'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Numer kontaktowy'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if user:
            # Filtrujemy listę wszystkich produktów firmy
            qs = Product.objects.filter(tenant=user.tenant)
            self.fields['products_selection'].queryset = qs

            # Jeśli edytujemy dostawcę, zaznaczamy te produkty, które już go mają
            if self.instance and self.instance.pk:
                # Używamy related_name='products' z Twojego modelu Product
                self.initial['products_selection'] = self.instance.products.all()