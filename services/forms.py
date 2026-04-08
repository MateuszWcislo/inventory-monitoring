from django import forms
from .models import Service

class ServiceForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = ['name', 'net_price', 'vat_rate']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'np. Wymiana tarcz'}),
            'net_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'vat_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }