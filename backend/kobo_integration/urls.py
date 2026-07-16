from django.urls import path
from . import views
from .webhook import kobo_webhook

urlpatterns = [
    path('records/', views.record_list, name='record_list'),
    path('records/add/', views.record_create, name='record_create'),
    path('records/export/', views.export_records_csv, name='export_records_csv'),
    path('records/<int:pk>/', views.record_detail, name='record_detail'),
    path('records/<int:pk>/edit/', views.record_update, name='record_update'),
    path('records/<int:pk>/delete/', views.record_delete, name='record_delete'),
    path('projects/<int:project_id>/sync/', views.kobo_sync, name='kobo_sync'),
    path('projects/<int:project_id>/webhook/', views.register_kobo_webhook, name='register_kobo_webhook'),
    # Webhook — no auth middleware, validated internally by token
    path('webhook/kobo/', kobo_webhook, name='kobo_webhook'),
]
