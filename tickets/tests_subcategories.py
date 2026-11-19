from django.contrib.auth import get_user_model
from django.test import TestCase
from .models import Ticket


class SubcategoryTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('owner')
        self.other = get_user_model().objects.create_user('other')
        self.client.force_login(self.user)

    def payload(self, **changes):
        data = {'category': 'suporte', 'subcategory': 'fones',
                'description': 'Sem áudio', 'urgency': 'media', 'mode': 'nenhuma'}
        data.update(changes)
        return data

    def test_create_edit_and_history(self):
        response = self.client.post('/tickets/novo/', self.payload())
        self.assertEqual(response.status_code, 302)
        ticket = Ticket.objects.get()
        self.assertEqual(ticket.subcategory, 'fones')
        response = self.client.post(f'/tickets/{ticket.pk}/editar/',
                                   self.payload(subcategory='teclados', version=ticket.version))
        self.assertEqual(response.status_code, 302)
        ticket.refresh_from_db()
        self.assertEqual(ticket.subcategory, 'teclados')
        self.assertTrue(ticket.events.filter(text__contains='subcategory: fones → teclados').exists())
        self.assertContains(self.client.get(f'/tickets/{ticket.pk}/'), 'Subcategoria: Teclados')
        self.assertContains(self.client.get('/dashboard/'), '<dt>Subcategoria</dt><dd>Teclados</dd>', html=True)

    def test_optional_and_invalid_subcategory(self):
        self.assertEqual(self.client.post('/tickets/novo/', self.payload(subcategory='')).status_code, 302)
        self.assertEqual(Ticket.objects.get().subcategory, '')
        response = self.client.post('/tickets/novo/', self.payload(subcategory='invalid'))
        self.assertIn('subcategory', response.context['form'].errors)
        self.assertEqual(Ticket.objects.count(), 1)

    def test_filter_permissions_areas_and_pagination(self):
        for i in range(26):
            Ticket.objects.create(requester=self.user, description=f'Fone {i}', subcategory='fones')
        Ticket.objects.create(requester=self.other, description='Privado', subcategory='fones')
        Ticket.objects.create(requester=self.user, description='Tarefa', category='manutencao', subcategory='fones')
        Ticket.objects.create(requester=self.user, description='Sem classificação')
        Ticket.objects.create(requester=self.user, description='Teclado', subcategory='teclados')
        response = self.client.get('/suporte/', {'subcategory': 'fones', 'status': 'novo'})
        self.assertEqual(response.context['page'].paginator.count, 26)
        self.assertContains(response, 'subcategory=fones&amp;sort=newest&amp;page=2')
        self.assertNotContains(response, 'Privado')
        self.assertNotContains(response, '>Tarefa<')
        self.assertEqual(len(self.client.get('/suporte/', {'subcategory': 'fones', 'page': 2}).context['page'].object_list), 1)
        self.assertEqual(self.client.get('/tarefas/', {'subcategory': 'fones'}).context['page'].paginator.count, 1)
        self.assertEqual(self.client.get('/', {'subcategory': 'none'}).context['page'].paginator.count, 1)
        self.assertEqual(self.client.get('/', {'subcategory': 'teclados', 'urgency': 'alta'}).context['page'].paginator.count, 0)

    def test_edit_protects_other_users_and_stale_versions(self):
        ticket = Ticket.objects.create(requester=self.other, description='Privado', subcategory='hub')
        self.assertEqual(self.client.post(f'/tickets/{ticket.pk}/editar/', self.payload(version=ticket.version)).status_code, 404)
        ticket.requester = self.user
        ticket.save()
        response = self.client.post(f'/tickets/{ticket.pk}/editar/', self.payload(version=ticket.version - 1))
        self.assertContains(response, 'O chamado mudou.')
        ticket.refresh_from_db()
        self.assertEqual(ticket.subcategory, 'hub')
