# suppliers/forms.py
from django import forms
from .models import Supplier
from inventory.models import Product


class SupplierForm(forms.ModelForm):
    # Używamy ModelMultipleChoiceField, bo daje nam łatwą listę wszystkich produktów
    products_selection = forms.ModelMultipleChoiceField(
        queryset=Product.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input product-cb'}),
        label="Asortyment"
    )

    class Meta:
        model = Supplier
        fields = ['name', 'nip', 'address', 'phone', 'representative', 'email', 'website']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'nip': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'representative': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'website': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields['products_selection'].queryset = Product.objects.filter(tenant=user.tenant).order_by('name')

            if self.instance.pk:
                # Pobieramy aktualnie przypisane produkty dla initiala
                self.fields['products_selection'].initial = Product.objects.filter(
                    supplier_mappings__supplier=self.instance
                )