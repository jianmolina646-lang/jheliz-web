from django import forms

from inventory.models import DigitalAccount

from .models import Sale


class SaleForm(forms.ModelForm):
    class Meta:
        model = Sale
        fields = ("account", "amount", "payment_method", "payment_reference", "sold_at", "notes")
        widgets = {
            "sold_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["account"].queryset = DigitalAccount.objects.filter(
            status=DigitalAccount.Status.AVAILABLE
        ).select_related("service")
        self.fields["sold_at"].input_formats = ("%Y-%m-%dT%H:%M",)

    def clean_account(self):
        account = self.cleaned_data["account"]
        if account.status != DigitalAccount.Status.AVAILABLE:
            raise forms.ValidationError("La cuenta ya no está disponible para venta.")
        return account
