from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'periods', views.PeriodViewSet)
router.register(r'subjects', views.SubjectViewSet)
router.register(r'courses', views.CourseViewSet)
router.register(r'groups', views.GroupViewSet)
router.register(r'classes', views.ClassViewSet)
router.register(r'attendances', views.AttendanceViewSet)
router.register(r'participations', views.ParticipationViewSet)

urlpatterns = [
    path('', include(router.urls)),
    # Añadir esta ruta de depuración
    path('debug/student-classes/', views.debug_student_classes, name='debug-student-classes'),
]