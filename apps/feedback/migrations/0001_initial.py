import django.core.validators
import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('menu', '0012_menucategory_color'),
        ('orders', '0026_session_auto_extended'),
        ('restaurants', '0023_seed_new_restaurants'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Feedback',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('public_id', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('overall_rating', models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(5)])),
                ('service_rating', models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(5)])),
                ('comment', models.TextField(blank=True, default='')),
                ('review_status', models.CharField(choices=[('new', 'New'), ('reviewed', 'Reviewed'), ('resolved', 'Resolved')], default='new', max_length=20)),
                ('prompt_shown_at', models.DateTimeField(blank=True, null=True)),
                ('dismissed', models.BooleanField(default=False)),
                ('guest', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='feedback', to=settings.AUTH_USER_MODEL)),
                ('order', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='feedback', to='orders.order')),
                ('restaurant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='restaurants.restaurant')),
            ],
            options={
                'ordering': ['-created_at', '-id'],
            },
        ),
        migrations.CreateModel(
            name='DishFeedback',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('public_id', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('rating', models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(5)])),
                ('comment', models.TextField(blank=True, default='')),
                ('menu_item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='dish_feedback', to='menu.menuitem')),
                ('feedback', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='dish_feedback', to='feedback.feedback')),
            ],
            options={
                'ordering': ['id'],
            },
        ),
        migrations.AddConstraint(
            model_name='feedback',
            constraint=models.CheckConstraint(condition=models.Q(('overall_rating__gte', 1), ('overall_rating__lte', 5)), name='feedback_overall_rating_range'),
        ),
        migrations.AddConstraint(
            model_name='feedback',
            constraint=models.CheckConstraint(condition=models.Q(('service_rating__gte', 1), ('service_rating__lte', 5)), name='feedback_service_rating_range'),
        ),
        migrations.AddConstraint(
            model_name='feedback',
            constraint=models.CheckConstraint(condition=models.Q(('review_status__in', ['new', 'reviewed', 'resolved'])), name='feedback_review_status_valid'),
        ),
        migrations.AddConstraint(
            model_name='feedback',
            constraint=models.UniqueConstraint(fields=('restaurant', 'id'), name='feedback_rest_uniq'),
        ),
        migrations.AddConstraint(
            model_name='dishfeedback',
            constraint=models.CheckConstraint(condition=models.Q(('rating__gte', 1), ('rating__lte', 5)), name='dishfeedback_rating_range'),
        ),
        migrations.AddConstraint(
            model_name='dishfeedback',
            constraint=models.UniqueConstraint(fields=('feedback', 'menu_item'), name='dishfeedback_feedback_menu_item_unique'),
        ),
    ]
