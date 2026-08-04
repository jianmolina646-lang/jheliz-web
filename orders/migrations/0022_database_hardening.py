from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("orders", "0021_orderitem_same_day_reminders")]

    operations = [
        migrations.AddConstraint(
            model_name="order",
            constraint=models.UniqueConstraint(fields=("payment_provider", "payment_reference"), condition=~models.Q(payment_reference=""), name="uniq_order_payment_reference"),
        ),
        migrations.AddConstraint(
            model_name="order",
            constraint=models.CheckConstraint(condition=models.Q(total__gte=0, discount_amount__gte=0, combo_discount_amount__gte=0), name="order_amounts_nonnegative"),
        ),
        migrations.AddConstraint(
            model_name="orderitem",
            constraint=models.UniqueConstraint(fields=("renewal_token",), condition=~models.Q(renewal_token=""), name="uniq_orderitem_renewal_token"),
        ),
        migrations.AddConstraint(model_name="orderitem", constraint=models.CheckConstraint(condition=models.Q(quantity__gte=1), name="orderitem_quantity_gte_1")),
        migrations.AddConstraint(model_name="orderitem", constraint=models.CheckConstraint(condition=models.Q(unit_price__gte=0), name="orderitem_unit_price_nonnegative")),
        migrations.RemoveIndex(model_name="emaillog", name="emaillog_sent_at_idx"),
        migrations.RemoveIndex(model_name="reminderrunlog", name="reminderrun_started_idx"),
    ]
