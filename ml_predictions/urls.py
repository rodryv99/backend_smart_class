from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'predictions', views.PredictionViewSet)
router.register(r'prediction-history', views.PredictionHistoryViewSet)

urlpatterns = [
    path('', include(router.urls)),
]