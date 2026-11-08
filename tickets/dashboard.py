"""Indicadores operacionais simples. Limites em dias, sem pontuação opaca."""
from django.utils import timezone

SUPPORT_CATEGORIES = ("hardware", "suporte", "falha_software")
CLOSED_STATUSES = ("resolvido", "fechado")
OLD_DAYS = 7
STALE_DAYS = 3
PRIORITY = {"critica": 0, "alta": 1, "media": 2, "baixa": 3}


def build_dashboard(tickets, technician):
    records = list(tickets)
    opened = [t for t in records if t.status not in CLOSED_STATUSES]
    result = {"total": len(records), "opened": len(opened),
              "closed": len(records) - len(opened),
              "waiting": sum(t.status == "aguardando" for t in opened)}
    if not technician:
        return result
    now = timezone.now()
    alerts = []
    for ticket in opened:
        reasons = []
        if (now - ticket.created_at).days >= OLD_DAYS:
            reasons.append(f"Aberto há pelo menos {OLD_DAYS} dias")
        if (now - ticket.updated_at).days >= STALE_DAYS:
            reasons.append(f"Sem atualização há pelo menos {STALE_DAYS} dias")
        if ticket.urgency == "critica" and not ticket.responsible_id:
            reasons.append("Crítico sem responsável")
        if reasons:
            alerts.append({"ticket": ticket, "reasons": reasons})
    result["alerts"] = alerts
    result["priority"] = sorted(opened, key=lambda t: (
        PRIORITY[t.urgency], t.responsible_id is not None, t.created_at))[:10]
    return result
