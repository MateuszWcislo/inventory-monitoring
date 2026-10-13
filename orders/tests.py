from django.test import TestCase
from decimal import Decimal
from tenants.models import Tenant
from users.models import User
from inventory.models import Product, ProductBatch, ProductSupplier
from suppliers.models import Supplier
from orders.models import Order
from orders.utils import process_auto_order_logic
from orders.forms import OrderForm


class AutoOrderLogicTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Firma Testowa", subdomain="firma-testowa")
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="password123",
            tenant=self.tenant
        )
        self.supplier = Supplier.objects.create(
            name="Dostawca A",
            tenant=self.tenant,
            phone="123456789"
        )

    def test_auto_order_created_when_stock_below_minimum(self):
        # Produkt z progiem min 10 i docelowym 20
        product = Product.objects.create(
            tenant=self.tenant,
            name="Śruba M6",
            min_threshold=10,
            target_stock=20
        )
        ProductSupplier.objects.create(
            tenant=self.tenant,
            product=product,
            supplier=self.supplier,
            supplier_sku="SKU-SRUBA"
        )
        # Tworzymy partię z 5 sztukami (5 < 10)
        ProductBatch.objects.create(
            tenant=self.tenant,
            product=product,
            current_stock=5,
            net_price=Decimal("2.50")
        )

        auto_order = Order.objects.filter(
            product=product,
            order_type='AUTO',
            status='CREATED'
        ).first()

        self.assertIsNotNone(auto_order)
        # target_stock (20) - virtual_stock (5) = 15
        self.assertEqual(auto_order.quantity, 15)
        self.assertEqual(auto_order.supplier, self.supplier)
        self.assertEqual(auto_order.net_price, Decimal("2.50"))

    def test_auto_order_not_created_when_stock_at_or_above_minimum(self):
        product = Product.objects.create(
            tenant=self.tenant,
            name="Podkładka M6",
            min_threshold=5,
            target_stock=15
        )
        ProductBatch.objects.create(
            tenant=self.tenant,
            product=product,
            current_stock=10,
            net_price=Decimal("1.00")
        )

        auto_order = Order.objects.filter(product=product).first()
        self.assertIsNone(auto_order)

    def test_cancel_auto_order_does_not_resurrect_in_loop(self):
        product = Product.objects.create(
            tenant=self.tenant,
            name="Nakrętka M6",
            min_threshold=10,
            target_stock=20
        )
        # Stock is 0, auto order generated
        process_auto_order_logic(product)
        order = Order.objects.filter(product=product, order_type='AUTO').first()
        self.assertIsNotNone(order)
        self.assertEqual(order.status, 'CREATED')

        # Anulujemy zamówienie
        order.status = 'CANCELLED'
        order.save()

        # Upewniamy się, że nie powstało natychmiast drugie zamówienie w CREATED
        created_orders = Order.objects.filter(product=product, status='CREATED')
        self.assertEqual(created_orders.count(), 0)

    def test_order_save_does_not_override_needed_quantity_of_one(self):
        product = Product.objects.create(
            tenant=self.tenant,
            name="Klej",
            min_threshold=10,
            target_stock=10
        )
        # Stan 9, limit 10, target 10 -> needed_quantity = 1
        ProductBatch.objects.create(
            tenant=self.tenant,
            product=product,
            current_stock=9,
            net_price=Decimal("15.00")
        )

        auto_order = Order.objects.filter(product=product, order_type='AUTO').first()
        self.assertIsNotNone(auto_order)
        self.assertEqual(auto_order.quantity, 1)

    def test_order_form_unsaved_instance_is_not_treated_as_removed(self):
        form = OrderForm(user=self.user)
        # Form for new order should NOT disable fields as removed
        self.assertFalse(form.fields['quantity'].disabled)
        self.assertNotIn('(USUNIĘTY)', str(form.fields['product'].help_text))


class OrderCrossTenantIsolationTests(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(name="Tenant A", subdomain="tenant-a")
        self.tenant_b = Tenant.objects.create(name="Tenant B", subdomain="tenant-b")

        self.user_a = User.objects.create_user(
            username="user_a",
            email="user_a_ord@test.com",
            password="password_a",
            tenant=self.tenant_a
        )
        self.user_b = User.objects.create_user(
            username="user_b",
            email="user_b_ord@test.com",
            password="password_b",
            tenant=self.tenant_b
        )

        self.supp_a = Supplier.objects.create(name="Dostawca A", tenant=self.tenant_a)
        self.supp_b = Supplier.objects.create(name="Dostawca B", tenant=self.tenant_b)

        self.prod_a = Product.objects.create(name="Produkt A", tenant=self.tenant_a)
        self.prod_b = Product.objects.create(name="Produkt B", tenant=self.tenant_b)

        ProductSupplier.objects.create(tenant=self.tenant_a, product=self.prod_a, supplier=self.supp_a)
        ProductSupplier.objects.create(tenant=self.tenant_b, product=self.prod_b, supplier=self.supp_b)

        self.order_a = Order.objects.create(
            tenant=self.tenant_a,
            product=self.prod_a,
            supplier=self.supp_a,
            quantity=5,
            net_price=Decimal("10.00"),
            status='CREATED'
        )
        self.order_b = Order.objects.create(
            tenant=self.tenant_b,
            product=self.prod_b,
            supplier=self.supp_b,
            quantity=10,
            net_price=Decimal("20.00"),
            status='CREATED'
        )

    def test_order_edit_cross_tenant_denied(self):
        from django.test import Client
        from django.urls import reverse
        client = Client()
        client.login(username="user_a", password="password_a")

        # Próba edycji zamówienia tenanta B przez usera A -> 404
        response = client.get(reverse('order_edit', kwargs={'pk': self.order_b.pk}))
        self.assertEqual(response.status_code, 404)

        # Próba zmiany statusu
        response = client.post(reverse('order_status_update', kwargs={'pk': self.order_b.pk}), {'status': 'CANCELLED'})
        self.assertEqual(response.status_code, 404)

        # Próba usunięcia
        response = client.post(reverse('order_delete', kwargs={'pk': self.order_b.pk}))
        self.assertEqual(response.status_code, 404)

    def test_order_form_cross_tenant_validation(self):
        # Próba utworzenia formularza z produktem tenanta B przez usera A
        form_data = {
            'product': self.prod_b.id,
            'supplier': self.supp_a.id,
            'quantity': 10,
            'net_price': '15.00',
            'order_type': 'MANUAL',
            'status': 'CREATED'
        }
        form = OrderForm(data=form_data, user=self.user_a)
        self.assertFalse(form.is_valid())
        self.assertIn('product', form.errors)
