from django import forms

from inventory.models import DigitalAccount

from .models import Replacement


class ReplacementForm(forms.ModelForm):
    class Meta:
        model = Replacement
        fields = ("original_account", "replacement_account", "reason", "replaced_at", "notes")
        widgets = {
            "replaced_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["original_account"].queryset = DigitalAccount.objects.filter(
            status=DigitalAccount.Status.SOLD,
            replacement_outgoing__isnull=True,
        ).select_related("service")
        replacements = DigitalAccount.objects.filter(
            status=DigitalAccount.Status.AVAILABLE,
            replacement_incoming__isnull=True,
        ).select_related("service")
        original_id = self.data.get("original_account") or self.initial.get("original_account")
        if str(original_id).isdigit():
            original = DigitalAccount.objects.filter(pk=original_id).first()
            if original:
                replacements = replacements.filter(service=original.service)
        self.fields["replacement_account"].queryset = replacements
        self.fields["replaced_at"].input_formats = ("%Y-%m-%dT%H:%M",)

    def clean(self):
        cleaned_data = super().clean()
        original = cleaned_data.get("original_account")
        replacement = cleaned_data.get("replacement_account")
        if original and original.status != DigitalAccount.Status.SOLD:
            self.add_error("original_account", "La cuenta anterior debe estar vendida.")
        if replacement and replacement.status != DigitalAccount.Status.AVAILABLE:
            self.add_error("replacement_account", "La cuenta de reposición ya no está disponible.")
        if original and replacement and original.service_id != replacement.service_id:
            self.add_error("replacement_account", "Selecciona una cuenta del mismo servicio.")
        return cleaned_data
