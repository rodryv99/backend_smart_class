from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _

class User(AbstractUser):
    email = models.EmailField(_('email address'), unique=True)
    
    USER_TYPE_CHOICES = (
        ('admin', 'Administrador'),
        ('teacher', 'Profesor'),
        ('student', 'Alumno'),
    )
    
    user_type = models.CharField(max_length=10, choices=USER_TYPE_CHOICES, default='student')
    
    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email']
    
    def __str__(self):
        return self.username

class TeacherProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='teacher_profile')
    teacher_code = models.CharField(max_length=20, unique=True)
    ci = models.CharField(max_length=20, unique=True)
    first_name = models.CharField(max_length=100)  # Nombre
    last_name = models.CharField(max_length=100)   # Apellido
    phone = models.CharField(max_length=20)
    birth_date = models.DateField()
    
    def __str__(self):
        return f"{self.user.username} - {self.first_name} {self.last_name}"

class StudentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student_profile')
    ci = models.CharField(max_length=20, unique=True)
    first_name = models.CharField(max_length=100)  # Nombre
    last_name = models.CharField(max_length=100)   # Apellido
    phone = models.CharField(max_length=20)
    birth_date = models.DateField()
    tutor_name = models.CharField(max_length=100)
    tutor_phone = models.CharField(max_length=20)
    
    def __str__(self):
        return f"{self.user.username} - {self.first_name} {self.last_name}"