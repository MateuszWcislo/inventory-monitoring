from django.db.models.signals import pre_delete
from django.dispatch import receiver
from .models import Product

@receiver(pre_delete, sender=Product)
def cancel_orders_on_product_delete(sender, instance, **kwargs):
    """
    Przed usunięciem produktu, znajdź wszystkie powiązane zamówienia,
    które nie są jeszcze zakończone, i ustaw im status na 'CANCELLED'.
    """
    # Import wewnątrz funkcji, aby uniknąć problemu circular import
    from orders.models import Order

    # Szukamy zamówień, które nie są COMPLETED ani CANCELLED
    open_orders = Order.objects.filter(
        product=instance,
        tenant=instance.tenant
    ).exclude(status__in=['COMPLETED', 'CANCELLED'])

    # Masowa aktualizacja statusu
    open_orders.update(status='CANCELLED')