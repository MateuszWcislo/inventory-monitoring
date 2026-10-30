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

    # Szukamy istniejącego szkicu AUTO (żeby nie mnożyć zamówień)
    existing_draft = Order.objects.filter(
        product=product,
        status='CREATED',
        order_type='AUTO',
        tenant=product.tenant
    ).first()

    # Stan wirtualny produktu (fizyczny stan + oczekujące zamówienia)
    virtual_stock = product.get_virtual_stock()

    # Stan wirtualny z wyłączeniem bieżącego szkicu AUTO (czyli fizyczny + zamówienia MANUAL / ORDERED)
    virtual_without_draft = virtual_stock - (existing_draft.quantity if existing_draft else 0)

    # Sprawdzamy czy bez szkicu stan jest poniżej progu alarmowego
    if virtual_without_draft < product.min_threshold:
        target = product.target_stock if product.target_stock is not None else product.min_threshold
        needed_quantity = target - virtual_without_draft

        if needed_quantity <= 0:
            if existing_draft:
                existing_draft.delete()
            return

        if existing_draft:
            if existing_draft.quantity != needed_quantity:
                existing_draft.quantity = needed_quantity
                existing_draft.save()
            return

        # Logika ustalania ceny i dostawcy na podstawie historii lub powiązań produktu
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

        # Tworzenie nowego zamówienia AUTO
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
    elif existing_draft:
        # Jeśli stan bez szkicu już osiągnął min_threshold (np. przyjęto dostawę ręczną), usuwamy niepotrzebny szkic
        existing_draft.delete()
