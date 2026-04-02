from django import forms
from django.forms import inlineformset_factory
from .models import Product, ProductSupplier, ProductBatch

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'description', 'vat_rate', 'min_threshold', 'is_favourite']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'vat_rate': forms.NumberInput(attrs={'class': 'form-control', 'id': 'id_vat_rate'}),
            'min_threshold': forms.NumberInput(attrs={'class': 'form-control'}),
            'is_favourite': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

# Formset dla dostawców
SupplierFormSet = inlineformset_factory(
    Product,
    ProductSupplier,
    fields=('supplier', 'supplier_sku'),
    extra=0,            # Zaczynamy od 0, bo mamy przycisk "Dodaj"
    can_delete=True,
    widgets={
        'supplier': forms.Select(attrs={'class': 'form-select'}),
        'supplier_sku': forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Opcjonalne SKU'
        }),
    }
)

# Formset dla partii
BatchFormSet = inlineformset_factory(
    Product,
    ProductBatch,
    fields=('current_stock', 'net_price', 'gross_price'),
    extra=0,
    can_delete=True,
    widgets={
        'current_stock': forms.NumberInput(attrs={'class': 'form-control form-control-sm'}),
        'net_price': forms.NumberInput(attrs={
            'class': 'form-control form-control-sm net-price',
            'step': '0.01'
        }),
        'gross_price': forms.NumberInput(attrs={
            'class': 'form-control form-control-sm gross-price',
            'step': '0.01'
        }),
    }
)