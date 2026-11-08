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
    machines = models.ManyToManyField(Machine, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)

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
