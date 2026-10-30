import os
import sys
import django
from decimal import Decimal
import datetime
from django.utils import timezone

# Konfiguracja Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from tenants.models import Tenant
from users.models import User
from inventory.models import Location, Product, ProductBatch
from suppliers.models import Supplier
from orders.models import Order
from services.models import Service
from work_orders.models import WorkOrder, WorkOrderProduct, WorkOrderService

def seed_demo_data():
    tenant, _ = Tenant.objects.get_or_create(
        name='demo',
        defaults={
            'nip': '1112223344',
            'email': 'demo@example.com',
            'phone': '+48 123 456 789',
            'address': 'ul. Przykładowa 10, 00-001 Warszawa'
        }
    )

    user = User.objects.filter(tenant=tenant).first()

    # 1. Tworzenie 2 magazynów
    loc_main, _ = Location.objects.get_or_create(
        tenant=tenant,
        name='Magazyn Główny (A)',
        defaults={'code': 'MAG-01', 'address': 'ul. Centralna 1, Warszawa', 'is_default': True}
    )
    loc_secondary, _ = Location.objects.get_or_create(
        tenant=tenant,
        name='Magazyn Pomocniczy (B)',
        defaults={'code': 'MAG-02', 'address': 'ul. Warsztatowa 5, Warszawa', 'is_default': False}
    )

    # 2. Tworzenie 3 dostawców
    sup1, _ = Supplier.objects.get_or_create(
        tenant=tenant,
        name='Dostawca Alfa Sp. z o.o.',
        defaults={
            'representative': 'Jan Kowalski',
            'email': 'alfa@dostawcy.pl',
            'phone': '123-111-222',
            'address': 'ul. Przemysłowa 1, Kraków',
            'nip': '1234567891'
        }
    )
    sup2, _ = Supplier.objects.get_or_create(
        tenant=tenant,
        name='Dostawca Beta Hurtownia',
        defaults={
            'representative': 'Anna Nowak',
            'email': 'zamowienia@beta-hurt.pl',
            'phone': '123-333-444',
            'address': 'ul. Magazynowa 15, Katowice',
            'nip': '1234567892'
        }
    )
    sup3, _ = Supplier.objects.get_or_create(
        tenant=tenant,
        name='Dostawca Gamma Narzędzia',
        defaults={
            'representative': 'Piotr Wiśniewski',
            'email': 'biuro@gamma-tools.pl',
            'phone': '123-555-666',
            'address': 'ul. Handlowa 8, Warszawa',
            'nip': '1234567893'
        }
    )
    suppliers = [sup1, sup2, sup3]

    # 3. Tworzenie produktów
    products_data = [
        {'name': 'Olej silnikowy 5W30', 'min_threshold': 10, 'is_favourite': True},
        {'name': 'Filtr powietrza', 'min_threshold': 5, 'is_favourite': True},
        {'name': 'locki hamulcowe komplet', 'min_threshold': 8, 'is_favourite': False},
        {'name': 'Płyn hamulcowy DOT-4', 'min_threshold': 15, 'is_favourite': False},
        {'name': 'Świeca zapłonowa', 'min_threshold': 20, 'is_favourite': False},
    ]

    created_products = []
    for p_data in products_data:
        p, _ = Product.objects.get_or_create(
            tenant=tenant,
            name=p_data['name'],
            defaults={
                'min_threshold': p_data['min_threshold'],
                'target_stock': p_data['min_threshold'] * 2,
                'is_favourite': p_data['is_favourite'],
                'vat_rate': Decimal('23.00'),
                'description': f"Opis dla {p_data['name']}"
            }
        )
        created_products.append(p)

    # 4. Tworzenie partii (batches) w obu magazynach oraz powiązanych zamówień
    from decimal import ROUND_HALF_UP
    import random

    # Funkcja pomocnicza do losowania wartości Decimal z przedziału
    def random_decimal(min_val, max_val, places=2):
        value = random.uniform(float(min_val), float(max_val))
        return Decimal(str(value)).quantize(Decimal(10) ** -places, rounding=ROUND_HALF_UP)

    now = timezone.now()
    batch_configurations = [
        # (loc, quantity [10-50], base_price [40.00-60.00], days_ago [1-30])
        (loc_main, random.randint(10, 50), random_decimal(40, 60), random.randint(1, 30)),
        (loc_main, random.randint(10, 50), random_decimal(20, 30), random.randint(1, 30)),
        (loc_secondary, random.randint(5, 30), random_decimal(50, 65), random.randint(1, 15)),
        (loc_secondary, random.randint(5, 30), random_decimal(5, 12), random.randint(1, 15)),
    ]

    for idx, prod in enumerate(created_products):
        for b_idx, (loc, qty, base_price, days_ago) in enumerate(batch_configurations):
            net = base_price + Decimal(str(idx * 10))
            vat = Decimal('23.00')
            gross = (net * (Decimal('1') + vat / Decimal('100'))).quantize(Decimal('0.01'))

            batch = ProductBatch.objects.create(
                tenant=tenant,
                product=prod,
                location=loc,
                current_stock=qty,
                net_price=net,
                gross_price=gross
            )

            # Dostawca
            sup = suppliers[(idx + b_idx) % len(suppliers)]

            order_date = now - datetime.timedelta(days=days_ago)
            order = Order.objects.create(
                tenant=tenant,
                product=prod,
                supplier=sup,
                quantity=qty + 5,
                net_price=net,
                gross_price=gross,
                status='COMPLETED'
            )
            Order.objects.filter(id=order.id).update(created_at=order_date, updated_at=order_date)
            batch.processed_orders.add(order)

    # 5. Tworzenie usług (Services) i zleceń pracy (WorkOrders)
    srv1, _ = Service.objects.get_or_create(
        tenant=tenant,
        name='Wymiana oleju i filtrów',
        defaults={
            'net_price': Decimal('150.00'),
            'gross_price': Decimal('184.50'),
            'vat_rate': Decimal('23.00')
        }
    )
    srv2, _ = Service.objects.get_or_create(
        tenant=tenant,
        name='Przegląd układu hamulcowego',
        defaults={
            'net_price': Decimal('200.00'),
            'gross_price': Decimal('246.00'),
            'vat_rate': Decimal('23.00')
        }
    )

    # Zlecenie pracy ze zużyciem materiałów
    wo1 = WorkOrder.objects.create(
        tenant=tenant,
        name='Serwis okresowy floty - Pojazd #1',
        client='Jan Kowalski Auto-Serwis',
        description='Wymiana filtrów i płynów eksploatacyjnych',
        status='COMPLETED'
    )
    wo1_date = now - datetime.timedelta(days=3)
    WorkOrder.objects.filter(id=wo1.id).update(created_at=wo1_date)

    p1 = created_products[0]
    p2 = created_products[1]
    b1 = ProductBatch.objects.filter(product=p1, location=loc_main).first()
    b2 = ProductBatch.objects.filter(product=p2, location=loc_main).first()

    if b1:
        WorkOrderProduct.objects.create(
            order=wo1,
            product_batch=b1,
            quantity=4,
            unit_price_net=Decimal('80.00'),
            vat_rate=p1.vat_rate,
            name_snapshot=p1.name
        )
    if b2:
        WorkOrderProduct.objects.create(
            order=wo1,
            product_batch=b2,
            quantity=2,
            unit_price_net=Decimal('60.00'),
            vat_rate=p2.vat_rate,
            name_snapshot=p2.name
        )

    WorkOrderService.objects.create(
        order=wo1,
        service=srv1,
        quantity=1,
        unit_price_net=srv1.net_price,
        vat_rate=srv1.vat_rate,
        name_snapshot=srv1.name
    )

    print("--- Sukces: Utworzono dane testowe dla tenanta demo ---")
    print("Magazyny:", Location.objects.filter(tenant=tenant).count())
    print("Dostawcy:", Supplier.objects.filter(tenant=tenant).count())
    print("Produkty:", Product.objects.filter(tenant=tenant).count())
    print("Partie:", ProductBatch.objects.filter(tenant=tenant).count())
    print("Zamowienia:", Order.objects.filter(tenant=tenant).count())
    print("Uslugi:", Service.objects.filter(tenant=tenant).count())
    print("Zlecenia pracy:", WorkOrder.objects.filter(tenant=tenant).count())

if __name__ == '__main__':
    seed_demo_data()
