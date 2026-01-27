from django import forms
from .models import Product

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        # Dodaj 'description' do listy pól, jeśli chcesz go używać!
        fields = [
            'name', 'sku', 'description', 'current_stock',
            'min_threshold', 'default_supplier', 'suppliers'
        ]

        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'sku': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'current_stock': forms.NumberInput(attrs={'class': 'form-control'}),
            'min_threshold': forms.NumberInput(attrs={'class': 'form-control'}),
            'default_supplier': forms.Select(attrs={'class': 'form-select'}),
            'suppliers': forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        }

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            # Dodatkowa klasa dla kontenera checkboxów (opcjonalnie),
            # aby nie były zbite ciasno obok siebie.
            self.fields['suppliers'].help_text = "Zaznacz wszystkich dostawców, od których możesz zamawiać ten produkt."