from django import forms
from .models import Supplier

class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ['name', 'nip', 'address', 'phone']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nazwa firmy'}),
            'nip': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'NIP'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Pełny adres'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Numer kontaktowy'}),
        }