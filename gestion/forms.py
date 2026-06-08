"""Formularios de Jheliz Control."""
from __future__ import annotations

from django import forms
from django.utils import timezone

from .models import Client, Service, Subscription, Transaction


class ServiceForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = ("name", "category", "image", "icon", "color")


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ("name", "telegram", "whatsapp", "email", "notes")
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 2}),
        }


class SubscriptionForm(forms.ModelForm):
    # Permitimos crear cliente nuevo al vuelo desde el mismo formulario.
    duration_days = forms.IntegerField(
        label="Duración (días)", min_value=1, initial=30, required=False,
        help_text="Si no ponés 'Vence', se calcula desde el inicio + estos días.",
    )

    class Meta:
        model = Subscription
        fields = (
            "client", "service", "account_email", "account_password",
            "plan", "profiles", "profile_name", "profile_pin",
            "currency", "cost", "investment",
            "starts_at", "expires_at",
        )
        widgets = {
            "starts_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "expires_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["expires_at"].required = False
        self.fields["starts_at"].required = False
        self.fields["currency"].required = False

    def clean(self):
        cleaned = super().clean()
        editing = bool(self.instance and self.instance.pk)

        # Inicio: si no llega, conservar el de la instancia (al editar) o ahora.
        starts = cleaned.get("starts_at")
        if not starts:
            starts = self.instance.starts_at if editing and self.instance.starts_at else timezone.now()
        cleaned["starts_at"] = starts

        # Vencimiento: si no llega, conservar el de la instancia (al editar);
        # si es nueva, calcular desde el inicio + duración en días.
        if not cleaned.get("expires_at"):
            if editing and self.instance.expires_at:
                cleaned["expires_at"] = self.instance.expires_at
            else:
                days = cleaned.get("duration_days") or 30
                cleaned["expires_at"] = starts + timezone.timedelta(days=int(days))

        # Perfiles entre 1 y 7.
        profiles = cleaned.get("profiles") or 1
        cleaned["profiles"] = max(1, min(7, int(profiles)))

        # Moneda por defecto USD.
        if not cleaned.get("currency"):
            cleaned["currency"] = "USD"
        return cleaned


class TransactionForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = ("kind", "amount", "currency", "description", "client", "occurred_at")
        widgets = {
            "occurred_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["currency"].required = False
        self.fields["occurred_at"].required = False

    def clean_currency(self):
        return self.cleaned_data.get("currency") or "USD"

    def clean_occurred_at(self):
        return self.cleaned_data.get("occurred_at") or timezone.now()
