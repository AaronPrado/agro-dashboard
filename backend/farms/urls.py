"""Rutas de la app farms."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from farms import views

app_name = "farms"

router = DefaultRouter()
router.register("farms", views.FarmViewSet, basename="farm")
router.register("animals", views.AnimalViewSet, basename="animal")
router.register("daily-yields", views.DailyYieldViewSet, basename="daily-yield")
router.register("milk-records", views.MilkRecordViewSet, basename="milk-record")
router.register("batches", views.AnimalBatchViewSet, basename="batch")
router.register("target-profiles", views.TargetProfileViewSet, basename="target-profile")

urlpatterns = [
    path("health/", views.health, name="health"),
    path("", include(router.urls)),
]
