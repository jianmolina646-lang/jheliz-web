"""Formularios de Jheliz Control."""
from __future__ import annotations

from decimal import Decimal

from django import forms

from config.date_utils import add_service_duration
from django.utils import timezone

from .currencies import COUNTRY_CHOICES, CURRENCY_CHOICES, normalize_currency
from .models import Client, ControlSettings, Service, Subscription, Transaction


class ServiceForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = ("name", "category", "image", "icon", "color")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # `color` tiene default en el modelo; no obligamos a enviarlo.
        self.fields["color"].required = False

    def clean_color(self):
        return self.cleaned_data.get("color") or "#10b981"


class ClientForm(forms.ModelForm):
    whatsapp_opt_in = forms.BooleanField(
        label="El cliente autorizo recordatorios por WhatsApp", required=False,
    )

    class Meta:
        model = Client
        fields = ("name", "telegram", "whatsapp", "email", "notes")
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["whatsapp_opt_in"].initial = bool(
            self.instance and self.instance.whatsapp_opt_in_at
        )

    def save(self, commit=True):
        client = super().save(commit=False)
        accepted = self.cleaned_data.get("whatsapp_opt_in", False)
        client.whatsapp_opt_in_at = (
            client.whatsapp_opt_in_at or timezone.now()
        ) if accepted else None
        if commit:
            client.save()
            self.save_m2m()
        return client


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
            "plan", "profiles", "profile_name", "profile_pin", "plan_label",
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
        # Tienen default en el modelo: no obligamos a reenviarlos al editar.
        self.fields["cost"].required = False
        self.fields["investment"].required = False

    def clean(self):
        cleaned = super().clean()
        editing = bool(self.instance and self.instance.pk)

        # Costo / inversión: si no llegan, conservar el de la instancia o 0.
        if cleaned.get("cost") is None:
            cleaned["cost"] = self.instance.cost if editing else Decimal("0.00")
        if cleaned.get("investment") is None:
            cleaned["investment"] = self.instance.investment if editing else Decimal("0.00")

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
                cleaned["expires_at"] = add_service_duration(starts, int(days))

        # Perfiles entre 1 y 7.
        profiles = cleaned.get("profiles") or 1
        cleaned["profiles"] = max(1, min(7, int(profiles)))

        # Código ISO de moneda; el símbolo se resuelve sólo al mostrarlo.
        if not cleaned.get("currency"):
            cleaned["currency"] = "PEN"
        cleaned["currency"] = normalize_currency(cleaned["currency"])
        return cleaned


class TransactionForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = ("kind", "amount", "currency", "exchange_rate", "description", "client", "occurred_at")
        widgets = {
            "occurred_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["currency"].required = False
        self.fields["occurred_at"].required = False

    def clean_currency(self):
        return normalize_currency(self.cleaned_data.get("currency"))

    def clean_occurred_at(self):
        return self.cleaned_data.get("occurred_at") or timezone.now()


class ControlSettingsForm(forms.ModelForm):
    class Meta:
        model = ControlSettings
        fields = ("country", "currency")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["country"] = forms.ChoiceField(
            label="País", choices=COUNTRY_CHOICES,
            initial=getattr(self.instance, "country", "PE") or "PE",
        )

    def clean_currency(self):
        return normalize_currency(self.cleaned_data.get("currency"))
