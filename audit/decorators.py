# audit/decorators.py
from functools import wraps
import logging
from .signals import log_custom_action, set_audit_user

logger = logging.getLogger('audit')

def audit_action(action, description_template=None, object_getter=None):
    """
    Decorador para auditar acciones específicas en vistas
    
    Args:
        action: Tipo de acción (ej: 'GRADE_BULK_CREATE')
        description_template: Template para descripción (ej: 'Usuario {user} creó notas masivamente')
        object_getter: Función para obtener el objeto afectado desde los argumentos
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Establecer contexto de auditoría
            if hasattr(request, 'user') and request.user.is_authenticated:
                set_audit_user(request.user, request)
            
            # Ejecutar la vista original
            response = view_func(request, *args, **kwargs)
            
            try:
                # Determinar si la acción fue exitosa
                success = True
                error_message = ''
                
                if hasattr(response, 'status_code'):
                    success = response.status_code < 400
                    if not success and hasattr(response, 'data'):
                        error_message = str(response.data)[:500]
                
                # Generar descripción
                if description_template:
                    description = description_template.format(
                        user=request.user.username if hasattr(request, 'user') else 'Anónimo'
                    )
                else:
                    username = request.user.username if hasattr(request, 'user') and request.user.is_authenticated else 'Anónimo'
                    description = f"{username} ejecutó {action}"
                
                # Obtener objeto afectado si se especificó
                object_instance = None
                if object_getter and callable(object_getter):
                    try:
                        object_instance = object_getter(request, *args, **kwargs)
                    except Exception as e:
                        logger.warning(f"Error obteniendo objeto para auditoría: {str(e)}")
                
                # Crear datos extra
                extra_data = {
                    'view_name': view_func.__name__,
                    'method': request.method,
                    'path': request.path,
                    'args': args,
                    'kwargs': kwargs,
                }
                
                # Crear log de auditoría
                log_custom_action(
                    user=request.user if hasattr(request, 'user') and request.user.is_authenticated else None,
                    action=action,
                    description=description,
                    object_instance=object_instance,
                    extra_data=extra_data,
                    request=request
                )
                
            except Exception as e:
                logger.error(f"Error en decorador de auditoría: {str(e)}")
            
            return response
        
        return wrapper
    return decorator

def log_user_action(user, action, description, object_instance=None, extra_data=None, request=None):
    """
    Helper function para crear logs de auditoría desde cualquier parte del código
    
    Args:
        user: Usuario que realiza la acción
        action: Tipo de acción
        description: Descripción de la acción
        object_instance: Objeto afectado (opcional)
        extra_data: Datos adicionales (opcional)
        request: Request HTTP (opcional)
    """
    try:
        return log_custom_action(
            user=user,
            action=action,
            description=description,
            object_instance=object_instance,
            extra_data=extra_data or {},
            request=request
        )
    except Exception as e:
        logger.error(f"Error creando log de usuario: {str(e)}")
        return None

def track_model_changes(model_class, action_prefix=None):
    """
    Decorador de clase para trackear cambios en modelos específicos
    
    Args:
        model_class: Clase del modelo a trackear
        action_prefix: Prefijo para las acciones (ej: 'CUSTOM_MODEL')
    """
    def decorator(cls):
        original_save = model_class.save
        original_delete = model_class.delete
        
        def tracked_save(self, *args, **kwargs):
            # Determinar si es creación o actualización
            is_create = self.pk is None
            
            # Guardar el objeto
            result = original_save(self, *args, **kwargs)
            
            # Crear log
            action = f"{action_prefix or model_class.__name__.upper()}_{'CREATE' if is_create else 'UPDATE'}"
            description = f"{'Creación' if is_create else 'Actualización'} de {model_class.__name__}: {str(self)}"
            
            # Intentar obtener usuario del contexto
            from .signals import get_audit_user, get_audit_request
            user = get_audit_user()
            request = get_audit_request()
            
            log_custom_action(
                user=user,
                action=action,
                description=description,
                object_instance=self,
                request=request
            )
            
            return result
        
        def tracked_delete(self, *args, **kwargs):
            # Guardar información antes de eliminar
            object_repr = str(self)
            object_pk = self.pk
            
            # Eliminar el objeto
            result = original_delete(self, *args, **kwargs)
            
            # Crear log
            action = f"{action_prefix or model_class.__name__.upper()}_DELETE"
            description = f"Eliminación de {model_class.__name__}: {object_repr}"
            
            # Intentar obtener usuario del contexto
            from .signals import get_audit_user, get_audit_request
            user = get_audit_user()
            request = get_audit_request()
            
            log_custom_action(
                user=user,
                action=action,
                description=description,
                extra_data={
                    'deleted_object_pk': object_pk,
                    'deleted_object_repr': object_repr
                },
                request=request
            )
            
            return result
        
        # Reemplazar métodos
        model_class.save = tracked_save
        model_class.delete = tracked_delete
        
        return cls
    
    return decorator

# Context manager para establecer usuario de auditoría temporalmente
class audit_context:
    """
    Context manager para establecer el usuario de auditoría
    
    Uso:
        with audit_context(user, request):
            # Código que necesita auditoría
            model.save()
    """
    
    def __init__(self, user, request=None):
        self.user = user
        self.request = request
        self.previous_user = None
        self.previous_request = None
    
    def __enter__(self):
        from .signals import get_audit_user, get_audit_request, set_audit_user
        
        # Guardar contexto anterior
        self.previous_user = get_audit_user()
        self.previous_request = get_audit_request()
        
        # Establecer nuevo contexto
        set_audit_user(self.user, self.request)
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        from .signals import set_audit_user
        
        # Restaurar contexto anterior
        set_audit_user(self.previous_user, self.previous_request)