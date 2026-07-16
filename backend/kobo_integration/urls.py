from django.urls import path
from . import views

urlpatterns = [
    path('records/', views.record_list, name='record_list'),
    path('records/add/', views.record_create, name='record_create'),
    path('records/<int:pk>/edit/', views.record_update, name='record_update'),
    path('records/<int:pk>/delete/', views.record_delete, name='record_delete'),
]
