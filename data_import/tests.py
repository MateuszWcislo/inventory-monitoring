import io
import csv
from decimal import Decimal
from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from tenants.models import Tenant
from users.models import User
from inventory.models import Product, ProductBatch, ProductSupplier
from suppliers.models import Supplier
from data_import.models import ImportJob
from data_import.services import (
    parse_uploaded_file,
    analyze_product_import,
    execute_product_import
)

class ProductImportTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Firma Testowa", subdomain="firma-testowa")
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="password123",
            tenant=self.tenant
        )
        self.supplier = Supplier.objects.create(
            tenant=self.tenant,
            name="Dostawca Hurt"
        )

    def test_parse_csv_and_analyze(self):
        csv_content = (
            "Nazwa;Opis;VAT %;Próg alarmowy;Stan docelowy;Cena netto;Cena brutto;Stan partii;SKU u dostawcy;Nazwa dostawcy\n"
            "Klocki Hamulcowe;Ceramiczne;23;10;25;100.00;123.00;5;KH-101;Dostawca Hurt\n"
            "Olej 5W30;Syntetyk;23;5;15;50.00;;10;OL-530;Nieistniejący Dostawca\n"
            "Klocki Hamulcowe;Inny opis;23;12;20;100.00;123.00;2;KH-102;Dostawca Hurt\n"
        ).encode('utf-8-sig')

        uploaded = SimpleUploadedFile("produkty.csv", csv_content, content_type="text/csv")
        rows = parse_uploaded_file(uploaded)
        self.assertEqual(len(rows), 3)

        analysis = analyze_product_import(rows, self.tenant)
        self.assertEqual(analysis['total_count'], 3)
        self.assertEqual(analysis['total_valid'], 3)
        self.assertTrue(analysis['has_file_duplicates'])
        self.assertTrue(any("Klocki Hamulcowe" in d for d in analysis['file_duplicates_names']))

        # Wiersz 2 ma tylko cenę netto 50 -> brutto powinno zostać wyliczone na 61.50
        self.assertEqual(analysis['rows'][1]['parsed']['gross_price'], Decimal('61.50'))
        self.assertEqual(analysis['rows'][1]['parsed']['current_stock'], 10)

        # Wiersz 2 ma nieistniejącego dostawcę -> ostrzeżenie, ale jest poprawny (is_valid == True)
        self.assertTrue(analysis['rows'][1]['is_valid'])
        self.assertTrue(any("nie istnieje w systemie" in w for w in analysis['rows'][1]['warnings']))

    def test_execute_product_import_with_batches_and_prices(self):
        rows_data = [
            {
                'Nazwa': 'Filtr Powietrza',
                'Opis': 'Wysoka jakość',
                'VAT %': '23',
                'Próg alarmowy': '8',
                'Stan docelowy': '16',
                'Cena netto': '40.00',
                'Cena brutto': '49.20',
                'Stan partii': '12',
                'SKU u dostawcy': 'FP-01',
                'Nazwa dostawcy': 'Brakujący Dostawca'
            },
            {
                'Nazwa': 'Płyn Hamulcowy',
                'Opis': 'DOT4',
                'VAT %': '23',
                'Próg alarmowy': '4',
                'Stan docelowy': '10',
                'Cena netto': '',
                'Cena brutto': '24.60',
                'Stan partii': '7',
                'SKU u dostawcy': 'DOT4-500',
                'Nazwa dostawcy': 'Dostawca Hurt'
            }
        ]

        analysis = analyze_product_import(rows_data, self.tenant)
        result = execute_product_import(analysis['rows'], self.tenant, user=self.user)

        self.assertEqual(result['imported_count'], 2)
        self.assertEqual(result['failed_count'], 0)

        # Sprawdzenie utworzenia produktów
        p1 = Product.objects.get(tenant=self.tenant, name='Filtr Powietrza')
        self.assertEqual(p1.min_threshold, 8)
        self.assertEqual(p1.target_stock, 16)
        self.assertEqual(p1.total_stock, 12)
        b1 = ProductBatch.objects.get(product=p1)
        self.assertEqual(b1.net_price, Decimal('40.00'))
        self.assertEqual(b1.gross_price, Decimal('49.20'))
        self.assertEqual(b1.current_stock, 12)
        # Relacja nie powinna powstać dla brakującego dostawcy
        self.assertEqual(ProductSupplier.objects.filter(product=p1).count(), 0)

        p2 = Product.objects.get(tenant=self.tenant, name='Płyn Hamulcowy')
        self.assertEqual(p2.total_stock, 7)
        b2 = ProductBatch.objects.get(product=p2)
        self.assertEqual(b2.gross_price, Decimal('24.60'))
        self.assertEqual(b2.net_price, Decimal('20.00'))
        # Relacja powinna powstać dla istniejącego dostawcy
        rel = ProductSupplier.objects.get(product=p2)
        self.assertEqual(rel.supplier, self.supplier)
        self.assertEqual(rel.supplier_sku, 'DOT4-500')

    def test_import_products_view_selective_confirm(self):
        self.client.force_login(self.user)
        csv_content = (
            "Nazwa;Opis;VAT %;Próg alarmowy;Stan docelowy;SKU u dostawcy;Nazwa dostawcy\n"
            "Produkt A;Opis A;23;5;10;;Dostawca Hurt\n"
            "Produkt B;Opis B;23;5;10;;Dostawca Hurt\n"
        ).encode('utf-8-sig')

        uploaded = SimpleUploadedFile("produkty.csv", csv_content, content_type="text/csv")
        # Krok 1: analyze
        resp1 = self.client.post('/import/products/', {'action': 'analyze', 'file': uploaded})
        self.assertEqual(resp1.status_code, 200)
        self.assertIn('step', resp1.context)
        self.assertEqual(resp1.context['step'], 'preview')
        serialized_rows = resp1.context['serialized_rows_json']

        # Krok 2: confirm tylko dla wiersza 1 (odrzucamy wiersz 2)
        resp2 = self.client.post('/import/products/', {
            'action': 'confirm',
            'file_name': 'produkty.csv',
            'serialized_rows_json': serialized_rows,
            'selected_rows': ['1']  # tylko wiersz 1
        })
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2.context['result']['imported_count'], 1)
        self.assertTrue(Product.objects.filter(tenant=self.tenant, name='Produkt A').exists())
        self.assertFalse(Product.objects.filter(tenant=self.tenant, name='Produkt B').exists())

    def test_import_job_detail_view(self):
        self.client.force_login(self.user)
        job = ImportJob.objects.create(
            tenant=self.tenant,
            user=self.user,
            file_type='PRODUCTS',
            status='COMPLETED',
            file_name='test_file.xlsx',
            records_total=10,
            records_imported=8,
            records_failed=2,
            error_log="Wiersz 3: Błąd walidacji\nWiersz 5: Brak dostawcy"
        )

        response = self.client.get(f'/import/job/{job.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'data_import/partials/job_detail.html')
        self.assertContains(response, 'test_file.xlsx')
        self.assertContains(response, 'Wiersz 3: Błąd walidacji')
        self.assertContains(response, 'Wiersz 5: Brak dostawcy')
        self.assertContains(response, '10')
        self.assertContains(response, '8')
        self.assertContains(response, '2')

    def test_import_job_detail_tenant_isolation(self):
        other_tenant = Tenant.objects.create(name="Inna Firma", subdomain="inna-firma")
        other_job = ImportJob.objects.create(
            tenant=other_tenant,
            file_type='PRODUCTS',
            status='COMPLETED',
            file_name='other.xlsx'
        )
        self.client.force_login(self.user)
        response = self.client.get(f'/import/job/{other_job.id}/')
        self.assertEqual(response.status_code, 404)
