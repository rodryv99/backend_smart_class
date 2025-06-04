# audit/signals.py
from django.db.models.signals import post_save, post_delete, pre_delete
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.apps import apps
import logging
import threading

from .models import AuditLog

User = get_user_model()
logger = logging.getLogger('audit')

# Variable local del hilo para almacenar el usuario actual
_audit_context = threading.local()

def get_client_ip(request):
    """
    Obtener IP del cliente
    """
    if not request:
        return None
    
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def set_audit_user(user, request=None):
    """
    Establecer el usuario actual para auditoría en el contexto del hilo
    """
    _audit_context.user = user
    _audit_context.request = request

def get_audit_user():
    """
    Obtener el usuario actual del contexto del hilo
    """
    return getattr(_audit_context, 'user', None)

def get_audit_request():
    """
    Obtener la request actual del contexto del hilo
    """
    return getattr(_audit_context, 'request', None)

@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    """
    Registrar inicio de sesión exitoso
    """
    try:
        # Establecer contexto de auditoría
        set_audit_user(user, request)
        
        AuditLog.log_action(
            user=user,
            action='LOGIN',
            description=f'Usuario {user.username} inició sesión exitosamente',
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            extra_data={
                'login_time': timezone.now().isoformat(),
                'user_type': getattr(user, 'user_type', 'unknown'),
                'session_key': request.session.session_key if hasattr(request, 'session') else None
            }
        )
        logger.info(f"Login exitoso registrado para usuario: {user.username}")
    except Exception as e:
        logger.error(f"Error logging user login: {str(e)}")

@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    """
    Registrar cierre de sesión
    """
    try:
        username = user.username if user else 'unknown'
        
        AuditLog.log_action(
            user=user,
            action='LOGOUT',
            description=f'Usuario {username} cerró sesión',
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            extra_data={
                'logout_time': timezone.now().isoformat(),
                'session_key': request.session.session_key if hasattr(request, 'session') else None
            }
        )
        logger.info(f"Logout registrado para usuario: {username}")
    except Exception as e:
        logger.error(f"Error logging user logout: {str(e)}")

@receiver(user_login_failed)
def log_user_login_failed(sender, credentials, request, **kwargs):
    """
    Registrar intento de inicio de sesión fallido
    """
    try:
        username = credentials.get('username', 'unknown')
        
        AuditLog.log_action(
            user=None,
            action='LOGIN_FAILED',
            description=f'Intento de inicio de sesión fallido para usuario: {username}',
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            extra_data={
                'attempted_username': username,
                'failure_time': timezone.now().isoformat(),
                'session_key': request.session.session_key if hasattr(request, 'session') else None
            },
            success=False,
            error_message='Credenciales inválidas'
        )
        logger.warning(f"Intento de login fallido registrado para usuario: {username} desde IP: {get_client_ip(request)}")
    except Exception as e:
        logger.error(f"Error logging failed login: {str(e)}")

# Diccionario para mapear modelos a acciones
MODEL_ACTION_MAP = {
    'User': 'USER',
    'TeacherProfile': 'TEACHER_PROFILE',
    'StudentProfile': 'STUDENT_PROFILE',
    'Period': 'PERIOD',
    'Subject': 'SUBJECT',
    'Course': 'COURSE',
    'Group': 'GROUP',
    'Class': 'CLASS',
    'Attendance': 'ATTENDANCE',
    'Participation': 'PARTICIPATION',
    'Grade': 'GRADE',
    'FinalGrade': 'FINAL_GRADE',
    'Prediction': 'PREDICTION',
    'PredictionHistory': 'PREDICTION_HISTORY',
}

# Modelos que NO queremos auditar automáticamente
EXCLUDED_MODELS = {
    'AuditLog',
    'AuditLogSummary',
    'Session',
    'ContentType',
    'Permission',
    'Group',  # Django Group, no nuestro modelo Group
    'LogEntry',
}

def should_audit_model(model_name, app_label):
    """
    Determinar si debemos auditar este modelo
    """
    # No auditar modelos excluidos
    if model_name in EXCLUDED_MODELS:
        return False
    
    # No auditar modelos de Django admin
    if app_label in ['admin', 'auth', 'contenttypes', 'sessions']:
        return False
    
    # Solo auditar nuestros modelos importantes
    return model_name in MODEL_ACTION_MAP

@receiver(post_save)
def log_model_save(sender, instance, created, **kwargs):
    """
    Registrar creación/actualización de modelos importantes
    """
    try:
        model_name = sender.__name__
        app_label = sender._meta.app_label
        
        # Verificar si debemos auditar este modelo
        if not should_audit_model(model_name, app_label):
            return
        
        action_prefix = MODEL_ACTION_MAP[model_name]
        action = f"{action_prefix}_CREATE" if created else f"{action_prefix}_UPDATE"
        
        # Obtener usuario actual del contexto
        user = get_audit_user()
        request = get_audit_request()
        
        # Obtener representación del objeto
        object_repr = get_object_repr(instance)
        
        description = f"{'Creación' if created else 'Actualización'} de {model_name}: {object_repr}"
        
        # Datos extra específicos por modelo
        extra_data = {
            'model': model_name,
            'app_label': app_label,
            'pk': str(instance.pk),
            'created': created
        }
        
        # Añadir campos específicos por modelo
        add_model_specific_data(instance, model_name, extra_data)
        
        # Obtener información de IP si hay request
        ip_address = get_client_ip(request) if request else None
        user_agent = request.META.get('HTTP_USER_AGENT', '') if request else ''
        
        AuditLog.log_action(
            user=user,
            action=action,
            description=description,
            ip_address=ip_address,
            user_agent=user_agent,
            object_type=model_name,
            object_id=str(instance.pk),
            object_repr=object_repr,
            extra_data=extra_data
        )
        
        logger.info(f"Audit log created: {action} for {model_name} ID {instance.pk}")
        
    except Exception as e:
        logger.error(f"Error logging model save for {sender.__name__}: {str(e)}")

@receiver(pre_delete)
def log_model_delete(sender, instance, **kwargs):
    """
    Registrar eliminación de modelos importantes (antes de eliminar)
    """
    try:
        model_name = sender.__name__
        app_label = sender._meta.app_label
        
        # Verificar si debemos auditar este modelo
        if not should_audit_model(model_name, app_label):
            return
        
        action = f"{MODEL_ACTION_MAP[model_name]}_DELETE"
        
        # Obtener usuario actual del contexto
        user = get_audit_user()
        request = get_audit_request()
        
        # Obtener representación del objeto antes de eliminarlo
        object_repr = get_object_repr(instance)
        
        description = f"Eliminación de {model_name}: {object_repr}"
        
        extra_data = {
            'model': model_name,
            'app_label': app_label,
            'pk': str(instance.pk),
            'deleted_object_repr': object_repr
        }
        
        # Guardar datos importantes antes de la eliminación
        add_model_specific_data(instance, model_name, extra_data)
        
        # Obtener información de IP si hay request
        ip_address = get_client_ip(request) if request else None
        user_agent = request.META.get('HTTP_USER_AGENT', '') if request else ''
        
        AuditLog.log_action(
            user=user,
            action=action,
            description=description,
            ip_address=ip_address,
            user_agent=user_agent,
            object_type=model_name,
            object_id=str(instance.pk),
            object_repr=object_repr,
            extra_data=extra_data
        )
        
        logger.info(f"Audit log created: {action} for {model_name} ID {instance.pk}")
        
    except Exception as e:
        logger.error(f"Error logging model delete for {sender.__name__}: {str(e)}")

def get_object_repr(instance):
    """
    Obtener representación legible del objeto
    """
    try:
        # Intentar diferentes métodos para obtener una buena representación
        if hasattr(instance, 'name') and instance.name:
            return str(instance.name)
        elif hasattr(instance, 'username') and instance.username:
            return str(instance.username)
        elif hasattr(instance, 'code') and instance.code:
            return str(instance.code)
        elif hasattr(instance, 'first_name') and hasattr(instance, 'last_name'):
            if instance.first_name and instance.last_name:
                return f"{instance.first_name} {instance.last_name}"
        elif hasattr(instance, 'title') and instance.title:
            return str(instance.title)
        else:
            # Fallback al método __str__ del modelo
            return str(instance)
    except Exception:
        # Si todo falla, usar la representación básica
        return f"{instance.__class__.__name__} #{instance.pk}"

def add_model_specific_data(instance, model_name, extra_data):
    """
    Añadir datos específicos según el tipo de modelo
    """
    try:
        if model_name == 'User':
            extra_data.update({
                'username': getattr(instance, 'username', ''),
                'user_type': getattr(instance, 'user_type', ''),
                'email': getattr(instance, 'email', ''),
                'is_active': getattr(instance, 'is_active', None),
                'is_staff': getattr(instance, 'is_staff', None),
            })
        
        elif model_name in ['TeacherProfile', 'StudentProfile']:
            extra_data.update({
                'first_name': getattr(instance, 'first_name', ''),
                'last_name': getattr(instance, 'last_name', ''),
                'ci': getattr(instance, 'ci', ''),
                'phone': getattr(instance, 'phone', ''),
                'user_id': getattr(instance, 'user_id', None),
            })
            
            if model_name == 'TeacherProfile':
                extra_data.update({
                    'teacher_code': getattr(instance, 'teacher_code', ''),
                })
            elif model_name == 'StudentProfile':
                extra_data.update({
                    'tutor_name': getattr(instance, 'tutor_name', ''),
                    'tutor_phone': getattr(instance, 'tutor_phone', ''),
                })
        
        elif model_name == 'Class':
            extra_data.update({
                'code': getattr(instance, 'code', ''),
                'name': getattr(instance, 'name', ''),
                'year': getattr(instance, 'year', ''),
                'subject_id': getattr(instance, 'subject_id', None),
                'course_id': getattr(instance, 'course_id', None),
                'group_id': getattr(instance, 'group_id', None),
                'teacher_id': getattr(instance, 'teacher_id', None),
            })
        
        elif model_name in ['Grade', 'Attendance', 'Participation']:
            extra_data.update({
                'student_id': getattr(instance, 'student_id', None),
                'class_id': getattr(instance, 'class_id', None),
                'period_id': getattr(instance, 'period_id', None),
                'date': str(getattr(instance, 'date', '')),
            })
            
            if model_name == 'Grade':
                extra_data.update({
                    'ser': getattr(instance, 'ser', None),
                    'saber': getattr(instance, 'saber', None),
                    'hacer': getattr(instance, 'hacer', None),
                    'decidir': getattr(instance, 'decidir', None),
                    'autoevaluacion': getattr(instance, 'autoevaluacion', None),
                    'nota': getattr(instance, 'nota', None),
                    'estado': getattr(instance, 'estado', ''),
                })
            elif model_name == 'Attendance':
                extra_data.update({
                    'status': getattr(instance, 'status', ''),
                })
            elif model_name == 'Participation':
                extra_data.update({
                    'level': getattr(instance, 'level', ''),
                })
        
        elif model_name in ['Period', 'Subject', 'Course', 'Group']:
            extra_data.update({
                'name': getattr(instance, 'name', ''),
                'code': getattr(instance, 'code', ''),
            })
            
            if model_name == 'Period':
                extra_data.update({
                    'period_type': getattr(instance, 'period_type', ''),
                    'number': getattr(instance, 'number', None),
                    'year': getattr(instance, 'year', None),
                    'start_date': str(getattr(instance, 'start_date', '')),
                    'end_date': str(getattr(instance, 'end_date', '')),
                })
        
        elif model_name in ['Prediction', 'PredictionHistory']:
            extra_data.update({
                'student_id': getattr(instance, 'student_id', None),
                'class_id': getattr(instance, 'class_id', None),
                'predicted_grade': getattr(instance, 'predicted_grade', None),
                'confidence': getattr(instance, 'confidence', None),
            })
        
    except Exception as e:
        logger.error(f"Error adding model-specific data for {model_name}: {str(e)}")

def log_custom_action(user, action, description, object_instance=None, extra_data=None, request=None):
    """
    Función helper para crear logs de auditoría personalizados desde las vistas
    """
    try:
        if extra_data is None:
            extra_data = {}
        
        object_type = ''
        object_id = ''
        object_repr = ''
        
        if object_instance:
            object_type = object_instance.__class__.__name__
            object_id = str(object_instance.pk) if hasattr(object_instance, 'pk') else ''
            object_repr = get_object_repr(object_instance)
        
        ip_address = get_client_ip(request) if request else None
        user_agent = request.META.get('HTTP_USER_AGENT', '') if request else ''
        
        return AuditLog.log_action(
            user=user,
            action=action,
            description=description,
            ip_address=ip_address,
            user_agent=user_agent,
            object_type=object_type,
            object_id=object_id,
            object_repr=object_repr,
            extra_data=extra_data
        )
    except Exception as e:
        logger.error(f"Error creating custom audit log: {str(e)}")
        return None