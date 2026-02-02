from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User

class TenantUserCreateForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'role')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Dodajemy klasy Bootstrapa
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})


from django import forms
from .models import User


class TenantUserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        # Wybieramy pola, które Admin może zmieniać
        fields = ['first_name', 'last_name', 'email', 'role', 'is_active']
        labels = {
            'is_active': 'Konto aktywne (dostęp do systemu)',
            'role': 'Uprawnienia'
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Stylizujemy pola (oprócz checkboxa)
        for name, field in self.fields.items():
            if name != 'is_active':
                field.widget.attrs.update({'class': 'form-control'})
            else:
                field.widget.attrs.update({'class': 'form-check-input'})