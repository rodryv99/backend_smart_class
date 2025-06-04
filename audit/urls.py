# audit/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'logs', views.AuditLogViewSet)
router.register(r'summaries', views.AuditLogSummaryViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('log-manual/', views.log_manual_action, name='log-manual-action'),
    path('action-choices/', views.get_action_choices, name='get-action-choices'),
    path('cleanup/', views.cleanup_old_logs, name='cleanup-old-logs'),
]