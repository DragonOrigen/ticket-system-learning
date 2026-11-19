from django.urls import path
from . import views, extras
urlpatterns = [
    path("lixeira/", extras.trash, name="trash"),
    path("lixeira/<int:pk>/restaurar/", extras.restore, name="ticket_restore"),
    path("lixeira/<int:pk>/apagar/", extras.purge, name="ticket_purge"),
    path("anexos/<int:pk>/", extras.download, name="attachment_download"),
    path("notificacoes/", extras.notifications, name="notifications"),
    path("relatorios/", extras.reports, name="reports"),
    path("tickets/<int:pk>/excluir/", extras.ticket_trash, name="ticket_delete"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("suporte/", views.ticket_list, {"area": "support"}, name="support_list"),
    path("tarefas/", views.ticket_list, {"area": "tasks"}, name="task_list"),
    path("ajuda/", views.help_page, name="help"),
    path("tickets/<int:pk>/editar/", views.ticket_edit, name="ticket_edit"),
    path("", views.ticket_list, name="ticket_list"),
    path("tickets/novo/", views.ticket_create, name="ticket_create"),
    path("tickets/<int:pk>/", views.ticket_detail, name="ticket_detail"),
]
