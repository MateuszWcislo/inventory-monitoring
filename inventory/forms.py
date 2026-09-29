from django import forms
from django.forms import inlineformset_factory
from django.forms.models import BaseInlineFormSet
from .models import Product, ProductSupplier, ProductBatch
from suppliers.models import Supplier


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'description', 'vat_rate', 'min_threshold', 'target_stock', 'is_favourite']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'vat_rate': forms.NumberInput(attrs={'class': 'form-control', 'id': 'id_vat_rate', 'step': '0.01'}),
            'min_threshold': forms.NumberInput(attrs={'class': 'form-control'}),
            'target_stock': forms.NumberInput(attrs={'class': 'form-control'}),
            'is_favourite': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance._state.adding:
            self.fields['vat_rate'].initial = 23.00

    def clean(self):
        cleaned_data = super().clean()
        min_val = cleaned_data.get("min_threshold")
        target_val = cleaned_data.get("target_stock")

        if target_val is not None and min_val is not None:
            if target_val < min_val:
                self.add_error('target_stock', "Stan docelowy nie może być mniejszy niż próg minimalny.")

        return cleaned_data


class BaseSupplierInlineFormSet(BaseInlineFormSet):
    def __init__(self, *args, **kwargs):
        self.tenant = kwargs.pop('tenant', None)
        super().__init__(*args, **kwargs)
        if self.tenant:
            for form in self.forms:
                form.fields['supplier'].queryset = Supplier.objects.filter(tenant=self.tenant)

    def _construct_form(self, i, **kwargs):
        form = super()._construct_form(i, **kwargs)
        if self.tenant:
            form.fields['supplier'].queryset = Supplier.objects.filter(tenant=self.tenant)
        return form

    @property
    def empty_form(self):
        form = super().empty_form
        if self.tenant:
            form.fields['supplier'].queryset = Supplier.objects.filter(tenant=self.tenant)
        return form


SupplierFormSet = inlineformset_factory(
    Product,
    ProductSupplier,
    formset=BaseSupplierInlineFormSet,
    fields=('supplier', 'supplier_sku'),
    extra=0,
    can_delete=True,
    widgets={
        'supplier': forms.Select(attrs={'class': 'form-select'}),
        'supplier_sku': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Kod SKU'}),
    }
)

BatchFormSet = inlineformset_factory(
    Product,
    ProductBatch,
    fields=('current_stock', 'net_price', 'gross_price'),
    extra=0,
    can_delete=True,
    widgets={
        'current_stock': forms.NumberInput(attrs={'class': 'form-control form-control-sm'}),
        'net_price': forms.NumberInput(attrs={'class': 'form-control form-control-sm net-price', 'step': '0.01'}),
        'gross_price': forms.NumberInput(attrs={'class': 'form-control form-control-sm gross-price', 'step': '0.01'}),
    }
)
