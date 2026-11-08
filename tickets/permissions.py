from django.db.models import Q
from django.contrib.auth import get_user_model


def is_technician(user):
    return user.is_superuser or user.groups.filter(name="Tecnicos").exists()


def technicians():
    return get_user_model().objects.filter(is_active=True).filter(
        Q(is_superuser=True) | Q(groups__name="Tecnicos")
    ).distinct()


def visible_tickets(user):
    from .models import Ticket
    tickets = Ticket.objects.select_related("requester", "responsible").prefetch_related("machines")
    return tickets if is_technician(user) else tickets.filter(requester=user)
