from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from tenants.models import Tenant
from suppliers.models import Supplier
from inventory.models import Product, ProductSupplier

User = get_user_model()


class SupplierCrossTenantTests(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(name="Tenant A", subdomain="tenant-a-supp")
        self.tenant_b = Tenant.objects.create(name="Tenant B", subdomain="tenant-b-supp")

        self.user_a = User.objects.create_user(username="user_a", email="user_a_supp@test.com", password="password_a", tenant=self.tenant_a)
        self.user_b = User.objects.create_user(username="user_b", email="user_b_supp@test.com", password="password_b", tenant=self.tenant_b)

        self.client_a = Client()
        self.client_a.login(username="user_a", password="password_a")

        self.client_b = Client()
        self.client_b.login(username="user_b", password="password_b")

        self.supp_a = Supplier.objects.create(name="Dostawca A", tenant=self.tenant_a)
        self.supp_b = Supplier.objects.create(name="Dostawca B", tenant=self.tenant_b)

        self.prod_a = Product.objects.create(name="Produkt A", tenant=self.tenant_a)
        self.prod_b = Product.objects.create(name="Produkt B", tenant=self.tenant_b)

    def test_supplier_edit_cross_tenant_denied(self):
        # Próba edycji dostawcy Tenanta B przez Usrera A -> 404
        response = self.client_a.get(reverse('supplier_edit', kwargs={'pk': self.supp_b.pk}))
        self.assertEqual(response.status_code, 404)

        response_post = self.client_a.post(
            reverse('supplier_edit', kwargs={'pk': self.supp_b.pk}),
            {'name': 'Zmieniona nazwa'}
        )
        self.assertEqual(response_post.status_code, 404)

    def test_supplier_delete_cross_tenant_denied(self):
        response = self.client_a.post(reverse('supplier_delete', kwargs={'pk': self.supp_b.pk}))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Supplier.objects.filter(pk=self.supp_b.pk).exists())

    def test_supplier_preview_cross_tenant_denied(self):
        response = self.client_a.get(reverse('supplier_preview', kwargs={'pk': self.supp_b.pk}))
        self.assertEqual(response.status_code, 404)

    def test_supplier_products_form_rendering(self):
        # Sprawdzenie obecności elementów zaznaczania wszystkich produktów w obu formularzach
        response_edit = self.client_a.get(reverse('supplier_edit', kwargs={'pk': self.supp_a.pk}))
        self.assertEqual(response_edit.status_code, 200)
        self.assertContains(response_edit, 'id="selectAllProducts"')

        response_products = self.client_a.get(reverse('supplier_edit_products', kwargs={'pk': self.supp_a.pk}))
        self.assertEqual(response_products.status_code, 200)
        self.assertContains(response_products, 'id="selectAllModalProducts"')
