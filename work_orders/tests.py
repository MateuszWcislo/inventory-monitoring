from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from tenants.models import Tenant
from work_orders.models import WorkOrder, WorkOrderProduct, WorkOrderService
from inventory.models import Product, ProductBatch
from services.models import Service
from decimal import Decimal

User = get_user_model()


class WorkOrderCrossTenantTests(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(name="Tenant A", subdomain="tenant-a-wo")
        self.tenant_b = Tenant.objects.create(name="Tenant B", subdomain="tenant-b-wo")

        self.user_a = User.objects.create_user(username="user_a", email="user_a_wo@test.com", password="password_a", tenant=self.tenant_a)
        self.user_b = User.objects.create_user(username="user_b", email="user_b_wo@test.com", password="password_b", tenant=self.tenant_b)

        self.client_a = Client()
        self.client_a.login(username="user_a", password="password_a")

        self.order_a = WorkOrder.objects.create(tenant=self.tenant_a, name="Zlecenie A", client="Klient A")
        self.order_b = WorkOrder.objects.create(tenant=self.tenant_b, name="Zlecenie B", client="Klient B")

        self.prod_b = Product.objects.create(tenant=self.tenant_b, name="Produkt B")
        self.batch_b = ProductBatch.objects.create(tenant=self.tenant_b, product=self.prod_b, current_stock=10, net_price=Decimal("10.00"))

        self.service_b = Service.objects.create(tenant=self.tenant_b, name="Usługa B", net_price=Decimal("50.00"))

    def test_work_order_detail_cross_tenant_denied(self):
        # User A próbuje wejść w szczegóły zlecenia Tenanta B -> 404
        response = self.client_a.get(reverse('work_order_detail', kwargs={'pk': self.order_b.pk}))
        self.assertEqual(response.status_code, 404)

    def test_add_product_item_cross_tenant_denied(self):
        # User A próbuje dodać partię Tenanta B do swojego zlecenia -> 404
        response = self.client_a.post(
            reverse('add_product_item', kwargs={'pk': self.order_a.pk}),
            {'batch_id': self.batch_b.id, 'quantity': 1}
        )
        self.assertEqual(response.status_code, 404)

    def test_add_service_item_cross_tenant_denied(self):
        # User A próbuje dodać usługę Tenanta B do swojego zlecenia -> 404
        response = self.client_a.post(
            reverse('add_service_item', kwargs={'pk': self.order_a.pk}),
            {'service_id': self.service_b.id, 'quantity': 1}
        )
        self.assertEqual(response.status_code, 404)
