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
        fields = ["category", "subcategory", "description", "urgency", "mode", "machines"]
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
        fields = ["status", "urgency", "responsible", "due_date"]
        widgets = {"due_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}
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
        fields = ["category", "subcategory", "description", "urgency", "mode", "machines"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Equipamentos antigos continuam editáveis mesmo quando desativados no catálogo.
        self.fields["machines"].queryset = Machine.objects.all()


class AttachmentForm(forms.Form):
    file = forms.FileField(label="Anexo (PNG, JPG ou PDF, até 5 MB)")

    def clean_file(self):
        from pathlib import Path
        file = self.cleaned_data["file"]
        if file.size > 5 * 1024 * 1024:
            raise forms.ValidationError("O limite por arquivo é 5 MB.")
        suffix = Path(file.name).suffix.lower()
        header = file.read(8)
        file.seek(0)
        valid = ((suffix == ".png" and header.startswith(b"\x89PNG\r\n\x1a\n")) or
                 (suffix in (".jpg", ".jpeg") and header.startswith(b"\xff\xd8\xff")) or
                 (suffix == ".pdf" and header.startswith(b"%PDF-")))
        if not valid:
            raise forms.ValidationError("Envie um arquivo PNG, JPG ou PDF válido.")
        return file
