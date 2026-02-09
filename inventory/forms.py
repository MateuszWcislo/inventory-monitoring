from django import forms
from .models import Product
from suppliers.models import Supplier

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        # Dodaj 'description' do listy pól, jeśli chcesz go używać!
        fields = [
            'name', 'sku', 'description', 'current_stock',
            'min_threshold', 'suppliers'
        ]

        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'sku': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'current_stock': forms.NumberInput(attrs={'class': 'form-control'}),
            'min_threshold': forms.NumberInput(attrs={'class': 'form-control'}),
            'suppliers': forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        # Wyciągamy 'user', którego przekazujemy w widoku
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if user:
            self.fields['suppliers'].queryset = Supplier.objects.filter(tenant=user.tenant)

        self.fields['suppliers'].help_text = "Zaznacz wszystkich dostawców, od których możesz zamawiać ten produkt."