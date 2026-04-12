from decimal import Decimal
from django.db.models import Sum
from .models import Order, ProductSupplier

def process_auto_order_logic(product):
    """
    Główna funkcja decyzyjna automatyzacji zakupów.
    """
    virtual_stock = product.get_virtual_stock()

    if virtual_stock < product.min_threshold:
        needed_quantity = product.target_stock - virtual_stock

        # 1. Szukamy istniejącego szkicu (żeby nie mnożyć zamówień)
        existing_draft = Order.objects.filter(
            product=product,
            status='CREATED',
            order_type='AUTO',
            tenant=product.tenant
        ).first()

        if existing_draft:
            existing_draft.quantity += needed_quantity
            existing_draft.save()
            return

        # 2. Logika ustalania ceny i dostawcy na podstawie historii
        last_order = Order.objects.filter(
            product=product,
            status='COMPLETED',
            tenant=product.tenant
        ).order_by('-created_at').first()

        # Domyślne wartości
        final_supplier = None
        final_net = Decimal('0.00')
        final_gross = Decimal('0.00')

        if last_order:
            # Cena z historii jest zawsze sugestią
            final_net = last_order.net_price
            final_gross = last_order.gross_price

            # Sprawdzamy, czy dostawca jest nadal powiązany z produktem (M2M)
            is_valid = product.supplier_mappings.filter(supplier=last_order.supplier).exists()
            if is_valid:
                final_supplier = last_order.supplier
            # Jeśli nie jest valid, final_supplier pozostaje None (zgodnie z planem)

        # 3. TWORZENIE ZAMÓWIENIA
        # Ta linia musi być wcięta tak samo jak "if last_order:" powyżej
        Order.objects.create(
            product=product,
            tenant=product.tenant,
            supplier=final_supplier,
            quantity=needed_quantity,
            net_price=final_net,
            gross_price=final_gross,
            order_type='AUTO',
            status='CREATED'
        )