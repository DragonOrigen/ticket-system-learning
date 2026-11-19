"""Anexos privados, lixeira, notificações e relatórios simples."""
from pathlib import Path
from collections import Counter
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.admin.models import LogEntry, CHANGE, DELETION
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import F
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from django.utils.http import content_disposition_header
from django.views.decorators.http import require_POST, require_http_methods
from .models import Ticket, Attachment, Notification, Event
from .permissions import visible_tickets
from .notifications import notify_ticket


def require_admin(user):
    if not user.is_superuser:
        raise PermissionDenied


def audit(ticket, actor, text, flag=CHANGE):
    LogEntry.objects.log_actions(user_id=actor.pk, queryset=[ticket],
                                action_flag=flag, change_message=text)


def save_attachment(ticket, actor, file):
    # O bloqueio serializa o limite por ticket no PostgreSQL.
    with transaction.atomic():
        current = Ticket.objects.select_for_update().get(pk=ticket.pk)
        if current.deleted_at or current.attachments.count() >= 10:
            return False
        name = Path(file.name.replace('\\', '/')).name[:200]
        Attachment.objects.create(ticket=current, author=actor, name=name,
                                  size=file.size, data=file.read())
        Ticket.objects.filter(pk=current.pk).update(updated_at=timezone.now(), version=F('version') + 1)
        Event.objects.create(ticket=current, author=actor, text=f'Anexo enviado: {name}')
        notify_ticket(current, actor, 'Novo anexo no ticket.')
    return True


@login_required
@require_http_methods(['GET'])
def download(request, pk):
    attachment = get_object_or_404(Attachment.objects.filter(
        ticket_id__in=visible_tickets(request.user).values('pk')), pk=pk)
    # Sempre download: não renderizamos conteúdo enviado pelo usuário no domínio do site.
    response = HttpResponse(bytes(attachment.data), content_type='application/octet-stream')
    response['Content-Disposition'] = content_disposition_header(True, attachment.name)
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'private, no-store'
    return response


@login_required
@require_http_methods(['GET', 'POST'])
def ticket_trash(request, pk):
    require_admin(request.user)
    ticket = get_object_or_404(Ticket, pk=pk, deleted_at__isnull=True)
    if request.method == 'POST':
        if request.POST.get('confirm_code', '').strip() != ticket.code:
            return render(request, 'tickets/delete.html', {'ticket': ticket,
                'error': 'Digite o código do ticket para confirmar.'}, status=400)
        with transaction.atomic():
            ticket = get_object_or_404(Ticket.objects.select_for_update(), pk=pk, deleted_at__isnull=True)
            ticket.deleted_at = timezone.now()
            ticket.deleted_by = request.user
            ticket.version += 1
            ticket.save(update_fields=['deleted_at', 'deleted_by', 'version'])
            Event.objects.create(ticket=ticket, author=request.user, text='Movido para a lixeira.')
            audit(ticket, request.user, 'Movido para a lixeira.')
        messages.success(request, f'{ticket.code} movido para a lixeira.')
        return redirect('trash')
    return render(request, 'tickets/delete.html', {'ticket': ticket})


@login_required
@require_http_methods(['GET'])
def trash(request):
    require_admin(request.user)
    tickets = Ticket.objects.filter(deleted_at__isnull=False).select_related('deleted_by').order_by('-deleted_at', '-pk')
    return render(request, 'tickets/trash.html', {'page': Paginator(tickets, 25).get_page(request.GET.get('page'))})


@login_required
@require_POST
def restore(request, pk):
    require_admin(request.user)
    with transaction.atomic():
        ticket = get_object_or_404(Ticket.objects.select_for_update(), pk=pk, deleted_at__isnull=False)
        ticket.deleted_at = None
        ticket.deleted_by = None
        ticket.version += 1
        ticket.updated_at = timezone.now()
        ticket.save(update_fields=['deleted_at', 'deleted_by', 'version', 'updated_at'])
        Event.objects.create(ticket=ticket, author=request.user, text='Restaurado da lixeira.')
        audit(ticket, request.user, 'Restaurado da lixeira.')
        notify_ticket(ticket, request.user, 'Ticket restaurado da lixeira.')
    return redirect('ticket_detail', pk=pk)


@login_required
@require_http_methods(['GET', 'POST'])
def purge(request, pk):
    require_admin(request.user)
    ticket = get_object_or_404(Ticket, pk=pk, deleted_at__isnull=False)
    if request.method == 'POST':
        if request.POST.get('confirm_code', '').strip() != ticket.code:
            return render(request, 'tickets/delete.html', {'ticket': ticket, 'permanent': True,
                'error': 'Digite o código do ticket para confirmar.'}, status=400)
        with transaction.atomic():
            ticket = get_object_or_404(Ticket.objects.select_for_update(), pk=pk, deleted_at__isnull=False)
            audit(ticket, request.user, 'Exclusão definitiva pela lixeira.', DELETION)
            if hasattr(ticket, 'spreadsheet_import'):
                ticket.spreadsheet_import.delete()
            ticket.delete()
        messages.success(request, 'Ticket excluído definitivamente.')
        return redirect('trash')
    return render(request, 'tickets/delete.html', {'ticket': ticket, 'permanent': True})


@login_required
@require_http_methods(['GET', 'POST'])
def notifications(request):
    records = Notification.objects.filter(recipient=request.user,
        ticket_id__in=visible_tickets(request.user).values('pk')).select_related('ticket')
    if request.method == 'POST':
        notification_id = request.POST.get('notification_id', '')
        if not notification_id.isdigit():
            return HttpResponseBadRequest('Notificação inválida.')
        record = get_object_or_404(records, pk=notification_id)
        record.read_at = timezone.now()
        record.save(update_fields=['read_at'])
        return redirect('notifications')
    return render(request, 'tickets/notifications.html', {
        'page': Paginator(records, 25).get_page(request.GET.get('page')),
        'unread': records.filter(read_at__isnull=True).count()})


class ReportFilter(forms.Form):
    start = forms.DateField(label='Abertos a partir de', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    end = forms.DateField(label='Abertos até', required=False, widget=forms.DateInput(attrs={'type': 'date'}))

    def clean(self):
        data = super().clean()
        if data.get('start') and data.get('end') and data['start'] > data['end']:
            raise forms.ValidationError('A data inicial deve ser anterior ou igual à final.')
        return data


@login_required
@require_http_methods(['GET'])
def reports(request):
    form = ReportFilter(request.GET)
    tickets = visible_tickets(request.user)
    if form.is_valid():
        if form.cleaned_data['start']:
            tickets = tickets.filter(created_at__date__gte=form.cleaned_data['start'])
        if form.cleaned_data['end']:
            tickets = tickets.filter(created_at__date__lte=form.cleaned_data['end'])
    else:
        tickets = tickets.none()
    records = list(tickets)
    durations = [(t.completed_at - t.created_at).total_seconds() / 3600 for t in records
                 if t.status in ('resolvido', 'fechado') and t.completed_at and t.completed_at >= t.created_at]
    statuses = Counter(t.get_status_display() for t in records)
    subcategories = Counter(t.get_subcategory_display() or 'Sem subcategoria' for t in records)
    machines = Counter(str(machine) for t in records for machine in t.machines.all())
    return render(request, 'tickets/reports.html', {
        'form': form, 'total': len(records), 'overdue': sum(t.overdue for t in records),
        'average': sum(durations) / len(durations) if durations else None, 'sample': len(durations),
        'statuses': statuses.most_common(), 'subcategories': subcategories.most_common(),
        'machines': machines.most_common(10)})
