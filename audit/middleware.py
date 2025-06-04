# audit/middleware.py
import json
import logging
from django.utils.deprecation import MiddlewareMixin
from django.contrib.auth import get_user_model
from .models import AuditLog
from .signals import set_audit_user, log_custom_action

logger = logging.getLogger('audit')

class AuditMiddleware(MiddlewareMixin):
    """
    Middleware para capturar automáticamente acciones de auditoría
    """
    
    # Rutas que queremos auditar
    AUDIT_PATHS = [
        '/api/users/',
        '/api/academic/',
        '/api/grades/',
        '/api/ml/',
    ]
    
    # Acciones que NO queremos auditar (para evitar spam)
    SKIP_PATHS = [
        '/api/users/token/refresh/',
        '/api/audit/',  # Evitar recursión
        '/admin/jsi18n/',
        '/static/',
        '/media/',
        '/favicon.ico',
    ]
    
    # Mapeo de métodos HTTP a acciones
    METHOD_ACTION_MAP = {
        'POST': 'CREATE',
        'PUT': 'UPDATE',
        'PATCH': 'UPDATE',
        'DELETE': 'DELETE',
        'GET': 'VIEW'
    }
    
    def __init__(self, get_response):
        self.get_response = get_response
        super().__init__(get_response)
    
    def process_request(self, request):
        """
        Preparar datos para auditoría antes de procesar la request
        """
        try:
            # Obtener IP del cliente
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip = x_forwarded_for.split(',')[0].strip()
            else:
                ip = request.META.get('REMOTE_ADDR')
            
            # Guardar información en request para usar después
            request.audit_ip = ip
            request.audit_user_agent = request.META.get('HTTP_USER_AGENT', '')
            request.audit_method = request.method
            request.audit_path = request.path
            
            # Establecer contexto de auditoría si hay usuario autenticado
            if hasattr(request, 'user') and request.user.is_authenticated:
                set_audit_user(request.user, request)
            
        except Exception as e:
            logger.error(f"Error en process_request de AuditMiddleware: {str(e)}")
        
        return None
    
    def process_response(self, request, response):
        """
        Procesar respuesta y crear log de auditoría si es necesario
        """
        try:
            # Verificar si debemos auditar esta ruta
            if not self._should_audit(request.path):
                return response
            
            # Solo auditar si la respuesta fue exitosa o si hubo errores importantes
            if response.status_code >= 400 or self._is_important_action(request):
                self._create_audit_log(request, response)
                
        except Exception as e:
            logger.error(f"Error en process_response de AuditMiddleware: {str(e)}")
            # No interrumpir el flujo normal aunque falle la auditoría
        
        return response
    
    def _should_audit(self, path):
        """
        Determinar si debemos auditar esta ruta
        """
        # Saltar rutas específicas
        for skip_path in self.SKIP_PATHS:
            if path.startswith(skip_path):
                return False
        
        # Auditar solo rutas específicas
        for audit_path in self.AUDIT_PATHS:
            if path.startswith(audit_path):
                return True
        
        return False
    
    def _is_important_action(self, request):
        """
        Determinar si es una acción importante que debemos auditar
        """
        # Auditar todas las acciones de modificación
        if request.method in ['POST', 'PUT', 'PATCH', 'DELETE']:
            return True
        
        # Auditar algunos GETs importantes
        important_get_paths = [
            '/api/users/users/',  # Lista de usuarios
            '/api/grades/grades/stats/',  # Estadísticas
            '/api/ml/predictions/',  # Predicciones
            '/api/academic/classes/',  # Lista de clases
        ]
        
        for important_path in important_get_paths:
            if request.path.startswith(important_path):
                return True
        
        return False
    
    def _create_audit_log(self, request, response):
        """
        Crear el log de auditoría
        """
        try:
            # Determinar la acción basada en la ruta y método
            action = self._determine_action(request.path, request.method)
            
            # Obtener usuario
            user = request.user if hasattr(request, 'user') and request.user.is_authenticated else None
            
            # Determinar si fue exitoso
            success = response.status_code < 400
            
            # Preparar datos extra
            extra_data = {
                'method': request.method,
                'path': request.path,
                'status_code': response.status_code,
                'query_params': dict(request.GET) if request.GET else {},
            }
            
            # Añadir datos del body para POST/PUT (cuidado con datos sensibles)
            if request.method in ['POST', 'PUT', 'PATCH'] and hasattr(request, 'body'):
                try:
                    if request.content_type == 'application/json' and request.body:
                        body_data = json.loads(request.body.decode('utf-8'))
                        # Filtrar datos sensibles
                        filtered_body = self._filter_sensitive_data(body_data)
                        extra_data['request_data'] = filtered_body
                except (json.JSONDecodeError, UnicodeDecodeError):
                    # Si no podemos parsear el body, no es crítico
                    extra_data['request_data_error'] = 'No se pudo parsear el body de la request'
            
            # Obtener información del objeto afectado
            object_info = self._extract_object_info(request.path, extra_data.get('request_data', {}))
            
            # Crear descripción
            description = self._generate_description(action, request.path, user, success)
            
            # Error message si hay error
            error_message = ''
            if not success:
                if hasattr(response, 'data'):
                    error_message = str(response.data)[:500]  # Limitar longitud
                else:
                    error_message = f"HTTP {response.status_code}"
            
            # Crear el log
            AuditLog.log_action(
                user=user,
                action=action,
                description=description,
                ip_address=getattr(request, 'audit_ip', None),
                user_agent=getattr(request, 'audit_user_agent', ''),
                object_type=object_info.get('type', ''),
                object_id=object_info.get('id', ''),
                object_repr=object_info.get('repr', ''),
                extra_data=extra_data,
                success=success,
                error_message=error_message
            )
            
        except Exception as e:
            logger.error(f"Error creando audit log: {str(e)}")
    
    def _determine_action(self, path, method):
        """
        Determinar la acción específica basada en la ruta y método
        """
        # Mapeo específico de rutas
        route_mappings = {
            '/api/users/login/': 'LOGIN',
            '/api/users/register/student/': 'STUDENT_PROFILE_CREATE',
            '/api/users/register/teacher/': 'TEACHER_PROFILE_CREATE',
        }
        
        # Buscar mapeo exacto primero
        for route, action in route_mappings.items():
            if path.startswith(route):
                return action
        
        # Mapeo por patrones específicos
        if '/add_students/' in path:
            return 'CLASS_ADD_STUDENT'
        elif '/remove_students/' in path:
            return 'CLASS_REMOVE_STUDENT'
        elif '/add_periods/' in path:
            return 'CLASS_ADD_PERIOD'
        elif '/remove_periods/' in path:
            return 'CLASS_REMOVE_PERIOD'
        elif '/bulk_create/' in path:
            if 'attendance' in path:
                return 'ATTENDANCE_BULK_CREATE'
            elif 'participation' in path:
                return 'PARTICIPATION_BULK_CREATE'
            elif 'grades' in path:
                return 'GRADE_BULK_CREATE'
        elif '/stats/' in path:
            if 'attendance' in path:
                return 'ATTENDANCE_STATS'
            elif 'participation' in path:
                return 'PARTICIPATION_STATS'
            elif 'grades' in path:
                return 'GRADE_STATS'
        elif '/recalculate/' in path:
            return 'FINAL_GRADE_RECALCULATE'
        elif '/retrain_model/' in path:
            return 'PREDICTION_RETRAIN'
        
        # Mapeo genérico por tipo de recurso
        if '/api/academic/periods/' in path:
            return f'PERIOD_{self.METHOD_ACTION_MAP.get(method, "VIEW")}'
        elif '/api/academic/subjects/' in path:
            return f'SUBJECT_{self.METHOD_ACTION_MAP.get(method, "VIEW")}'
        elif '/api/academic/courses/' in path:
            return f'COURSE_{self.METHOD_ACTION_MAP.get(method, "VIEW")}'
        elif '/api/academic/groups/' in path:
            return f'GROUP_{self.METHOD_ACTION_MAP.get(method, "VIEW")}'
        elif '/api/academic/classes/' in path:
            return f'CLASS_{self.METHOD_ACTION_MAP.get(method, "VIEW")}'
        elif '/api/academic/attendances/' in path:
            return f'ATTENDANCE_{self.METHOD_ACTION_MAP.get(method, "VIEW")}'
        elif '/api/academic/participations/' in path:
            return f'PARTICIPATION_{self.METHOD_ACTION_MAP.get(method, "VIEW")}'
        elif '/api/grades/grades/' in path:
            return f'GRADE_{self.METHOD_ACTION_MAP.get(method, "VIEW")}'
        elif '/api/ml/predictions/' in path:
            return f'PREDICTION_{self.METHOD_ACTION_MAP.get(method, "VIEW")}'
        elif '/api/users/users/' in path:
            return f'USER_{self.METHOD_ACTION_MAP.get(method, "VIEW")}'
        
        # Default
        return f'API_ACCESS_{method}'
    
    def _filter_sensitive_data(self, data):
        """
        Filtrar datos sensibles del body de la request
        """
        if not isinstance(data, dict):
            return data
        
        sensitive_fields = ['password', 'token', 'secret', 'key', 'auth', 'csrf']
        filtered_data = data.copy()
        
        for field in sensitive_fields:
            for key in list(filtered_data.keys()):
                if field.lower() in key.lower():
                    filtered_data[key] = '[FILTERED]'
        
        return filtered_data
    
    def _extract_object_info(self, path, request_data):
        """
        Extraer información del objeto afectado
        """
        info = {'type': '', 'id': '', 'repr': ''}
        
        # Extraer ID de la URL
        path_parts = path.strip('/').split('/')
        
        # Mapeo de rutas a tipos de objeto
        if '/users/' in path:
            info['type'] = 'User'
        elif '/periods/' in path:
            info['type'] = 'Period'
        elif '/subjects/' in path:
            info['type'] = 'Subject'
        elif '/courses/' in path:
            info['type'] = 'Course'
        elif '/groups/' in path:
            info['type'] = 'Group'
        elif '/classes/' in path:
            info['type'] = 'Class'
        elif '/attendances/' in path:
            info['type'] = 'Attendance'
        elif '/participations/' in path:
            info['type'] = 'Participation'
        elif '/grades/' in path:
            info['type'] = 'Grade'
        elif '/predictions/' in path:
            info['type'] = 'Prediction'
        
        # Extraer ID si está en la URL
        try:
            for part in path_parts:
                if part.isdigit():
                    info['id'] = part
                    break
        except:
            pass
        
        # Extraer representación de los datos de request
        if request_data and isinstance(request_data, dict):
            if 'name' in request_data:
                info['repr'] = str(request_data['name'])
            elif 'code' in request_data:
                info['repr'] = str(request_data['code'])
            elif 'username' in request_data:
                info['repr'] = str(request_data['username'])
            elif 'first_name' in request_data and 'last_name' in request_data:
                info['repr'] = f"{request_data['first_name']} {request_data['last_name']}"
        
        return info
    
    def _generate_description(self, action, path, user, success):
        """
        Generar descripción legible de la acción
        """
        username = user.username if user else 'Usuario anónimo'
        status = 'exitosamente' if success else 'con error'
        
        # Generar descripción más legible según la acción
        action_descriptions = {
            'LOGIN': f"{username} inició sesión {status}",
            'USER_CREATE': f"{username} creó un usuario {status}",
            'USER_UPDATE': f"{username} actualizó un usuario {status}",
            'USER_DELETE': f"{username} eliminó un usuario {status}",
            'CLASS_CREATE': f"{username} creó una clase {status}",
            'CLASS_UPDATE': f"{username} actualizó una clase {status}",
            'CLASS_DELETE': f"{username} eliminó una clase {status}",
            'CLASS_ADD_STUDENT': f"{username} añadió estudiante(s) a una clase {status}",
            'CLASS_REMOVE_STUDENT': f"{username} removió estudiante(s) de una clase {status}",
            'GRADE_CREATE': f"{username} registró una nota {status}",
            'GRADE_BULK_CREATE': f"{username} registró notas masivamente {status}",
            'ATTENDANCE_CREATE': f"{username} registró asistencia {status}",
            'ATTENDANCE_BULK_CREATE': f"{username} registró asistencia masivamente {status}",
            'PARTICIPATION_CREATE': f"{username} registró participación {status}",
            'PARTICIPATION_BULK_CREATE': f"{username} registró participación masivamente {status}",
            'PREDICTION_UPDATE': f"{username} actualizó predicciones {status}",
            'PREDICTION_RETRAIN': f"{username} reentrenó el modelo de predicciones {status}",
        }
        
        if action in action_descriptions:
            return action_descriptions[action]
        else:
            return f"{username} ejecutó {action} en {path} {status}"