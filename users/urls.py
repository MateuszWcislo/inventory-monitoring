from django.urls import path
from . import views

urlpatterns = [
    path('list/', views.user_list, name='user_list'),
    path('create/', views.user_create, name='user_create'),
    path('edit/<int:pk>/', views.user_edit, name='user_edit'),
]