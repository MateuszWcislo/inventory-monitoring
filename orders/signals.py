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
    """
    Przyjęcie towaru na stan magazynowy po osiągnięciu statusu COMPLETED.
    """
    if getattr(instance, '_skip_signal', False):
        return

    if instance.status == 'COMPLETED':
        if not instance.product:
            return
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


@receiver(post_save, sender=Product)
def trigger_auto_order_on_product_change(sender, instance, created, **kwargs):
    """
    Wywoływane, gdy zmieni się konfiguracja produktu (np. min_threshold lub target_stock).
    Dla nowych produktów pomijamy – weryfikacja następuje w widoku po zapisaniu partii.
    """
    if created:
        return
    if not getattr(instance, '_skip_signal', False):
        process_auto_order_logic(instance)


@receiver(post_save, sender=ProductBatch)
def trigger_auto_order_on_stock_change(sender, instance, created, **kwargs):
    """
    Wywoływane, gdy zmieni się fizyczny stan magazynowy (np. dodasz nową partię lub zaktualizujesz stan).
    """
    if not getattr(instance, '_skip_signal', False) and instance.product:
        process_auto_order_logic(instance.product)
