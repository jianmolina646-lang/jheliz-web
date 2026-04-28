from django import forms

from .models import Ticket, TicketMessage


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
