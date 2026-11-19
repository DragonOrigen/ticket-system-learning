from django.conf import settings
from django.db import models


class Machine(models.Model):
    name = models.CharField("nome", max_length=100, unique=True)
    active = models.BooleanField("ativa", default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "máquina"

    def __str__(self):
        return self.name


class Ticket(models.Model):
    class Category(models.TextChoices):
        HARDWARE = "hardware", "Hardware"
        SUPPORT = "suporte", "Suporte geral"
        SOFTWARE_ISSUE = "falha_software", "Problema de software"
        SOFTWARE = "software", "Instalação de software"
        MAINTENANCE = "manutencao", "Manutenção preventiva"
        OTHER = "outros", "Outros serviços"

    class Subcategory(models.TextChoices):
        PRACTICAL_CLASS = "aula_pratica", "Aula prática"
        HUB = "hub", "Hub"
        PERIODIC_MAINTENANCE = "manutencao_periodica", "Manutenção periódica"
        HEADPHONES = "fones", "Fones"
        KEYBOARDS = "teclados", "Teclados"
        EQUIPMENT = "equipamentos", "Equipamentos"
        PC_SUPPORT = "suporte_pc", "Suporte PC"
        MOV_EDU = "ticket_mov_edu", "Ticket Mov Edu"
        BRIGHT_MINDS = "mentes_brilhantes", "Mentes brilhantes"
        ROOM_ORGANIZATION = "organizacao_sala", "Organização da sala"

    subcategory = models.CharField("subcategoria", max_length=30,
                                   choices=Subcategory.choices, blank=True, default="")
    category = models.CharField("categoria", max_length=20, choices=Category.choices, default=Category.SUPPORT)

    class Status(models.TextChoices):
        NEW = "novo", "Novo"
        WORKING = "andamento", "Em Andamento"
        WAITING = "aguardando", "Aguardando Resposta"
        RESOLVED = "resolvido", "Resolvido"
        CLOSED = "fechado", "Fechado"

    class Urgency(models.TextChoices):
        LOW = "baixa", "Baixa"
        MEDIUM = "media", "Média"
        HIGH = "alta", "Alta"
        CRITICAL = "critica", "Crítica"

    description = models.TextField("descrição", max_length=10000)
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="requests")
    responsible = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="assignments", null=True, blank=True)
    urgency = models.CharField("urgência", max_length=10, choices=Urgency.choices, default=Urgency.MEDIUM)
    status = models.CharField("status", max_length=12, choices=Status.choices, default=Status.NEW)
    all_machines = models.BooleanField(default=False)
    machines = models.ManyToManyField(Machine, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    due_date = models.DateField("prazo de atendimento", null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="trashed_tickets")

    @property
    def overdue(self):
        from django.utils import timezone
        return bool(self.due_date and self.due_date < timezone.localdate()
                    and self.status not in ("resolvido", "fechado") and not self.deleted_at)


    class Meta:
        ordering = ["-created_at"]

    @property
    def code(self):
        return f"TKT-{self.pk:03d}"

    def __str__(self):
        return self.code


class Message(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    text = models.TextField(max_length=10000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]


class Event(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="events")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]


class SpreadsheetImport(models.Model):
    """Origem estável para não duplicar tickets ao reler a mesma planilha."""
    ticket = models.OneToOneField(Ticket, on_delete=models.PROTECT, related_name="spreadsheet_import")
    source = models.CharField(max_length=100)
    original_id = models.CharField(max_length=100)
    original_requester = models.CharField(max_length=150)
    original_equipment = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    replies = models.TextField(blank=True)
    imported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["source", "original_id"], name="unique_spreadsheet_ticket")]


class Attachment(models.Model):
    """Arquivos pequenos no banco: backup único e sem disco efêmero no deploy."""
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="attachments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    name = models.CharField(max_length=200)
    data = models.BinaryField()
    size = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)


class Notification(models.Model):
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE)
    text = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
