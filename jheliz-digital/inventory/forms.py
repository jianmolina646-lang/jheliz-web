from django import forms

from .models import DigitalAccount


class DigitalAccountForm(forms.ModelForm):
    password = forms.CharField(
        label="Contraseña de la cuenta",
        required=False,
        strip=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Se cifra antes de guardar. Déjalo vacío al editar para conservar la actual.",
    )

    class Meta:
        model = DigitalAccount
        fields = (
            "service",
            "email",
            "password",
            "status",
            "purchase_date",
            "renewal_date",
            "acquisition_cost",
            "billing_method",
            "billing_reference",
            "country",
            "notes",
        )
        widgets = {
            "purchase_date": forms.DateInput(attrs={"type": "date"}),
            "renewal_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()

    def save(self, commit=True):
        account = super().save(commit=False)
        password = self.cleaned_data.get("password")
        if password:
            account.set_password(password)
        if commit:
            account.save()
        return account
