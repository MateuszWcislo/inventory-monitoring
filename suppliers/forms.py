from django import forms
from .models import Supplier
from inventory.models import Product

class SupplierForm(forms.ModelForm):
    products = forms.ModelMultipleChoiceField(
        queryset=Product.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        label="Asortyment produktów"
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
        # 1. Wyciągamy user zanim super() go "zje"
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # 2. Filtrowanie (Kluczowe dla Multi-tenancy)
        if user and 'products' in self.fields:
            self.fields['products'].queryset = Product.objects.filter(tenant=user.tenant)

        # Opcjonalnie: dodanie klasy bootstrapowej do checkboxów, jeśli nie masz tego w Meta
        if 'products' in self.fields:
            self.fields['products'].help_text = "Produkty przypisane do tego dostawcy."

    def save(self, commit=True):
        supplier = super().save(commit=commit)
        if commit:
            # Zapisujemy relację ManyToMany
            supplier.products.set(self.cleaned_data['products'])
        return supplier