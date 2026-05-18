from django.contrib import admin

from apps.authentication.models import User


@admin.register(User)
class CustomUserAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'email',
        'role',
        'is_staff',
        'is_active',
        'is_superuser',
    )
    list_filter = ('role', 'is_staff', 'is_active', 'is_superuser')
    search_fields = ('email', 'first_name', 'last_name')
    ordering = ('id',)
