from django.contrib import admin
from .models import CustomUser

# Registered Models

class CustomUserAdmin(admin.ModelAdmin):

    @admin.display(description='Full Name')
    def full_name(self, obj: CustomUser) -> str:
        return f"{obj.first_name} {obj.last_name}".strip() or obj.username

    list_display = ('username','email', 'full_name', 'is_staff')
    search_fields = ('email', 'first_name', 'last_name')
    ordering = ('email',)

admin.site.register(CustomUser, CustomUserAdmin)
