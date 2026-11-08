"""Leitura e validação sem gravar no banco. A gravação fica no comando."""
from datetime import date, datetime, time
import re
import unicodedata

from django.contrib.auth import get_user_model
from django.utils import timezone
from openpyxl import load_workbook

from .models import Machine, SpreadsheetImport, Ticket

HEADERS = (
    "ID do Ticket", "Descrição do Problema / Solicitação", "Nível de Urgência",
    "Status", "Solicitante (Quem Abriu)", "Data de Abertura", "PC com Problema",
    "Observações", "Resposta as observações",
)


def text(value):
    return "" if value is None else str(value).strip()


def normalized(value):
    value = unicodedata.normalize("NFKD", text(value).casefold())
    return " ".join("".join(c for c in value if not unicodedata.combining(c)).split())


def choices_map(choices):
    return {normalized(label): value for value, label in choices}


def parse_date(value):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.min)
    else:
        parsed = None
        for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(text(value), fmt)
                break
            except ValueError:
                continue
        if parsed is None:
            raise ValueError("data de abertura ausente ou inválida")
    return timezone.make_aware(parsed) if timezone.is_naive(parsed) else parsed


def read_plan(path, sheet, source, user_map, machine_map):
    """Retorna registros novos, contadores e todos os erros encontrados."""
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        if sheet not in workbook.sheetnames:
            raise ValueError(f"aba não encontrada: {sheet}")
        rows = workbook[sheet].iter_rows(values_only=True)
        header = list(next(rows, ()))
        positions = {normalized(value): i for i, value in enumerate(header) if value}
        missing = [name for name in HEADERS if normalized(name) not in positions]
        if missing:
            raise ValueError("colunas ausentes: " + ", ".join(missing))
        existing = set(SpreadsheetImport.objects.filter(source=source).values_list("original_id", flat=True))
        machines = list(Machine.objects.all())  # Todas inclui também as desativadas.
        machine_lookup = {normalized(m.name): m.pk for m in machines}
        users = {u.username: u.pk for u in get_user_model().objects.all()}
        user_map = {normalized(k): v for k, v in user_map.items()}
        machine_map = {normalized(k): v for k, v in machine_map.items()}
        statuses, urgencies = choices_map(Ticket.Status.choices), choices_map(Ticket.Urgency.choices)
        records, errors, seen = [], [], set()
        empty = duplicates = 0
        for number, row in enumerate(rows, 2):
            values = [row[positions[normalized(h)]] if positions[normalized(h)] < len(row) else None for h in HEADERS]
            old_id, description, urgency, status, requester, opened, equipment, notes, replies = values
            if not text(description):
                if any(text(value) for value in values):
                    empty += 1
                continue
            old_id = text(old_id).upper()
            try:
                if not re.fullmatch(r"TKT-\d+", old_id) or len(old_id) > 100:
                    raise ValueError("ID deve seguir TKT-001")
                if old_id in seen:
                    raise ValueError(f"ID repetido na própria planilha: {old_id}")
                seen.add(old_id)
                if old_id in existing:
                    duplicates += 1
                    continue
                username = user_map.get(normalized(requester))
                if username not in users:
                    raise ValueError(f"mapeie o solicitante {text(requester)!r} para uma conta existente")
                if normalized(status) not in statuses or normalized(urgency) not in urgencies:
                    raise ValueError("status ou urgência desconhecidos")
                if len(text(description)) > 10000 or len(text(requester)) > 150:
                    raise ValueError("descrição ou solicitante excede o limite")
                selected = []
                if normalized(equipment) == "todas":
                    selected = [m.pk for m in machines]
                    if not selected:
                        raise ValueError("Todas exige máquinas cadastradas")
                elif normalized(equipment) not in ("", "nenhuma", "sem equipamento"):
                    for name in re.split(r"[;,\n]+", text(equipment)):
                        target = machine_map.get(normalized(name), name)
                        machine_id = machine_lookup.get(normalized(target))
                        if machine_id is None:
                            raise ValueError(f"máquina não cadastrada ou sem mapeamento: {name!r}")
                        selected.append(machine_id)
                records.append(dict(
                    original_id=old_id, description=text(description), requester_id=users[username],
                    original_requester=text(requester), created_at=parse_date(opened),
                    status=statuses[normalized(status)], urgency=urgencies[normalized(urgency)],
                    machine_ids=sorted(set(selected)), original_equipment=text(equipment),
                    notes=text(notes), replies=text(replies),
                ))
            except ValueError as error:
                errors.append(f"Linha {number}: {error}")
        return records, empty, duplicates, errors
    finally:
        workbook.close()
