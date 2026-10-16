from django.urls import path

from . import views

urlpatterns = [
    path("health", views.health),
    path("geocode", views.geocode),
    path("plan", views.plan),
    path("plan/<str:plan_id>/heatmap", views.heatmap),
]
