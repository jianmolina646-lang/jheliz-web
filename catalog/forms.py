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
