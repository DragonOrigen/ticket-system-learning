"""Importação explícita: primeiro valide com --simular, depois grave."""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from tickets.import_spreadsheet import read_plan, normalized
from tickets.models import SpreadsheetImport, Ticket


class Command(BaseCommand):
    help = "Importa o XLSX legado sem duplicar referências da mesma origem."

    def add_arguments(self, parser):
        parser.add_argument("arquivo")
        parser.add_argument("--mapa", required=True, help="JSON que relaciona nomes a usuários e máquinas existentes")
        parser.add_argument("--origem", default="planilha-tickets", help="Identificador estável; mantenha nas reimportações")
        parser.add_argument("--aba", default="Sistema de Tickets")
        parser.add_argument("--simular", action="store_true")

    def handle(self, *args, **options):
        source = options["origem"].strip()
        if not source or len(source) > 100:
            raise CommandError("Origem deve ter entre 1 e 100 caracteres.")
        try:
            mapping = json.loads(Path(options["mapa"]).read_text(encoding="utf-8-sig"))
            if not isinstance(mapping, dict):
                raise ValueError("mapa deve ser um objeto JSON")
            for key in ("usuarios", "maquinas"):
                part = mapping.get(key, {})
                if not isinstance(part, dict) or any(not isinstance(v, str) for v in part.values()):
                    raise ValueError(f"{key} deve relacionar nomes a textos")
            records, empty, duplicates, errors = read_plan(
                options["arquivo"], options["aba"], source, mapping.get("usuarios", {}), mapping.get("maquinas", {}))
        except Exception as error:
            raise CommandError(f"Não foi possível ler a importação: {error}") from error
        self.stdout.write(f"Novos: {len(records)} | Sem descrição: {empty} | Já importados: {duplicates} | Erros: {len(errors)}")
        for error in errors:
            self.stderr.write(error)
        if errors:
            raise CommandError("Nenhum dado gravado. Corrija as linhas indicadas e execute novamente.")
        if options["simular"]:
            for record in records:
                self.stdout.write(f"{record['original_id']}: {len(record['machine_ids'])} máquina(s)")
            self.stdout.write("Simulação concluída. Nenhum dado gravado.")
            return
        try:
            with transaction.atomic():
                for record in records:
                    ticket = Ticket.objects.create(
                        requester_id=record["requester_id"], description=record["description"],
                        all_machines=normalized(record["original_equipment"]) == "todas",
                        status=record["status"], urgency=record["urgency"], category=Ticket.Category.SUPPORT)
                    # auto_now_add usaria hoje; preservamos a abertura original explicitamente.
                    Ticket.objects.filter(pk=ticket.pk).update(created_at=record["created_at"])
                    ticket.machines.set(record["machine_ids"])
                    SpreadsheetImport.objects.create(
                        ticket=ticket, source=source, original_id=record["original_id"],
                        original_requester=record["original_requester"], original_equipment=record["original_equipment"],
                        notes=record["notes"], replies=record["replies"])
        except IntegrityError as error:
            raise CommandError("Importação cancelada por conflito no banco; nada foi gravado. Execute novamente para revalidar.") from error
        self.stdout.write(self.style.SUCCESS(f"Importados: {len(records)}. IDs novos do sistema; referências antigas preservadas."))
