from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from tenants.models import Tenant
from services.models import Service

User = get_user_model()


class ServiceCrossTenantTests(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(name="Tenant A", subdomain="tenant-a-serv")
        self.tenant_b = Tenant.objects.create(name="Tenant B", subdomain="tenant-b-serv")

        self.user_a = User.objects.create_user(username="user_a", email="user_a_serv@test.com", password="password_a", tenant=self.tenant_a)
        self.user_b = User.objects.create_user(username="user_b", email="user_b_serv@test.com", password="password_b", tenant=self.tenant_b)

        self.client_a = Client()
        self.client_a.login(username="user_a", password="password_a")

        self.service_a = Service.objects.create(name="Usługa A", tenant=self.tenant_a, net_price="100.00")
        self.service_b = Service.objects.create(name="Usługa B", tenant=self.tenant_b, net_price="200.00")

    def test_service_edit_cross_tenant_denied(self):
        response = self.client_a.get(reverse('service_edit', kwargs={'pk': self.service_b.pk}))
        self.assertEqual(response.status_code, 404)

        response_post = self.client_a.post(
            reverse('service_edit', kwargs={'pk': self.service_b.pk}),
            {'name': 'Zmieniona usługa'}
        )
        self.assertEqual(response_post.status_code, 404)

    def test_service_delete_cross_tenant_denied(self):
        response = self.client_a.post(reverse('service_delete', kwargs={'pk': self.service_b.pk}))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Service.objects.filter(pk=self.service_b.pk).exists())
