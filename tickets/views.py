from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q, F
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from .forms import TicketForm, AttendanceForm, MessageForm, EditTicketForm
from .models import Ticket, Message, Event
from .permissions import is_technician, visible_tickets
from .dashboard import SUPPORT_CATEGORIES, build_dashboard
from django.core.paginator import Paginator
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseBadRequest


@login_required
def ticket_list(request, area=None):
    tickets = visible_tickets(request.user)
    if area == "support":
        tickets = tickets.filter(category__in=SUPPORT_CATEGORIES)
    elif area == "tasks":
        tickets = tickets.exclude(category__in=SUPPORT_CATEGORIES)
    query = request.GET.get("q", "").strip()
    if query:
        search = Q(description__icontains=query) | Q(machines__name__icontains=query)
        number = query.upper().removeprefix("TKT-")
        if number.isdigit():
            search |= Q(pk=int(number))
        tickets = tickets.filter(search).distinct()
    status = request.GET.get("status", "")
    urgency = request.GET.get("urgency", "")
    category = request.GET.get("category", "")
    if category:
        tickets = tickets.filter(category=category)
    if status:
        tickets = tickets.filter(status=status)
    if urgency:
        tickets = tickets.filter(urgency=urgency)
    return render(request, "tickets/list.html", {
        "page": Paginator(tickets, 25).get_page(request.GET.get("page")), "query": query,
        "statuses": Ticket.Status.choices, "urgencies": Ticket.Urgency.choices,
        "area": area, "title": {"support": "Suporte de software / hardware", "tasks": "Tarefas e serviços"}.get(area, "Todos os chamados"),
        "selected_status": status, "selected_urgency": urgency,
        "categories": Ticket.Category.choices, "selected_category": category,
    })


@login_required
def ticket_create(request):
    form = TicketForm(request.POST or None, initial={"category": "manutencao" if request.GET.get("area") == "tasks" else "suporte"})
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            ticket = form.save(commit=False)
            ticket.all_machines = form.cleaned_data["mode"] == "todas"
            ticket.requester = request.user
            ticket.save()
            form.save_m2m()
            Event.objects.create(ticket=ticket, author=request.user, text="Ticket aberto.")
        return redirect("ticket_detail", pk=ticket.pk)
    return render(request, "tickets/form.html", {"form": form})


@login_required
def ticket_detail(request, pk):
    # A checagem se aplica tanto à leitura quanto às mensagens e alterações.
    ticket = get_object_or_404(visible_tickets(request.user), pk=pk)
    technician = is_technician(request.user)
    attendance = AttendanceForm(instance=ticket, initial={"version": ticket.version})
    note = MessageForm()
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "message":
            note = MessageForm(request.POST)
            if note.is_valid():
                with transaction.atomic():
                    Message.objects.create(ticket=ticket, author=request.user, text=note.cleaned_data["text"])
                    Ticket.objects.filter(pk=pk).update(updated_at=timezone.now(), version=F("version") + 1)
                return redirect("ticket_detail", pk=pk)
        elif action == "attendance":
            if not technician:
                raise PermissionDenied
            previous = {field: getattr(ticket, field) for field in ("status", "urgency", "responsible_id")}
            attendance = AttendanceForm(request.POST, instance=ticket)
            if attendance.is_valid():
                data = attendance.cleaned_data
                now = timezone.now()
                completed = (ticket.completed_at or now) if data["status"] in ("resolvido", "fechado") else None
                with transaction.atomic():
                    # Comparação e atualização em uma instrução: impede sobrescrever versão antiga.
                    changed = Ticket.objects.filter(pk=pk, version=data["version"]).update(
                        status=data["status"], urgency=data["urgency"], responsible=data["responsible"],
                        completed_at=completed, updated_at=now, version=F("version") + 1,
                    )
                    if changed:
                        details = []
                        for field in previous:
                            value = getattr(ticket, field)
                            if previous[field] != value:
                                details.append(f"{field}: {previous[field]} → {value}")
                        Event.objects.create(ticket=ticket, author=request.user,
                                             text="; ".join(details) or "Atendimento atualizado.")
                if changed:
                    messages.success(request, "Atendimento atualizado.")
                    return redirect("ticket_detail", pk=pk)
                attendance.add_error(None, "Outro usuário atualizou o chamado. Recarregue a página antes de salvar.")
        else:
            return HttpResponseBadRequest("Ação inválida.")
    return render(request, "tickets/detail.html", {"ticket": ticket, "technician": technician,
                                                    "attendance": attendance, "note": note})


@login_required
def dashboard(request):
    technician = is_technician(request.user)
    area = request.GET.get("area", "all")
    if area not in ("all", "support", "tasks"):
        area = "all"
    tickets = visible_tickets(request.user)
    if area == "support":
        tickets = tickets.filter(category__in=SUPPORT_CATEGORIES)
    elif area == "tasks":
        tickets = tickets.exclude(category__in=SUPPORT_CATEGORIES)
    context = build_dashboard(tickets, technician)
    context["selected_area"] = area
    context["dashboard_filters"] = [("all", "Todos"), ("support", "Suporte"), ("tasks", "Tarefas")]
    context["technician"] = technician
    return render(request, "tickets/dashboard.html", context)


@login_required
def help_page(request):
    return render(request, "tickets/help.html")


@login_required
def ticket_edit(request, pk):
    ticket = get_object_or_404(visible_tickets(request.user), pk=pk)
    count = ticket.machines.count()
    initial = {"version": ticket.version, "mode": "todas" if ticket.all_machines else ("nenhuma" if not count else ("uma" if count == 1 else "varias"))}
    previous = {key: getattr(ticket, key) for key in ("category", "description", "urgency", "all_machines")}
    previous_machines = set(ticket.machines.values_list("pk", flat=True))
    form = EditTicketForm(request.POST or None, instance=ticket, initial=initial)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        data["all_machines"] = data["mode"] == "todas"
        with transaction.atomic():
            changed = Ticket.objects.filter(pk=pk, version=data["version"]).update(
                category=data["category"], description=data["description"], urgency=data["urgency"],
                all_machines=data["all_machines"],
                updated_at=timezone.now(), version=F("version") + 1)
            if changed:
                changes = [f"{key}: {previous[key]} → {data[key]}" for key in previous if previous[key] != data[key]]
                selected = set(data["machines"].values_list("pk", flat=True))
                if selected != previous_machines:
                    changes.append(f"Máquinas (IDs): {sorted(previous_machines)} → {sorted(selected)}")
                ticket.machines.set(data["machines"])
                Event.objects.create(ticket=ticket, author=request.user,
                    text="Edição: " + ("; ".join(changes) or "sem alteração de conteúdo"))
        if changed:
            return redirect("ticket_detail", pk=pk)
        form.add_error(None, "O chamado mudou. Recarregue a página antes de salvar.")
    return render(request, "tickets/edit.html", {"form": form, "ticket": ticket})
