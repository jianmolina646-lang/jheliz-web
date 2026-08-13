from django import forms
from django.utils.text import slugify

from .models import DigitalService


class DigitalServiceForm(forms.ModelForm):
    class Meta:
        model = DigitalService
        fields = ("name", "color", "is_active")
        widgets = {"color": forms.TextInput(attrs={"type": "color"})}

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if DigitalService.objects.filter(slug=slugify(name)).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ya existe un servicio con un nombre equivalente.")
        return name
