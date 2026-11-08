from django.contrib import admin
from .models import Machine

# Usuários e grupos são gerenciados pelo admin nativo do Django.
# Tickets e mensagens só são alterados pelo fluxo que registra autoria e histórico.
@admin.register(Machine)
class MachineAdmin(admin.ModelAdmin):
    list_display = ("name", "active")
    search_fields = ("name",)
