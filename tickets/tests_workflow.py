from datetime import timedelta
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client
from django.utils import timezone
from .models import Ticket, Attachment, Notification, Message
from .forms import AttachmentForm
from .extras import save_attachment


class WorkflowTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user('owner')
        self.other = User.objects.create_user('other')
        self.tech = User.objects.create_user('tech')
        self.tech.groups.add(Group.objects.create(name='Tecnicos'))
        self.admin = User.objects.create_superuser('admin')
        self.ticket = Ticket.objects.create(requester=self.owner, description='Chamado', responsible=self.tech)
        self.client.force_login(self.owner)

    def upload(self):
        return SimpleUploadedFile('teste.pdf', b'%PDF-1.7\nexample', content_type='application/pdf')

    def test_attachment_upload_private_download_and_validation(self):
        url = f'/tickets/{self.ticket.pk}/'
        response = self.client.post(url, {'action': 'attachment', 'file': self.upload()})
        self.assertEqual(response.status_code, 302)
        attachment = Attachment.objects.get()
        response = self.client.get(f'/anexos/{attachment.pk}/')
        self.assertEqual(response.content, b'%PDF-1.7\nexample')
        self.assertIn('attachment;', response['Content-Disposition'])
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(f'/anexos/{attachment.pk}/').status_code, 404)
        self.assertEqual(self.client.post(url, {'action': 'attachment', 'file': self.upload()}).status_code, 404)
        self.assertFalse(AttachmentForm(files={'file': SimpleUploadedFile('bad.png', b'<script>bad</script>')}).is_valid())
        self.assertFalse(AttachmentForm(files={'file': SimpleUploadedFile('big.pdf', b'%PDF-' + b'x' * (5 * 1024 * 1024))}).is_valid())

    def test_attachment_limit(self):
        for i in range(10):
            self.assertTrue(save_attachment(self.ticket, self.owner, self.upload()))
        self.assertFalse(save_attachment(self.ticket, self.owner, self.upload()))
        self.assertEqual(self.ticket.attachments.count(), 10)

    def test_trash_restore_preserves_history_and_hides_everywhere(self):
        save_attachment(self.ticket, self.owner, self.upload())
        Message.objects.create(ticket=self.ticket, author=self.owner, text='Preservar')
        self.client.force_login(self.admin)
        self.client.post(f'/tickets/{self.ticket.pk}/excluir/', {'confirm_code': self.ticket.code})
        self.assertEqual(self.client.get('/dashboard/').context['total'], 0)
        self.assertEqual(self.client.get('/relatorios/').context['total'], 0)
        self.assertEqual(self.client.get('/').context['page'].paginator.count, 0)
        self.assertEqual(self.client.get(f'/tickets/{self.ticket.pk}/').status_code, 404)
        self.assertEqual(self.client.get(f'/anexos/{Attachment.objects.get().pk}/').status_code, 404)
        self.assertEqual(self.client.get('/notificacoes/').context['unread'], 0)
        self.assertEqual(self.client.get(f'/lixeira/{self.ticket.pk}/restaurar/').status_code, 405)
        self.assertEqual(self.client.post(f'/lixeira/{self.ticket.pk}/restaurar/').status_code, 302)
        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.deleted_at)
        self.assertEqual(self.ticket.messages.count(), 1)
        self.assertEqual(self.ticket.attachments.count(), 1)
        self.assertEqual(self.client.get('/dashboard/').context['total'], 1)

    def test_trash_and_purge_permissions(self):
        for user in [self.owner, self.tech]:
            self.client.force_login(user)
            self.assertEqual(self.client.get('/lixeira/').status_code, 403)
            self.assertEqual(self.client.post(f'/lixeira/{self.ticket.pk}/restaurar/').status_code, 403)
            self.assertEqual(self.client.post(f'/lixeira/{self.ticket.pk}/apagar/', {'confirm_code': self.ticket.code}).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(f'/lixeira/{self.ticket.pk}/apagar/').status_code, 404)
        self.client.post(f'/tickets/{self.ticket.pk}/excluir/', {'confirm_code': self.ticket.code})
        self.assertEqual(self.client.post(f'/lixeira/{self.ticket.pk}/apagar/', {'confirm_code': 'wrong'}).status_code, 400)
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.admin)
        self.assertEqual(csrf.post(f'/lixeira/{self.ticket.pk}/restaurar/').status_code, 403)

    def test_due_date_and_overdue(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        self.client.force_login(self.tech)
        response = self.client.post(f'/tickets/{self.ticket.pk}/', {
            'action': 'attendance', 'version': self.ticket.version, 'status': 'andamento',
            'urgency': 'alta', 'responsible': self.tech.pk, 'due_date': yesterday.isoformat()})
        self.assertEqual(response.status_code, 302)
        self.ticket.refresh_from_db()
        self.assertTrue(self.ticket.overdue)
        self.assertContains(self.client.get('/'), 'Em atraso')
        self.ticket.status = 'resolvido'
        self.assertFalse(self.ticket.overdue)
        self.ticket.status = 'novo'
        self.ticket.due_date = timezone.localdate()
        self.assertFalse(self.ticket.overdue)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(f'/tickets/{self.ticket.pk}/', {'action': 'attendance'}).status_code, 403)

    def test_sorting_is_stable_and_filters_remain(self):
        critical = Ticket.objects.create(requester=self.owner, description='Urgente', urgency='critica',
            due_date=timezone.localdate())
        for sort, expected in [('id_asc', self.ticket.pk), ('id_desc', critical.pk), ('urgency', critical.pk), ('deadline', critical.pk)]:
            response = self.client.get('/', {'sort': sort})
            self.assertEqual(response.context['page'][0].pk, expected)
        self.assertEqual(self.client.get('/', {'sort': 'bad'}).context['selected_sort'], 'newest')
        for i in range(25):
            Ticket.objects.create(requester=self.owner, description='Paginado', subcategory='fones')
        response = self.client.get('/', {'sort': 'id_asc'})
        self.assertContains(response, 'sort=id_asc&amp;page=2')
        response = self.client.get('/', {'sort': 'id_desc', 'subcategory': 'fones'})
        self.assertEqual(response.context['page'].paginator.count, 25)

    def test_notifications_recipient_scope_and_mark_read(self):
        self.client.post(f'/tickets/{self.ticket.pk}/', {'action': 'message', 'text': 'Olá'})
        n = Notification.objects.get(recipient=self.tech)
        self.assertFalse(Notification.objects.filter(recipient=self.owner).exists())
        self.assertEqual(self.client.post('/notificacoes/', {'notification_id': n.pk}).status_code, 404)
        self.client.force_login(self.tech)
        self.assertEqual(self.client.get('/notificacoes/').context['unread'], 1)
        self.assertEqual(self.client.post('/notificacoes/', {'notification_id': n.pk}).status_code, 302)
        self.assertEqual(self.client.get('/notificacoes/').context['unread'], 0)
        self.assertEqual(self.client.post('/notificacoes/', {'notification_id': 'invalid'}).status_code, 400)

    def test_reports_dates_privacy_and_resolution_average(self):
        now = timezone.now()
        Ticket.objects.filter(pk=self.ticket.pk).update(created_at=now-timedelta(hours=4),
            completed_at=now, status='resolvido')
        Ticket.objects.create(requester=self.other, description='Privado')
        response = self.client.get('/relatorios/')
        self.assertEqual(response.context['total'], 1)
        self.assertAlmostEqual(response.context['average'], 4)
        self.assertEqual(response.context['sample'], 1)
        response = self.client.get('/relatorios/', {'start': '2099-01-01'})
        self.assertEqual(response.context['total'], 0)
        self.assertIsNone(response.context['average'])
        self.assertContains(self.client.get('/relatorios/', {'start':'2026-02-01','end':'2026-01-01'}), 'A data inicial')
