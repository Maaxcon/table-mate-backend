from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0027_remove_order_orders_order_source_valid_and_more'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='session',
            name='orders_session_status_valid',
        ),
        migrations.AlterField(
            model_name='session',
            name='status',
            field=models.CharField(choices=[('scheduled', 'Scheduled'), ('open', 'Open'), ('closed', 'Closed'), ('voided', 'Voided')], default='open', max_length=20),
        ),
        migrations.AddConstraint(
            model_name='session',
            constraint=models.CheckConstraint(condition=models.Q(('status__in', ['scheduled', 'open', 'closed', 'voided'])), name='orders_session_status_valid'),
        ),
    ]
