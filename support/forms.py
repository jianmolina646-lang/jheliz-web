from django import forms

from .models import CodeRequest, Ticket, TicketMessage


_INPUT_CLASS = (
    "w-full rounded-xl border border-white/10 bg-white/5 px-4 py-3 "
    "text-white placeholder-white/40 focus:border-fuchsia-400 focus:outline-none "
    "focus:ring-2 focus:ring-fuchsia-400/40"
)


class TicketCreateForm(forms.ModelForm):
    body = forms.CharField(
        label="Mensaje",
        widget=forms.Textarea(attrs={"rows": 5, "class": _INPUT_CLASS}),
    )

    class Meta:
        model = Ticket
        fields = ("subject", "order")
        labels = {"subject": "Asunto", "order": "Pedido relacionado (opcional)"}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["subject"].widget.attrs.setdefault("class", _INPUT_CLASS)
        self.fields["order"].widget.attrs.setdefault("class", _INPUT_CLASS)
        self.fields["order"].required = False
        if user is not None:
            self.fields["order"].queryset = user.orders.all()
        self.fields["order"].empty_label = "— Sin pedido —"


class TicketReplyForm(forms.Form):
    body = forms.CharField(
        label="Responder",
        widget=forms.Textarea(attrs={"rows": 4, "class": _INPUT_CLASS, "placeholder": "Escribe tu mensaje…"}),
    )


class CodeRequestForm(forms.ModelForm):
    """Formulario público/distribuidor para solicitar un código.

    Captura solo los datos que el cliente escribe; el resto (``audience``,
    ``user``, ``order``, ``ip_address``, ``user_agent``) se completa en la vista.
    """

    class Meta:
        model = CodeRequest
        fields = (
            "platform", "requested_code_type", "account_email",
            "contact_email", "order_number", "note",
        )
        labels = {
            "platform": "Plataforma",
            "requested_code_type": "¿Qué código necesitas?",
            "account_email": "Email de la cuenta",
            "contact_email": "Tu email de contacto (opcional)",
            "order_number": "N° de pedido (opcional)",
            "note": "Detalle adicional (opcional)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("platform", "requested_code_type", "account_email",
                     "contact_email", "order_number", "note"):
            self.fields[name].widget.attrs.setdefault("class", _INPUT_CLASS)

        self.fields["requested_code_type"].required = True
        # Reemplaza el empty label heredado del modelo (``blank=True``) por algo
        # amigable, manteniendo el valor "" como inválido al enviar.
        self.fields["requested_code_type"].choices = [
            ("", "— Selecciona qué código necesitas —"),
            *list(self.fields["requested_code_type"].choices)[1:],
        ]
        self.fields["account_email"].widget.attrs.setdefault(
            "placeholder", "ejemplo@gmail.com",
        )
        self.fields["contact_email"].widget.attrs.setdefault(
            "placeholder", "opcional",
        )
        self.fields["contact_email"].required = False
        self.fields["order_number"].widget.attrs.setdefault(
            "placeholder", "Ej: 1234",
        )
        self.fields["order_number"].required = False
        self.fields["note"].required = False
        self.fields["note"].widget.attrs.setdefault(
            "placeholder", "Ej: pide código desde un Smart TV LG",
        )
