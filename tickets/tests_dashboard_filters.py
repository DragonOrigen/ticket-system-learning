from django.contrib.auth import get_user_model
from django.test import TestCase
from .models import Ticket


class DashboardFilterTests(TestCase):
    def test_filters_keep_counts_board_and_permissions_consistent(self):
        owner = get_user_model().objects.create_user('owner')
        other = get_user_model().objects.create_user('other')
        tickets = [Ticket.objects.create(requester=owner, category=value,
                   description=label) for value, label in Ticket.Category.choices]
        foreign = Ticket.objects.create(requester=other, description='Private', category='hardware')
        self.client.force_login(owner)
        expected = {'all': tickets, 'support': tickets[:3], 'tasks': tickets[3:]}
        for area, selected in expected.items():
            with self.subTest(area=area):
                response = self.client.get('/dashboard/', {'area': area})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context['total'], len(selected))
                actual = [t.pk for column in response.context['kanban_columns'] for t in column['tickets']]
                self.assertCountEqual(actual, [t.pk for t in selected])
                self.assertContains(response, f'?area={area}" aria-current="page"')
                self.assertNotIn(foreign.pk, actual)
        owner.is_superuser = True
        owner.save()
        response = self.client.get('/dashboard/', {'area': 'support'})
        self.assertEqual(response.context['total'], 4)
        self.assertIn(foreign, response.context['priority'])

    def test_default_invalid_and_empty_filters(self):
        user = get_user_model().objects.create_user('empty')
        self.client.force_login(user)
        for params in ({}, {'area': 'invalid'}, {'area': 'tasks'}):
            response = self.client.get('/dashboard/', params)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'Nenhum ticket nesta coluna.', count=3)
            self.assertEqual(response.context['selected_area'], 'tasks' if params.get('area') == 'tasks' else 'all')
