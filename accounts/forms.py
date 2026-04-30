from django import forms
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordResetForm,
    SetPasswordForm,
    UserCreationForm,
)

from .models import Role, User


class StyledMixin:
    """Add Tailwind classes to every widget automatically."""

    default_input_class = (
        "w-full rounded-xl border border-white/10 bg-white/5 px-4 py-3 "
        "text-white placeholder-white/40 focus:border-fuchsia-400 focus:outline-none "
        "focus:ring-2 focus:ring-fuchsia-400/40"
    )

    def _style_fields(self):
        for field in self.fields.values():
            widget = field.widget
            widget.attrs.setdefault("class", self.default_input_class)
            if field.label and "placeholder" not in widget.attrs:
                widget.attrs["placeholder"] = field.label


class SignupForm(StyledMixin, UserCreationForm):
    email = forms.EmailField(required=True, label="Correo electr\u00f3nico")
    phone = forms.CharField(required=False, max_length=30, label="WhatsApp")
    telegram_username = forms.CharField(
        required=False, max_length=60, label="Usuario de Telegram (opcional)"
    )
    role = forms.ChoiceField(
        choices=[
            (Role.CLIENTE, "Cliente (compro para m\u00ed)"),
            (Role.DISTRIBUIDOR, "Distribuidor (quiero revender)"),
        ],
        label="\u00bfC\u00f3mo te registras?",
        widget=forms.RadioSelect,
    )

    class Meta:
        model = User
        fields = ("username", "email", "phone", "telegram_username", "role",
                  "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style_fields()
        # Don't style radio buttons as text inputs
        self.fields["role"].widget.attrs.pop("class", None)

    def save(self, commit: bool = True) -> User:
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.phone = self.cleaned_data.get("phone", "")
        user.telegram_username = self.cleaned_data.get("telegram_username", "")
        user.role = self.cleaned_data["role"]
        if commit:
            user.save()
        return user


class LoginForm(StyledMixin, AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style_fields()


class JhelizPasswordResetForm(StyledMixin, PasswordResetForm):
    """Pide el email para mandar el link de reset.

    Hereda el comportamiento built-in: si el email no existe, el form
    devuelve éxito igual (no enumera cuentas), pero no manda correo.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style_fields()


class JhelizSetPasswordForm(StyledMixin, SetPasswordForm):
    """Form para definir la nueva contraseña tras validar el token."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style_fields()


class ProfileForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "phone", "telegram_username")
        labels = {
            "first_name": "Nombres",
            "last_name": "Apellidos",
            "email": "Correo",
            "phone": "WhatsApp",
            "telegram_username": "Telegram",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style_fields()
