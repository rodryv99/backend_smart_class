from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

router = DefaultRouter()
router.register(r'users', views.UserViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('register/student/', views.register_student, name='register_student'),
    path('register/teacher/', views.register_teacher, name='register_teacher'),
    path('login/', views.login_view, name='login'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    # Nuevas rutas para actualizar perfiles
    path('teacher-profile/<int:pk>/', views.update_teacher_profile, name='update-teacher-profile'),
    path('student-profile/<int:pk>/', views.update_student_profile, name='update-student-profile'),
    # Nueva ruta para obtener todos los perfiles de estudiantes
    path('student-profiles/', views.get_all_student_profiles, name='get-all-student-profiles'),
]