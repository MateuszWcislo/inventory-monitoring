import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from .models import Order
from inventory.models import Product, ProductBatch
from .utils import process_auto_order_logic

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Order)
def handle_order_completion(sender, instance, created, **kwargs):
    # Zapobiegamy pętli, jeśli flaga została ustawiona w tym cyklu
    if getattr(instance, '_skip_signal', False):
        return

    if instance.status == 'COMPLETED':
        with transaction.atomic():
            # Sprawdzamy czy to konkretne zamówienie zostało już rozliczone w magazynie
            if not ProductBatch.objects.filter(processed_orders=instance).exists():
                batch = ProductBatch.objects.filter(
                    product=instance.product,
                    net_price=instance.net_price,
                    tenant=instance.tenant
                ).first()

                if batch:
                    batch.current_stock += instance.quantity
                    batch.save()
                    batch.processed_orders.add(instance)
                else:
                    new_batch = ProductBatch.objects.create(
                        product=instance.product,
                        tenant=instance.tenant,
                        current_stock=instance.quantity,
                        net_price=instance.net_price,
                    )
                    new_batch.processed_orders.add(instance)

    # Ustawiamy flagę i przeliczamy zapotrzebowanie (tylko jeśli mamy produkt)
    instance._skip_signal = True
    if instance.product:
        process_auto_order_logic(instance.product)


@receiver(post_save, sender=Product)
def trigger_auto_order_on_product_change(sender, instance, created, **kwargs):
    """
    Wywoływane, gdy zmienisz np. min_threshold w edycji produktu.
    """
    # Opcjonalnie: Możesz tu dodać logikę sprawdzającą, czy pola
    # min_threshold lub target_stock uległy zmianie, ale
    # na obecnym etapie Twoja funkcja i tak jest bezpieczna.
    if not getattr(instance, '_skip_signal', False):
        process_auto_order_logic(instance)

@receiver(post_save, sender=ProductBatch)
def trigger_auto_order_on_stock_change(sender, instance, created, **kwargs):
    """
    Wywoływane, gdy zmieni się fizyczny stan magazynowy (np. dodasz nową partię).
    """
    if instance.product:
        process_auto_order_logic(instance.product)