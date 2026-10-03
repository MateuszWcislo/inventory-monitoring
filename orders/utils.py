from decimal import Decimal
from django.db.models import Sum
from .models import Order


def process_auto_order_logic(product):
    """
    Główna funkcja decyzyjna automatyzacji zakupów.
    Tworzy lub aktualizuje szkic zamówienia AUTO, gdy stan wirtualny spadnie poniżej progu min_threshold.
    """
    if not product or product.min_threshold is None:
        return

    virtual_stock = product.get_virtual_stock()

    if virtual_stock < product.min_threshold:
        target = product.target_stock if product.target_stock is not None else product.min_threshold
        needed_quantity = target - virtual_stock

        if needed_quantity <= 0:
            return

        # 1. Szukamy istniejącego szkicu (żeby nie mnożyć zamówień)
        existing_draft = Order.objects.filter(
            product=product,
            status='CREATED',
            order_type='AUTO',
            tenant=product.tenant
        ).first()

        if existing_draft:
            # Nie dodajemy do istniejącego szkicu, jeśli virtual_stock już go uwzględnia.
            # get_virtual_stock() uwzględnia status='CREATED', więc jeśli nadal jesteśmy poniżej progu,
            # to znaczy, że trzeba zwiększyć zamówienie o różnicę.
            if existing_draft.quantity < needed_quantity + existing_draft.quantity: # to jest zawsze prawda jeśli needed > 0
                 # Ale chwila: needed_quantity = target - virtual_stock.
                 # Jeśli virtual_stock zawiera już existing_draft.quantity, to needed_quantity jest tym, co brakuje PONAD to zamówienie.
                 existing_draft.quantity += needed_quantity
                 existing_draft.save()
            return

        # 2. Logika ustalania ceny i dostawcy na podstawie historii lub powiązań produktu
        last_order = Order.objects.filter(
            product=product,
            status='COMPLETED',
            tenant=product.tenant
        ).order_by('-created_at').first()

        final_supplier = None
        final_net = Decimal('0.00')
        final_gross = Decimal('0.00')

        if last_order:
            final_net = last_order.net_price
            final_gross = last_order.gross_price
            is_valid = product.supplier_mappings.filter(supplier=last_order.supplier).exists()
            if is_valid:
                final_supplier = last_order.supplier
        else:
            first_mapping = product.supplier_mappings.first()
            if first_mapping:
                final_supplier = first_mapping.supplier

            latest_batch = product.batches.order_by('-created_at').first()
            if latest_batch:
                final_net = latest_batch.net_price
                final_gross = latest_batch.gross_price

        # 3. Tworzenie nowego zamówienia AUTO
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
