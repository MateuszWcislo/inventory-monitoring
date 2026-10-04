from django.db.models.signals import pre_delete, post_save, pre_save
from django.dispatch import receiver
from .models import Product, ProductBatch, ActivityLog

@receiver(pre_delete, sender=Product)
def cancel_orders_on_product_delete(sender, instance, **kwargs):
    """
    Przed usunięciem produktu, znajdź wszystkie powiązane zamówienia,
    które nie są jeszcze zakończone, i ustaw im status na 'CANCELLED'.
    """
    from orders.models import Order
    open_orders = Order.objects.filter(
        product=instance,
        tenant=instance.tenant
    ).exclude(status__in=['COMPLETED', 'CANCELLED'])
    open_orders.update(status='CANCELLED')


@receiver(pre_save, sender=ProductBatch)
def track_batch_stock_change_pre(sender, instance, **kwargs):
    """Przechowuje starą wartość stanu przed zapisem."""
    if instance.pk:
        try:
            old_obj = ProductBatch.objects.get(pk=instance.pk)
            instance._old_stock = old_obj.current_stock
        except ProductBatch.DoesNotExist:
            instance._old_stock = 0
    else:
        instance._old_stock = 0

@receiver(post_save, sender=ProductBatch)
def track_batch_stock_change_post(sender, instance, created, **kwargs):
    """Loguje zmianę stanu partii."""
    old_stock = getattr(instance, '_old_stock', 0)
    new_stock = instance.current_stock or 0

    if created or old_stock != new_stock:
        action = 'BATCH_CREATED' if created else 'STOCK_UPDATE'
        desc = f"Utworzono partię ze stanem {new_stock}" if created else f"Zmiana stanu partii: {old_stock} -> {new_stock}"
        
        ActivityLog.objects.create(
            tenant=instance.tenant,
            product=instance.product,
            product_batch=instance,
            action=action,
            description=desc,
            old_value=str(old_stock) if not created else None,
            new_value=str(new_stock)
        )

@receiver(post_save, sender=Product)
def track_product_changes(sender, instance, created, **kwargs):
    """Loguje utworzenie produktu."""
    if created:
        ActivityLog.objects.create(
            tenant=instance.tenant,
            product=instance,
            action='PRODUCT_CREATED',
            description=f"Utworzono nowy produkt: {instance.name}",
            new_value=instance.name
        )