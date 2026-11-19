from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.admin.models import LogEntry, DELETION
from django.test import TestCase, Client
from .models import Ticket, Machine, Message, Event, SpreadsheetImport


class TicketDeleteTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user('owner')
        self.admin = User.objects.create_superuser('admin', password='example-test-only')
        self.ticket = Ticket.objects.create(requester=self.owner, description='Teste de exclusão')
        self.url = f'/tickets/{self.ticket.pk}/excluir/'

    def test_only_superuser_can_delete(self):
        self.assertEqual(self.client.post(self.url).status_code, 302)
        for role in ('owner', 'staff', 'technician'):
            self.owner.is_staff = role == 'staff'
            self.owner.save()
            if role == 'technician':
                self.owner.groups.add(Group.objects.create(name='Tecnicos'))
            self.client.force_login(self.owner)
            self.assertEqual(self.client.get(self.url).status_code, 403)
            self.assertEqual(self.client.post(self.url, {'confirm_code': self.ticket.code}).status_code, 403)
        self.assertTrue(Ticket.objects.filter(pk=self.ticket.pk).exists())

    def test_confirmation_and_csrf_required(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(self.url), 'Você poderá restaurar este ticket.')
        self.assertTrue(Ticket.objects.filter(pk=self.ticket.pk).exists())
        self.assertEqual(self.client.post(self.url, {'confirm_code': 'wrong'}).status_code, 400)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.admin)
        self.assertEqual(csrf_client.post(self.url, {'confirm_code': self.ticket.code}).status_code, 403)
        self.assertTrue(Ticket.objects.filter(pk=self.ticket.pk).exists())

    def test_delete_imported_ticket_preserves_machines_users_and_audit(self):
        machine = Machine.objects.create(name='PC')
        self.ticket.machines.add(machine)
        Message.objects.create(ticket=self.ticket, author=self.owner, text='Mensagem')
        Event.objects.create(ticket=self.ticket, author=self.owner, text='Evento')
        SpreadsheetImport.objects.create(ticket=self.ticket, source='sheet', original_id='1')
        self.client.force_login(self.admin)
        pk = self.ticket.pk
        self.assertEqual(self.client.post(self.url, {'confirm_code': self.ticket.code}).status_code, 302)
        self.ticket.refresh_from_db()
        self.assertIsNotNone(self.ticket.deleted_at)
        self.assertEqual(self.client.post(f'/lixeira/{pk}/apagar/', {'confirm_code': self.ticket.code}).status_code, 302)
        self.assertFalse(Ticket.objects.filter(pk=pk).exists())
        self.assertFalse(Message.objects.exists())
        self.assertFalse(Event.objects.exists())
        self.assertFalse(SpreadsheetImport.objects.exists())
        self.assertTrue(Machine.objects.filter(pk=machine.pk).exists())
        self.assertTrue(get_user_model().objects.filter(pk=self.owner.pk).exists())
        self.assertTrue(LogEntry.objects.filter(user=self.admin, object_id=str(pk), action_flag=DELETION).exists())
        self.assertEqual(self.client.post(self.url, {'confirm_code': self.ticket.code}).status_code, 404)
