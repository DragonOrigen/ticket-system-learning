"""Somente campos permitidos entram na ordenação enviada ao banco."""
from django.db.models import Case, When, Value, IntegerField, F

SORT_CHOICES = [
    ("newest", "Data: mais recentes"), ("oldest", "Data: mais antigos"),
    ("id_asc", "ID: crescente"), ("id_desc", "ID: decrescente"),
    ("updated", "Última atualização"), ("urgency", "Maior urgência"),
    ("deadline", "Prazo mais próximo"), ("status", "Status"),
]


def sort_tickets(tickets, selected):
    if selected not in dict(SORT_CHOICES):
        selected = "newest"
    if selected == "urgency":
        tickets = tickets.annotate(urgency_order=Case(
            *[When(urgency=value, then=Value(i)) for i, value in enumerate(
                ("critica", "alta", "media", "baixa"))], default=4, output_field=IntegerField()))
        fields = ("urgency_order", "created_at", "pk")
    elif selected == "deadline":
        fields = (F("due_date").asc(nulls_last=True), "pk")
    elif selected == "status":
        tickets = tickets.annotate(status_order=Case(
            *[When(status=value, then=Value(i)) for i, value in enumerate(
                ("novo", "andamento", "aguardando", "resolvido", "fechado"))], default=5, output_field=IntegerField()))
        fields = ("status_order", "-pk")
    else:
        fields = {"newest": ("-created_at", "-pk"), "oldest": ("created_at", "pk"),
                  "id_asc": ("pk",), "id_desc": ("-pk",), "updated": ("-updated_at", "-pk")}[selected]
    return tickets.order_by(*fields), selected
