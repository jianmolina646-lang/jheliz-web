from django import forms


class AddToCartForm(forms.Form):
    plan_id = forms.IntegerField(widget=forms.HiddenInput)
    quantity = forms.IntegerField(
        min_value=1, max_value=10, initial=1,
        widget=forms.NumberInput(attrs={"class": "form-input", "min": 1, "max": 10}),
    )
    profile_name = forms.CharField(
        label="Nombre del perfil",
        max_length=60, required=False,
        help_text="Ej: Jhonatan. Lo pondremos en tu perfil al crearlo.",
        widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "Jhonatan"}),
    )
    pin = forms.CharField(
        label="PIN (4 d\u00edgitos)",
        max_length=8, required=False,
        widget=forms.TextInput(attrs={
            "class": "form-input", "inputmode": "numeric",
            "pattern": "[0-9]*", "placeholder": "1234",
        }),
    )
    notes = forms.CharField(
        label="Notas (opcional)",
        required=False,
        widget=forms.Textarea(attrs={
            "class": "form-input", "rows": 2,
            "placeholder": "Ej: ponlo en espa\u00f1ol, av\u00edsame por correo",
        }),
    )


class CheckoutForm(forms.Form):
    """Datos de contacto del comprador. Los datos por item se editan en el carrito."""

    PAYMENT_METHODS = (
        ("mercadopago", "Tarjeta / Yape QR por Mercado Pago"),
        ("yape", "Yape directo (pago con QR y comprobante)"),
    )

    full_name = forms.CharField(
        label="Nombre completo", max_length=120,
        widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "Tu nombre y apellido"}),
    )
    email = forms.EmailField(
        label="Correo electr\u00f3nico",
        widget=forms.EmailInput(attrs={"class": "form-input", "placeholder": "tu@correo.com"}),
    )
    phone = forms.CharField(
        label="Tel\u00e9fono / WhatsApp",
        max_length=30, required=False,
        widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "+51 999 999 999"}),
    )
    payment_method = forms.ChoiceField(
        label="M\u00e9todo de pago",
        choices=PAYMENT_METHODS,
        initial="mercadopago",
        widget=forms.RadioSelect(attrs={"class": "payment-method-radio"}),
    )
    accept_terms = forms.BooleanField(
        label="Acepto los t\u00e9rminos y la pol\u00edtica de garant\u00eda.",
        required=True,
    )


class YapeProofForm(forms.Form):
    """Subida del comprobante Yape (captura)."""

    proof = forms.ImageField(
        label="Captura del comprobante",
        widget=forms.ClearableFileInput(attrs={
            "accept": "image/*",
            "class": "form-input",
        }),
        help_text="Sube la captura de Yape donde se vea el monto y el destinatario.",
    )

    def clean_proof(self):
        proof = self.cleaned_data.get("proof")
        if proof and proof.size > 8 * 1024 * 1024:
            raise forms.ValidationError("La imagen pesa m\u00e1s de 8 MB. Reduce la resoluci\u00f3n.")
        return proof
