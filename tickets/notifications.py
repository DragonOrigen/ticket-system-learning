"""Notificações internas para os participantes; nenhuma mensagem externa."""
from .models import Notification
from .permissions import technicians


def notify_ticket(ticket, actor, text):
    recipients = {ticket.requester_id}
    if ticket.responsible_id:
        recipients.add(ticket.responsible_id)
    else:
        recipients.update(technicians().values_list("pk", flat=True))
    recipients.discard(actor.pk)
    Notification.objects.bulk_create([
        Notification(recipient_id=pk, ticket=ticket, text=text) for pk in recipients
    ])
