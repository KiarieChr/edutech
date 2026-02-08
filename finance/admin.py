from django.contrib import admin
from .models import Account

@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'type', 'sub_type', 'is_active')
    list_filter = ('type', 'sub_type', 'is_active')
    search_fields = ('code', 'name')
    ordering = ('code',)
