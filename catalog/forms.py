from django import forms

from .models import ProductReview


class ProductReviewForm(forms.ModelForm):
    """Formulario p\u00fablico que el cliente usa al llegar v\u00eda link m\u00e1gico."""

    rating = forms.TypedChoiceField(
        label="\u00bfQu\u00e9 le pondr\u00edas?",
        coerce=int,
        choices=[(i, f"{i} \u2605") for i in range(5, 0, -1)],
        initial=5,
        widget=forms.RadioSelect,
    )

    class Meta:
        model = ProductReview
        fields = ("author_name", "city", "rating", "title", "comment", "photo")
        labels = {
            "author_name": "\u00bfC\u00f3mo te llamamos?",
            "city": "Ciudad (opcional)",
            "title": "T\u00edtulo corto (opcional)",
            "comment": "Cu\u00e9ntanos c\u00f3mo te fue",
            "photo": "Sube una foto (opcional)",
        }
        widgets = {
            "comment": forms.Textarea(attrs={"rows": 5, "placeholder": "Ej. La cuenta lleg\u00f3 en 2 minutos y todo bien."}),
            "title": forms.TextInput(attrs={"placeholder": "Ej. Top, lleg\u00f3 en minutos"}),
            "author_name": forms.TextInput(attrs={"placeholder": "Carla M."}),
            "city": forms.TextInput(attrs={"placeholder": "Lima"}),
        }

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        if photo and photo.size > 2 * 1024 * 1024:
            raise forms.ValidationError("La foto no debe pesar m\u00e1s de 2 MB.")
        return photo

    def clean_comment(self):
        comment = (self.cleaned_data.get("comment") or "").strip()
        if len(comment) < 10:
            raise forms.ValidationError("Cu\u00e9ntanos un poquito m\u00e1s (m\u00ednimo 10 caracteres).")
        return comment


class ReclamacionForm(forms.ModelForm):
    """Formulario público del Libro de Reclamaciones (Indecopi).

    Validaciones extra:
    - Si es_menor=True → padre_nombre y padre_documento son obligatorios.
    - documento_numero formato básico (DNI 8 dígitos numéricos).
    """

    declaracion_jurada = forms.BooleanField(
        label=("Declaro bajo juramento que la información proporcionada es "
               "verdadera y autorizo el tratamiento de mis datos para "
               "atender este reclamo (Ley 29733)."),
        required=True,
    )

    class Meta:
        from .models import Reclamacion
        model = Reclamacion
        fields = (
            "nombre", "documento_tipo", "documento_numero",
            "domicilio", "telefono", "email",
            "es_menor", "padre_nombre", "padre_documento",
            "tipo_bien", "monto", "descripcion_bien", "pedido_referencia",
            "tipo", "detalle", "pedido_consumidor",
        )
        widgets = {
            "detalle": forms.Textarea(attrs={
                "rows": 5,
                "placeholder": "Describe lo que sucedió. Sé claro/a y específico/a.",
            }),
            "pedido_consumidor": forms.Textarea(attrs={
                "rows": 3,
                "placeholder": "Ej. Solicito reposición de la cuenta o devolución del importe pagado.",
            }),
            "descripcion_bien": forms.TextInput(attrs={
                "placeholder": "Ej. Cuenta Netflix Premium 1 mes",
            }),
            "pedido_referencia": forms.TextInput(attrs={
                "placeholder": "Ej. AB12CD (opcional)",
            }),
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("es_menor"):
            if not cleaned.get("padre_nombre"):
                self.add_error(
                    "padre_nombre",
                    "Si eres menor de edad, este campo es obligatorio.",
                )
            if not cleaned.get("padre_documento"):
                self.add_error(
                    "padre_documento",
                    "Si eres menor de edad, este campo es obligatorio.",
                )
        doc_tipo = cleaned.get("documento_tipo")
        doc_num = (cleaned.get("documento_numero") or "").strip()
        if doc_tipo == "DNI" and doc_num and (not doc_num.isdigit() or len(doc_num) != 8):
            self.add_error(
                "documento_numero",
                "El DNI peruano debe tener exactamente 8 dígitos.",
            )
        return cleaned
