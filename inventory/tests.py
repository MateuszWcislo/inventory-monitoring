from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from decimal import Decimal
from tenants.models import Tenant
from inventory.models import Product, Location, ProductBatch, ProductSupplier, Stocktake, StocktakeItem, ActivityLog
from suppliers.models import Supplier

User = get_user_model()


class ProductSortingTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test Tenant", is_active=True)
        self.user = User.objects.create_user(
            username="testuser",
            password="testpassword",
            tenant=self.tenant
        )
        self.client = Client()
        self.client.login(username="testuser", password="testpassword")

        # Tworzymy produkty testowe
        self.prod_a = Product.objects.create(
            name="Produkt A",
            tenant=self.tenant,
            is_favourite=False
        )
        self.prod_b = Product.objects.create(
            name="Produkt B",
            tenant=self.tenant,
            is_favourite=True
        )
        self.prod_c = Product.objects.create(
            name="Produkt C",
            tenant=self.tenant,
            is_favourite=False
        )
        self.prod_d = Product.objects.create(
            name="Produkt D",
            tenant=self.tenant,
            is_favourite=True
        )

    def test_default_sorting_favourite_first_then_alphabetical(self):
        """
        Domyślne sortowanie powinno ustawiać ulubione na samej górze (alfabetycznie),
        a następnie pozostałe produkty alfabetycznie.
        Oczekiwana kolejność: Produkt B (fav), Produkt D (fav), Produkt A, Produkt C
        """
        response = self.client.get(reverse('product_list'))
        self.assertEqual(response.status_code, 200)

        products = list(response.context['products'])
        expected_order = [self.prod_b, self.prod_d, self.prod_a, self.prod_c]
        self.assertEqual(products, expected_order)

    def test_sorting_desc_keeps_favourite_on_top(self):
        """
        Przy sortowaniu malejącym po nazwie, ulubione pozostają na górze,
        ale wewnątrz grup są posortowane malejąco.
        Oczekiwana kolejność: Produkt D (fav), Produkt B (fav), Produkt C, Produkt A
        """
        response = self.client.get(reverse('product_list') + '?sort=name&direction=desc')
        self.assertEqual(response.status_code, 200)

        products = list(response.context['products'])
        expected_order = [self.prod_d, self.prod_b, self.prod_c, self.prod_a]
        self.assertEqual(products, expected_order)


class LocationAndMultiWarehouseTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Warehouse Tenant", is_active=True)
        self.user = User.objects.create_user(
            username="wh_user",
            password="password",
            tenant=self.tenant
        )
        self.client = Client()
        self.client.login(username="wh_user", password="password")

    def test_default_location_auto_creation(self):
        """Test automatycznego tworzenia i zwracania domyślnego magazynu."""
        loc = Location.get_default_location(self.tenant)
        self.assertIsNotNone(loc)
        self.assertTrue(loc.is_default)
        self.assertEqual(loc.name, "Główny")

    def test_location_crud(self):
        """Test dodawania, edycji i usuwania magazynu."""
        # 1. Tworzenie
        response = self.client.post(reverse('location_create'), {
            'name': 'Magazyn Południe',
            'code': 'MAG-S',
            'address': 'Kraków, ul. Przemysłowa 5',
            'is_default': False
        })
        self.assertEqual(response.status_code, 302)
        loc = Location.objects.get(name='Magazyn Południe', tenant=self.tenant)
        self.assertEqual(loc.code, 'MAG-S')

        # 2. Edycja
        response = self.client.post(reverse('location_edit', kwargs={'pk': loc.pk}), {
            'name': 'Magazyn Południe - Zaktualizowany',
            'code': 'MAG-S2',
            'address': 'Kraków, ul. Przemysłowa 10',
            'is_default': False
        })
        self.assertEqual(response.status_code, 302)
        loc.refresh_from_db()
        self.assertEqual(loc.name, 'Magazyn Południe - Zaktualizowany')

        # 3. Usuwanie
        response = self.client.post(reverse('location_delete', kwargs={'pk': loc.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Location.objects.filter(pk=loc.pk).exists())

    def test_product_batches_in_multiple_locations(self):
        """Test przypisywania partii do różnych lokalizacji i filtrowania na liście."""
        loc1 = Location.objects.create(tenant=self.tenant, name="Magazyn 1", is_default=True)
        loc2 = Location.objects.create(tenant=self.tenant, name="Magazyn 2", is_default=False)

        product = Product.objects.create(tenant=self.tenant, name="Towar Wielomagazynowy")
        ProductBatch.objects.create(
            tenant=self.tenant,
            product=product,
            location=loc1,
            current_stock=10,
            net_price=Decimal("100.00")
        )
        ProductBatch.objects.create(
            tenant=self.tenant,
            product=product,
            location=loc2,
            current_stock=25,
            net_price=Decimal("110.00")
        )

        # Pobranie bez filtra lokalizacji (suma ze wszystkich = 35)
        response = self.client.get(reverse('product_list'))
        self.assertEqual(response.status_code, 200)
        prod_item = list(response.context['products'])[0]
        self.assertEqual(prod_item.computed_total_stock, 35)

        # Pobranie z filtrem dla Magazynu 1 (stan = 10)
        response_loc1 = self.client.get(reverse('product_list') + f'?location={loc1.id}')
        self.assertEqual(response_loc1.status_code, 200)
        prod_item1 = list(response_loc1.context['products'])[0]
        self.assertEqual(prod_item1.computed_total_stock, 10)

        # Pobranie z filtrem dla Magazynu 2 (stan = 25)
        response_loc2 = self.client.get(reverse('product_list') + f'?location={loc2.id}')
        self.assertEqual(response_loc2.status_code, 200)
        prod_item2 = list(response_loc2.context['products'])[0]
        self.assertEqual(prod_item2.computed_total_stock, 25)


class StocktakeInventoryTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Stocktake Tenant", is_active=True)
        self.user = User.objects.create_user(
            username="stock_user",
            password="password",
            tenant=self.tenant
        )
        self.client = Client()
        self.client.login(username="stock_user", password="password")

        self.loc = Location.objects.create(tenant=self.tenant, name="Magazyn Centralny", is_default=True)
        self.prod1 = Product.objects.create(tenant=self.tenant, name="Kabel HDMI 2m")
        self.prod2 = Product.objects.create(tenant=self.tenant, name="Adapter USB-C")

        self.batch1 = ProductBatch.objects.create(
            tenant=self.tenant,
            product=self.prod1,
            location=self.loc,
            current_stock=50,
            net_price=Decimal("20.00")
        )

    def test_stocktake_creation_and_completion_adjusts_stock(self):
        """Test pełnego cyklu inwentaryzacji: utworzenie, zmiana stanów, zatwierdzenie i logi."""
        # 1. Tworzenie arkusza inwentaryzacji
        response = self.client.post(reverse('stocktake_create'), {
            'title': 'Inwentaryzacja Roczna 2026',
            'location': str(self.loc.id),
            'notes': 'Spis z natury magazynu centralnego'
        })
        self.assertEqual(response.status_code, 302)
        stocktake = Stocktake.objects.get(title='Inwentaryzacja Roczna 2026', tenant=self.tenant)
        self.assertEqual(stocktake.status, 'DRAFT')

        # Sprawdzenie utworzonych pozycji
        items = list(stocktake.items.all())
        self.assertEqual(len(items), 2)  # prod1 z partią i prod2 bez partii

        item1 = stocktake.items.get(product=self.prod1)
        self.assertEqual(item1.system_quantity, 50)
        self.assertEqual(item1.counted_quantity, 50)

        # 2. Aktualizacja ilości z natury (znaleziono 45 sztuk, czyli niedobór -5)
        response_update = self.client.post(reverse('stocktake_item_update', kwargs={'item_id': item1.id}), {
            'counted_quantity': 45,
            'notes': 'Uszkodzone 5 sztuk podczas transportu'
        })
        self.assertEqual(response_update.status_code, 200)
        item1.refresh_from_db()
        self.assertEqual(item1.counted_quantity, 45)
        self.assertEqual(item1.difference, -5)

        # 3. Zatwierdzenie inwentaryzacji
        response_complete = self.client.post(reverse('stocktake_complete', kwargs={'pk': stocktake.pk}))
        self.assertEqual(response_complete.status_code, 302)

        stocktake.refresh_from_db()
        self.assertEqual(stocktake.status, 'COMPLETED')
        self.assertIsNotNone(stocktake.completed_at)

        # Weryfikacja czy stan partii w magazynie został zaktualizowany
        self.batch1.refresh_from_db()
        self.assertEqual(self.batch1.current_stock, 45)

        # Weryfikacja wpisu w ActivityLog
        log_entry = ActivityLog.objects.filter(
            tenant=self.tenant,
            action='STOCKTAKE_ADJUSTMENT',
            product=self.prod1
        ).first()
        self.assertIsNotNone(log_entry)
        self.assertEqual(log_entry.old_value, '50')
        self.assertEqual(log_entry.new_value, '45')

    def test_stocktake_cancel_flow(self):
        """Test anulowania arkusza inwentaryzacyjnego."""
        stocktake = Stocktake.objects.create(
            tenant=self.tenant,
            created_by=self.user,
            title='Inwentaryzacja do anulowania',
            status='DRAFT'
        )

        # GET renderuje modal potwierdzenia
        response_get = self.client.get(reverse('stocktake_cancel', kwargs={'pk': stocktake.pk}))
        self.assertEqual(response_get.status_code, 200)
        self.assertTemplateUsed(response_get, 'inventory/partials/confirm_stocktake_cancel.html')

        # POST anuluje inwentaryzację
        response_post = self.client.post(reverse('stocktake_cancel', kwargs={'pk': stocktake.pk}))
        self.assertEqual(response_post.status_code, 302)

        stocktake.refresh_from_db()
        self.assertEqual(stocktake.status, 'CANCELLED')


class CrossTenantIsolationTests(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(name="Tenant A", subdomain="tenant-a", is_active=True)
        self.tenant_b = Tenant.objects.create(name="Tenant B", subdomain="tenant-b", is_active=True)

        self.user_a = User.objects.create_user(
            username="user_a",
            email="user_a@test.com",
            password="password_a",
            tenant=self.tenant_a
        )
        self.user_b = User.objects.create_user(
            username="user_b",
            email="user_b@test.com",
            password="password_b",
            tenant=self.tenant_b
        )

        self.client_a = Client()
        self.client_a.login(username="user_a", password="password_a")

        self.client_b = Client()
        self.client_b.login(username="user_b", password="password_b")

        # Obiekty Tenanta A
        self.prod_a = Product.objects.create(
            name="Produkt Tenanta A",
            tenant=self.tenant_a
        )
        self.loc_a = Location.objects.create(
            name="Magazyn Tenanta A",
            tenant=self.tenant_a
        )

        # Obiekty Tenanta B
        self.prod_b = Product.objects.create(
            name="Produkt Tenanta B",
            tenant=self.tenant_b
        )
        self.loc_b = Location.objects.create(
            name="Magazyn Tenanta B",
            tenant=self.tenant_b
        )

    def test_product_edit_cross_tenant_denied(self):
        """Użytkownik A nie może edytować produktu Tenanta B (powinien dostać 404)."""
        response = self.client_a.get(reverse('product_edit', kwargs={'pk': self.prod_b.pk}))
        self.assertEqual(response.status_code, 404)

        response_post = self.client_a.post(
            reverse('product_edit', kwargs={'pk': self.prod_b.pk}),
            {'name': 'Zmieniona nazwa'}
        )
        self.assertEqual(response_post.status_code, 404)

    def test_product_delete_cross_tenant_denied(self):
        """Użytkownik A nie może usunąć produktu Tenanta B."""
        response = self.client_a.post(reverse('product_delete', kwargs={'pk': self.prod_b.pk}))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Product.objects.filter(pk=self.prod_b.pk).exists())

    def test_product_list_only_shows_current_tenant(self):
        """Lista produktów powinna pokazywać wyłącznie produkty bieżącego tenanta."""
        response = self.client_a.get(reverse('product_list'))
        self.assertEqual(response.status_code, 200)
        products = list(response.context['products'])
        self.assertIn(self.prod_a, products)
        self.assertNotIn(self.prod_b, products)

    def test_location_cross_tenant_isolation(self):
        """Użytkownik A nie może wyświetlić ani modyfikować magazynu Tenanta B."""
        response = self.client_a.get(reverse('location_edit', kwargs={'pk': self.loc_b.pk}))
        self.assertEqual(response.status_code, 404)

        response_del = self.client_a.post(reverse('location_delete', kwargs={'pk': self.loc_b.pk}))
        self.assertEqual(response_del.status_code, 404)


class ProductFormSetEditTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Tenant Formset", is_active=True)
        self.user = User.objects.create_user(
            username="formset_user",
            password="password",
            tenant=self.tenant
        )
        self.client = Client()
        self.client.login(username="formset_user", password="password")

        self.location = Location.objects.create(
            name="Magazyn 1",
            tenant=self.tenant,
            is_default=True
        )
        self.supplier1 = Supplier.objects.create(
            name="Dostawca 1",
            tenant=self.tenant
        )
        self.supplier2 = Supplier.objects.create(
            name="Dostawca 2",
            tenant=self.tenant
        )
        self.product = Product.objects.create(
            name="Produkt Testowy",
            tenant=self.tenant,
            vat_rate=Decimal("23.00"),
            min_threshold=5,
            target_stock=20
        )
        self.ps1 = ProductSupplier.objects.create(
            tenant=self.tenant,
            product=self.product,
            supplier=self.supplier1,
            supplier_sku="SKU-1"
        )
        self.batch1 = ProductBatch.objects.create(
            tenant=self.tenant,
            product=self.product,
            location=self.location,
            current_stock=10,
            net_price=Decimal("100.00"),
            gross_price=Decimal("123.00")
        )

    def test_product_edit_with_formsets_save_and_delete(self):
        """
        Test edycji produktu z formsetami:
        - zmiana nazwy produktu
        - usunięcie powiązania z dostawcą 1 i dodanie powiązania z dostawcą 2
        - modyfikacja partii 1
        """
        data = {
            'name': 'Produkt Testowy Zmieniony',
            'description': 'Nowy opis',
            'vat_rate': '23.00',
            'min_threshold': '10',
            'target_stock': '30',
            'is_favourite': 'on',

            # Supplier formset management
            'suppliers-TOTAL_FORMS': '2',
            'suppliers-INITIAL_FORMS': '1',
            'suppliers-MIN_NUM_FORMS': '0',
            'suppliers-MAX_NUM_FORMS': '1000',
            # Form 0: Usuwamy ps1
            'suppliers-0-id': str(self.ps1.id),
            'suppliers-0-product': str(self.product.id),
            'suppliers-0-supplier': str(self.supplier1.id),
            'suppliers-0-supplier_sku': 'SKU-1',
            'suppliers-0-DELETE': 'on',
            # Form 1: Dodajemy supplier2
            'suppliers-1-id': '',
            'suppliers-1-product': str(self.product.id),
            'suppliers-1-supplier': str(self.supplier2.id),
            'suppliers-1-supplier_sku': 'SKU-2',

            # Batch formset management
            'batches-TOTAL_FORMS': '1',
            'batches-INITIAL_FORMS': '1',
            'batches-MIN_NUM_FORMS': '0',
            'batches-MAX_NUM_FORMS': '1000',
            'batches-0-id': str(self.batch1.id),
            'batches-0-product': str(self.product.id),
            'batches-0-location': str(self.location.id),
            'batches-0-current_stock': '15',
            'batches-0-net_price': '110.00',
            'batches-0-gross_price': '135.30',
        }

        response = self.client.post(reverse('product_edit', kwargs={'pk': self.product.pk}), data)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.headers.get('HX-Trigger'), 'productChanged')

        self.product.refresh_from_db()
        self.assertEqual(self.product.name, 'Produkt Testowy Zmieniony')
        self.assertEqual(self.product.min_threshold, 10)
        self.assertTrue(self.product.is_favourite)

        # Sprawdzenie powiązań z dostawcami
        self.assertFalse(ProductSupplier.objects.filter(id=self.ps1.id).exists())
        self.assertTrue(ProductSupplier.objects.filter(product=self.product, supplier=self.supplier2, supplier_sku="SKU-2").exists())

        # Sprawdzenie partii
        self.batch1.refresh_from_db()
        self.assertEqual(self.batch1.current_stock, 15)
        self.assertEqual(self.batch1.net_price, Decimal('110.00'))
