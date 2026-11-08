from django import forms
from .models import Ticket, Machine
from .permissions import technicians


class TicketForm(forms.ModelForm):
    mode = forms.ChoiceField(label="Equipamento", choices=[
        ("uma", "Uma máquina"), ("varias", "Várias"), ("todas", "Todas as máquinas cadastradas"),
        ("nenhuma", "Sem equipamento"),
    ])
    machines = forms.ModelMultipleChoiceField(label="Máquinas", queryset=Machine.objects.filter(active=True),
                                              widget=forms.CheckboxSelectMultiple, required=False)

    class Meta:
        model = Ticket
        fields = ["category", "description", "urgency", "mode", "machines"]
        widgets = {"description": forms.Textarea(attrs={"rows": 5})}

    def clean(self):
        data = super().clean()
        mode, machines = data.get("mode"), data.get("machines")
        if machines is None:
            return data
        if mode == "uma" and len(machines) != 1:
            self.add_error("machines", "Selecione exatamente uma máquina.")
        elif mode == "varias" and len(machines) < 2:
            self.add_error("machines", "Selecione pelo menos duas máquinas.")
        elif mode == "todas":
            data["machines"] = Machine.objects.all()
            if not data["machines"].exists():
                self.add_error("mode", "Cadastre máquinas antes de usar Todas.")
        elif mode == "nenhuma":
            data["machines"] = Machine.objects.none()
        return data


class AttendanceForm(forms.ModelForm):
    version = forms.IntegerField(widget=forms.HiddenInput)

    class Meta:
        model = Ticket
        fields = ["status", "urgency", "responsible"]
        labels = {"responsible": "Responsável"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["responsible"].queryset = technicians()


class MessageForm(forms.Form):
    text = forms.CharField(label="Nova observação / resposta", max_length=10000,
                           widget=forms.Textarea(attrs={"rows": 4}))


class EditTicketForm(TicketForm):
    version = forms.IntegerField(widget=forms.HiddenInput)

    class Meta(TicketForm.Meta):
        fields = ["category", "description", "urgency", "mode", "machines"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Equipamentos antigos continuam editáveis mesmo quando desativados no catálogo.
        self.fields["machines"].queryset = Machine.objects.all()
