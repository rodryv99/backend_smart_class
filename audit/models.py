# audit/models.py
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
import json

User = get_user_model()

class AuditLog(models.Model):
    """
    Modelo para registrar todas las acciones realizadas por los usuarios
    """
    ACTION_CHOICES = [
        # Autenticación
        ('LOGIN', 'Inicio de sesión'),
        ('LOGOUT', 'Cierre de sesión'),
        ('LOGIN_FAILED', 'Intento de inicio de sesión fallido'),
        
        # Usuarios
        ('USER_CREATE', 'Creación de usuario'),
        ('USER_UPDATE', 'Actualización de usuario'),
        ('USER_DELETE', 'Eliminación de usuario'),
        ('USER_VIEW', 'Visualización de usuario'),
        
        # Perfiles
        ('TEACHER_PROFILE_CREATE', 'Creación de perfil de profesor'),
        ('TEACHER_PROFILE_UPDATE', 'Actualización de perfil de profesor'),
        ('STUDENT_PROFILE_CREATE', 'Creación de perfil de estudiante'),
        ('STUDENT_PROFILE_UPDATE', 'Actualización de perfil de estudiante'),
        
        # Períodos
        ('PERIOD_CREATE', 'Creación de período'),
        ('PERIOD_UPDATE', 'Actualización de período'),
        ('PERIOD_DELETE', 'Eliminación de período'),
        ('PERIOD_VIEW', 'Visualización de período'),
        
        # Materias
        ('SUBJECT_CREATE', 'Creación de materia'),
        ('SUBJECT_UPDATE', 'Actualización de materia'),
        ('SUBJECT_DELETE', 'Eliminación de materia'),
        ('SUBJECT_VIEW', 'Visualización de materia'),
        
        # Cursos
        ('COURSE_CREATE', 'Creación de curso'),
        ('COURSE_UPDATE', 'Actualización de curso'),
        ('COURSE_DELETE', 'Eliminación de curso'),
        ('COURSE_VIEW', 'Visualización de curso'),
        
        # Grupos
        ('GROUP_CREATE', 'Creación de grupo'),
        ('GROUP_UPDATE', 'Actualización de grupo'),
        ('GROUP_DELETE', 'Eliminación de grupo'),
        ('GROUP_VIEW', 'Visualización de grupo'),
        
        # Clases
        ('CLASS_CREATE', 'Creación de clase'),
        ('CLASS_UPDATE', 'Actualización de clase'),
        ('CLASS_DELETE', 'Eliminación de clase'),
        ('CLASS_VIEW', 'Visualización de clase'),
        ('CLASS_ADD_STUDENT', 'Añadir estudiante a clase'),
        ('CLASS_REMOVE_STUDENT', 'Remover estudiante de clase'),
        ('CLASS_ADD_PERIOD', 'Añadir período a clase'),
        ('CLASS_REMOVE_PERIOD', 'Remover período de clase'),
        
        # Asistencia
        ('ATTENDANCE_CREATE', 'Registro de asistencia'),
        ('ATTENDANCE_UPDATE', 'Actualización de asistencia'),
        ('ATTENDANCE_DELETE', 'Eliminación de asistencia'),
        ('ATTENDANCE_BULK_CREATE', 'Registro masivo de asistencia'),
        ('ATTENDANCE_VIEW', 'Visualización de asistencia'),
        ('ATTENDANCE_STATS', 'Consulta de estadísticas de asistencia'),
        
        # Participación
        ('PARTICIPATION_CREATE', 'Registro de participación'),
        ('PARTICIPATION_UPDATE', 'Actualización de participación'),
        ('PARTICIPATION_DELETE', 'Eliminación de participación'),
        ('PARTICIPATION_BULK_CREATE', 'Registro masivo de participación'),
        ('PARTICIPATION_VIEW', 'Visualización de participación'),
        ('PARTICIPATION_STATS', 'Consulta de estadísticas de participación'),
        
        # Notas
        ('GRADE_CREATE', 'Registro de nota'),
        ('GRADE_UPDATE', 'Actualización de nota'),
        ('GRADE_DELETE', 'Eliminación de nota'),
        ('GRADE_BULK_CREATE', 'Registro masivo de notas'),
        ('GRADE_VIEW', 'Visualización de notas'),
        ('GRADE_STATS', 'Consulta de estadísticas de notas'),
        ('FINAL_GRADE_RECALCULATE', 'Recálculo de notas finales'),
        
        # Predicciones ML
        ('PREDICTION_CREATE', 'Creación de predicción'),
        ('PREDICTION_UPDATE', 'Actualización de predicción'),
        ('PREDICTION_VIEW', 'Visualización de predicción'),
        ('PREDICTION_RETRAIN', 'Reentrenamiento de modelo'),
        ('PREDICTION_BULK_UPDATE', 'Actualización masiva de predicciones'),
        ('PREDICTION_RETROSPECTIVE', 'Generación de predicciones retrospectivas'),
        
        # Sistema
        ('SYSTEM_ERROR', 'Error del sistema'),
        ('API_ACCESS', 'Acceso a API'),
        ('UNAUTHORIZED_ACCESS', 'Acceso no autorizado'),
    ]
    
    # Información del usuario
    user = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='audit_logs'
    )
    username = models.CharField(max_length=150, blank=True)  # Guardar username por si se elimina el usuario
    
    # Información de la acción
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    description = models.TextField(blank=True)
    
    # Información técnica
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    # Información temporal
    timestamp = models.DateTimeField(default=timezone.now)
    
    # Información del objeto afectado
    content_type = models.CharField(max_length=100, blank=True)  # Tipo de objeto (ej: 'Class', 'User')
    object_id = models.CharField(max_length=100, blank=True)     # ID del objeto afectado
    object_repr = models.CharField(max_length=200, blank=True)   # Representación del objeto
    
    # Datos adicionales (JSON)
    extra_data = models.JSONField(default=dict, blank=True)
    
    # Resultado de la acción
    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Registro de Auditoría'
        verbose_name_plural = 'Registros de Auditoría'
        indexes = [
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['action', '-timestamp']),
            models.Index(fields=['ip_address', '-timestamp']),
            models.Index(fields=['-timestamp']),
        ]
    
    def __str__(self):
        return f"{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')} - {self.username or 'Anonymous'} - {self.get_action_display()}"
    
    @classmethod
    def log_action(cls, user=None, action=None, description='', ip_address=None, 
                   user_agent='', object_type='', object_id='', object_repr='', 
                   extra_data=None, success=True, error_message=''):
        """
        Método de conveniencia para crear logs de auditoría
        """
        if extra_data is None:
            extra_data = {}
            
        return cls.objects.create(
            user=user,
            username=user.username if user else '',
            action=action,
            description=description,
            ip_address=ip_address,
            user_agent=user_agent,
            content_type=object_type,
            object_id=str(object_id) if object_id else '',
            object_repr=object_repr,
            extra_data=extra_data,
            success=success,
            error_message=error_message
        )


class AuditLogSummary(models.Model):
    """
    Resumen diario de logs de auditoría para reportes
    """
    date = models.DateField(unique=True)
    total_actions = models.IntegerField(default=0)
    unique_users = models.IntegerField(default=0)
    failed_actions = models.IntegerField(default=0)
    most_common_action = models.CharField(max_length=50, blank=True)
    most_active_user = models.CharField(max_length=150, blank=True)
    
    # Contadores por tipo de acción
    login_count = models.IntegerField(default=0)
    create_count = models.IntegerField(default=0)
    update_count = models.IntegerField(default=0)
    delete_count = models.IntegerField(default=0)
    view_count = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-date']
        verbose_name = 'Resumen de Auditoría'
        verbose_name_plural = 'Resúmenes de Auditoría'
    
    def __str__(self):
        return f"Resumen {self.date} - {self.total_actions} acciones"