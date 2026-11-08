from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import identify_hasher
from django.contrib.auth.models import Group
from django.test import TestCase, Client
from django.urls import reverse
from .models import Machine, Ticket, Event


class TicketTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user("felipe", password="Example!LongPassword23")
        cls.other = User.objects.create_user("outro", password="Example!LongPassword23")
        cls.tech = User.objects.create_user("tecnico", password="Example!LongPassword23")
        cls.tech.groups.add(Group.objects.create(name="Tecnicos"))
        cls.machine1 = Machine.objects.create(name="Máquina 01")
        cls.machine2 = Machine.objects.create(name="Máquina 02")
        cls.ticket = Ticket.objects.create(description="Falha na máquina", requester=cls.user)
        cls.foreign = Ticket.objects.create(description="Chamado privado", requester=cls.other)

    def setUp(self):
        self.client.force_login(self.user)

    def test_anonymous_requires_login(self):
        self.client.logout()
        for url in ("/", "/tickets/novo/", f"/tickets/{self.ticket.pk}/"):
            self.assertEqual(self.client.get(url).status_code, 302)

    def test_password_hash_and_independent_salts(self):
        self.assertNotEqual(self.user.password, "Example!LongPassword23")
        self.assertTrue(self.user.check_password("Example!LongPassword23"))
        self.assertEqual(identify_hasher(self.user.password).algorithm, "pbkdf2_sha256")
        self.assertNotEqual(self.user.password.split("$")[2], self.other.password.split("$")[2])

    def test_login_and_logout(self):
        self.client.logout()
        self.assertEqual(self.client.post("/login/", {"username": "felipe", "password": "wrong"}).status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        response = self.client.post("/login/", {"username": "felipe", "password": "Example!LongPassword23"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get("/logout/").status_code, 405)
        self.client.post("/logout/")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_inactive_user_cannot_login(self):
        self.user.is_active = False
        self.user.save()
        self.client.logout()
        self.assertFalse(self.client.login(username="felipe", password="Example!LongPassword23"))

    def test_no_public_registration(self):
        self.assertEqual(self.client.get("/cadastro/").status_code, 404)
        self.assertEqual(self.client.get("/register/").status_code, 404)
        self.assertEqual(self.client.get("/admin/auth/user/add/").status_code, 302)

    def test_visibility_and_direct_access(self):
        response = self.client.get("/")
        self.assertContains(response, "Falha na máquina")
        self.assertNotContains(response, "Chamado privado")
        self.assertEqual(self.client.get(f"/tickets/{self.foreign.pk}/").status_code, 404)
        self.assertEqual(self.client.post(f"/tickets/{self.foreign.pk}/", {"action": "message", "text": "inválida"}).status_code, 404)

    def test_multiple_machines_and_requester_cannot_be_forged(self):
        response = self.client.post("/tickets/novo/", {
            "description": "Nova falha", "category": "suporte", "urgency": "alta", "mode": "varias",
            "machines": [self.machine1.pk, self.machine2.pk], "requester": self.other.pk,
            "status": "fechado", "responsible": self.user.pk,
        })
        self.assertEqual(response.status_code, 302)
        ticket = Ticket.objects.latest("pk")
        self.assertEqual(ticket.requester, self.user)
        self.assertEqual(ticket.status, "novo")
        self.assertIsNone(ticket.responsible)
        self.assertEqual(ticket.machines.count(), 2)
        self.assertEqual(ticket.events.count(), 1)

    def test_multiple_selection_validation(self):
        response = self.client.post("/tickets/novo/", {
            "description": "Falha", "category": "suporte", "urgency": "alta", "mode": "varias", "machines": [self.machine1.pk],
        })
        self.assertContains(response, "Selecione pelo menos duas máquinas.")
        self.assertEqual(Ticket.objects.count(), 2)

    def test_all_and_none_modes(self):
        for mode, count in (("todas", 2), ("nenhuma", 0)):
            self.client.post("/tickets/novo/", {"description": mode, "category": "suporte", "urgency": "media", "mode": mode})
            self.assertEqual(Ticket.objects.latest("pk").machines.count(), count)

    def test_requester_cannot_update_attendance(self):
        response = self.client.post(f"/tickets/{self.ticket.pk}/", {
            "action": "attendance", "version": 1, "status": "fechado", "category": "suporte", "urgency": "alta",
        })
        self.assertEqual(response.status_code, 403)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, "novo")

    def test_message_author_and_html_escape(self):
        response = self.client.post(f"/tickets/{self.ticket.pk}/", {
            "action": "message", "text": "<script>alert(1)</script>", "author": self.other.pk,
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.ticket.messages.get().author, self.user)
        response = self.client.get(f"/tickets/{self.ticket.pk}/")
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertNotContains(response, "<script>alert(1)</script>")

    def test_technician_completion_reopen_and_conflict(self):
        self.client.force_login(self.tech)
        url = f"/tickets/{self.ticket.pk}/"
        payload = {"action": "attendance", "version": 1, "status": "resolvido", "category": "suporte", "urgency": "alta", "responsible": self.tech.pk}
        self.assertEqual(self.client.post(url, payload).status_code, 302)
        self.ticket.refresh_from_db()
        self.assertIsNotNone(self.ticket.completed_at)
        self.assertEqual(self.ticket.responsible, self.tech)
        self.assertEqual(Event.objects.count(), 1)
        self.assertContains(self.client.post(url, payload), "Outro usuário atualizou")
        self.assertEqual(Event.objects.count(), 1)
        payload.update(version=2, status="andamento")
        self.assertEqual(self.client.post(url, payload).status_code, 302)
        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.completed_at)
        self.assertContains(self.client.get("/"), "Chamado privado")

    def test_assignment_only_to_technicians(self):
        self.client.force_login(self.tech)
        response = self.client.post(f"/tickets/{self.ticket.pk}/", {
            "action": "attendance", "version": 1, "status": "andamento", "category": "suporte", "urgency": "alta", "responsible": self.other.pk,
        })
        self.assertEqual(response.status_code, 200)
        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.responsible)

    def test_csrf_and_unsafe_redirect(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post("/login/", {"username": "felipe"}).status_code, 403)
        self.client.logout()
        response = self.client.post("/login/", {
            "username": "felipe", "password": "Example!LongPassword23", "next": "https://example.org/",
        })
        self.assertEqual(response.url, "/")

    def test_pages_render_and_filters(self):
        for path in ("/", "/login/", "/senha/", "/tickets/novo/", f"/tickets/{self.ticket.pk}/"):
            self.assertIn(self.client.get(path).status_code, (200, 302))
        self.assertContains(self.client.get("/?q=Falha&status=novo&urgency=media"), "Falha na máquina")
        self.assertNotContains(self.client.get("/?q=inexistente"), "Falha na máquina")


class AreaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_user("cliente")
        cls.other = get_user_model().objects.create_user("vizinho")
        cls.tech = get_user_model().objects.create_user("atendente")
        cls.tech.groups.add(Group.objects.create(name="Tecnicos"))
        cls.support = Ticket.objects.create(requester=cls.owner, description="Erro no aplicativo", category="falha_software")
        cls.task = Ticket.objects.create(requester=cls.owner, description="Instalar aplicativo", category="software")
        cls.private = Ticket.objects.create(requester=cls.other, description="Pedido privado")
        cls.machine = Machine.objects.create(name="Equipamento teste")

    def setUp(self):
        self.client.force_login(self.owner)

    def payload(self, **changes):
        data = {"description": "Descrição corrigida", "category": "hardware", "urgency": "alta",
                "mode": "uma", "machines": [self.machine.pk], "version": 1}
        data.update(changes)
        return data

    def test_area_partition_and_privacy(self):
        support = self.client.get("/suporte/")
        tasks = self.client.get("/tarefas/")
        self.assertContains(support, self.support.description)
        self.assertNotContains(support, self.task.description)
        self.assertContains(tasks, self.task.description)
        self.assertNotContains(tasks, self.support.description)
        self.assertNotContains(support, self.private.description)

    def test_dashboard_customer_scope(self):
        response = self.client.get("/dashboard/")
        self.assertEqual(response.context["total"], 2)
        self.assertNotIn("priority", response.context)
        self.assertNotContains(response, "Casos fora do padrão")

    def test_technician_dashboard_rules(self):
        from datetime import timedelta
        from django.utils import timezone
        Ticket.objects.filter(pk=self.support.pk).update(urgency="critica",
            created_at=timezone.now()-timedelta(days=8), updated_at=timezone.now()-timedelta(days=4))
        Ticket.objects.filter(pk=self.task.pk).update(status="fechado", urgency="critica")
        self.client.force_login(self.tech)
        response = self.client.get("/dashboard/")
        self.assertEqual(response.context["total"], 3)
        self.assertEqual(response.context["priority"][0].pk, self.support.pk)
        self.assertEqual(len(response.context["alerts"]), 1)
        self.assertEqual(len(response.context["alerts"][0]["reasons"]), 3)
        self.assertNotIn(self.task, response.context["priority"])

    def test_owner_edit_and_protected_fields(self):
        response = self.client.post(f"/tickets/{self.support.pk}/editar/", self.payload(
            requester=self.other.pk, status="fechado", responsible=self.owner.pk))
        self.assertEqual(response.status_code, 302)
        self.support.refresh_from_db()
        self.assertEqual(self.support.description, "Descrição corrigida")
        self.assertEqual(self.support.requester, self.owner)
        self.assertEqual(self.support.status, "novo")
        self.assertIsNone(self.support.responsible)
        self.assertEqual(self.support.machines.get(), self.machine)
        self.assertEqual(self.support.events.count(), 1)
        self.assertEqual(self.support.version, 2)

    def test_foreign_edit_blocked_and_technician_allowed(self):
        url = f"/tickets/{self.private.pk}/editar/"
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, self.payload()).status_code, 404)
        self.client.force_login(self.tech)
        self.assertEqual(self.client.post(url, self.payload()).status_code, 302)

    def test_stale_edit_preserves_content_and_machines(self):
        Ticket.objects.filter(pk=self.support.pk).update(version=2)
        response = self.client.post(f"/tickets/{self.support.pk}/editar/", self.payload())
        self.assertContains(response, "O chamado mudou")
        self.support.refresh_from_db()
        self.assertEqual(self.support.description, "Erro no aplicativo")
        self.assertFalse(self.support.machines.exists())
        self.assertFalse(self.support.events.exists())

    def test_help_and_new_pages_require_login(self):
        paths = ("/ajuda/", "/dashboard/", "/suporte/", "/tarefas/", f"/tickets/{self.support.pk}/editar/")
        for path in paths:
            self.assertEqual(self.client.get(path).status_code, 200)
        self.client.logout()
        for path in paths:
            self.assertEqual(self.client.get(path).status_code, 302)


class SpreadsheetTests(TestCase):
    def setUp(self):
        import tempfile
        import json
        from pathlib import Path
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.mapping = Path(self.directory.name) / "mapa.json"
        self.mapping.write_text(json.dumps({"usuarios": {"Alex": "alex"}}))
        self.user = get_user_model().objects.create_user("alex")
        self.active = Machine.objects.create(name="Máquina 01")
        self.inactive = Machine.objects.create(name="Máquina 02", active=False)

    def row(self, **changes):
        from datetime import datetime
        data = dict(id="TKT-001", description="Limpeza semanal", urgency="Baixa", status="Resolvido",
                    requester="Alex", date=datetime(2026, 10, 26), equipment="Todas", notes="Nota antiga", replies="Obrigado")
        data.update(changes)
        return tuple(data.values())

    def run_import(self, rows, simulate=False):
        from unittest.mock import MagicMock, patch
        from io import StringIO
        from django.core.management import call_command
        from .import_spreadsheet import HEADERS
        workbook = MagicMock()
        workbook.sheetnames = ["Sistema de Tickets"]
        workbook.__getitem__.return_value.iter_rows.return_value = iter([HEADERS, *rows])
        output = StringIO()
        with patch("tickets.import_spreadsheet.load_workbook", return_value=workbook):
            call_command("importar_tickets", "example.xlsx", mapa=str(self.mapping), simular=simulate, stdout=output, stderr=output)
        return output.getvalue()

    def test_all_includes_inactive_preserves_history_and_date(self):
        from django.utils import timezone
        self.run_import([self.row()])
        ticket = Ticket.objects.get()
        self.assertEqual(set(ticket.machines.all()), {self.active, self.inactive})
        self.assertEqual(str(timezone.localdate(ticket.created_at)), "2026-10-26")
        self.assertEqual(ticket.status, "resolvido")
        self.assertIsNone(ticket.completed_at)
        self.assertEqual(ticket.spreadsheet_import.notes, "Nota antiga")
        self.assertEqual(ticket.spreadsheet_import.replies, "Obrigado")
        self.assertFalse(ticket.messages.exists())
        self.assertFalse(hasattr(ticket, "weekly_schedule"))
        self.client.force_login(self.user)
        self.assertContains(self.client.get(f"/tickets/{ticket.pk}/"), "Nota antiga")

    def test_simulation_writes_nothing(self):
        self.assertIn("Simulação concluída", self.run_import([self.row()], simulate=True))
        self.assertEqual(Ticket.objects.count(), 0)

    def test_repeat_import_does_not_duplicate_or_overwrite(self):
        self.run_import([self.row()])
        output = self.run_import([self.row(description="Alteração externa")])
        self.assertIn("Já importados: 1", output)
        self.assertEqual(Ticket.objects.count(), 1)
        self.assertEqual(Ticket.objects.get().description, "Limpeza semanal")

    def test_invalid_row_prevents_whole_import(self):
        from django.core.management.base import CommandError
        for changes in ({"requester": "Desconhecido"}, {"equipment": "Máquina inexistente"},
                        {"date": "inválida"}, {"status": "X"}):
            with self.assertRaises(CommandError):
                self.run_import([self.row(), self.row(id="TKT-002", **changes)])
            self.assertEqual(Ticket.objects.count(), 0)

    def test_duplicate_ids_in_file_rejected(self):
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            self.run_import([self.row(), self.row()])
        self.assertEqual(Ticket.objects.count(), 0)

    def test_blank_rows_and_specific_equipment(self):
        self.run_import([self.row(description=""), self.row(id="TKT-002", equipment="Máquina 01"),
                         self.row(id="TKT-003", equipment="")])
        self.assertEqual(Ticket.objects.count(), 2)
        self.assertEqual(Ticket.objects.get(spreadsheet_import__original_id="TKT-002").machines.get(), self.active)
        self.assertFalse(Ticket.objects.get(spreadsheet_import__original_id="TKT-003").machines.exists())

    def test_all_on_creation_form_includes_inactive(self):
        self.client.force_login(self.user)
        response = self.client.post("/tickets/novo/", {"description": "Todos", "category": "suporte",
            "urgency": "media", "mode": "todas"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Ticket.objects.get().machines.count(), 2)

    def test_database_failure_rolls_back_all_rows(self):
        from unittest.mock import patch
        from django.db import IntegrityError
        from django.core.management.base import CommandError
        with patch("tickets.management.commands.importar_tickets.SpreadsheetImport.objects.create", side_effect=IntegrityError):
            with self.assertRaises(CommandError):
                self.run_import([self.row()])
        self.assertEqual(Ticket.objects.count(), 0)


class ManualTasksTests(TestCase):
    def test_weekly_ui_and_command_removed(self):
        from django.core.management import get_commands
        from .forms import TicketForm
        self.assertNotIn("repeat_weekly", TicketForm().fields)
        self.assertNotIn("processar_recorrencias", get_commands())

    def test_old_weekly_parameter_creates_only_manual_ticket(self):
        user = get_user_model().objects.create_user("manual")
        self.client.force_login(user)
        response = self.client.post("/tickets/novo/", {"description": "Manutenção", "category": "manutencao",
            "urgency": "baixa", "mode": "nenhuma", "repeat_weekly": "on"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Ticket.objects.count(), 1)
        self.assertNotContains(self.client.get(response.url), "Próxima ocorrência")
