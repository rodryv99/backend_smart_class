from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'grades', views.GradeViewSet)
router.register(r'final-grades', views.FinalGradeViewSet)

urlpatterns = [
    path('', include(router.urls)),
    
    # Rutas personalizadas para resúmenes
    path('student/<int:class_id>/', views.student_grades_summary, name='student-grades-summary'),
    path('student/<int:class_id>/<int:student_id>/', views.student_grades_summary, name='student-grades-summary-specific'),
    path('class/<int:class_id>/summary/', views.class_grades_summary, name='class-grades-summary'),
]