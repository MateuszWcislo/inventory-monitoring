from django import forms
from .models import WorkOrder, WorkOrderProduct, WorkOrderService

class WorkOrderForm(forms.ModelForm):  # Tutaj była literówka
    class Meta:
        model = WorkOrder
        fields = ['name', 'description', 'client']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'np. Projekt X / Naprawa Y'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Dodatkowe informacje...'}),
            'client': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Imię i nazwisko lub nazwa firmy'}),
        }