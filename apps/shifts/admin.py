from django.contrib import admin

from .models import Shift


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ["employee", "date", "start_time", "end_time", "restaurant"]
    list_filter = ["restaurant", "date", "employee"]
    search_fields = ["employee__email", "employee__first_name", "employee__last_name"]
