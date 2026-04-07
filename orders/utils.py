from .models import Order

def process_auto_order_logic(product):
    """Główna funkcja decyzyjna automatyzacji."""
    virtual_stock = product.get_virtual_stock()

    # Jeśli stan wirtualny spadnie poniżej progu alarmowego
    if virtual_stock < product.min_threshold:
        needed_quantity = product.target_stock - virtual_stock

        # 1. Szukamy istniejącego szkicu AUTO (tylko status CREATED)
        existing_draft = Order.objects.filter(
            product=product,
            status='CREATED',
            order_type='AUTO',
            tenant=product.tenant
        ).first()

        if existing_draft:
            # AKTUALIZACJA: Jeśli szkic istnieje, po prostu zwiększamy w nim ilość
            existing_draft.quantity += needed_quantity
            existing_draft.save()
        else:
            # TWORZENIE: Pobieramy dane z ostatniego zakończonego zamówienia jako wzór
            last_order = Order.objects.filter(
                product=product,
                status='COMPLETED',
                tenant=product.tenant
            ).order_by('-created_at').first()

            if last_order:
                Order.objects.create(
                    product=product,
                    tenant=product.tenant,
                    supplier=last_order.supplier,
                    quantity=needed_quantity,
                    net_price=last_order.net_price,
                    gross_price=last_order.gross_price,
                    order_type='AUTO',
                    status='CREATED'
                )