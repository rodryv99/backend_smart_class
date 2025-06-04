# audit/apps.py
from django.apps import AppConfig

class AuditConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'audit'
    verbose_name = 'Auditoría'
    
    def ready(self):
        """
        Configurar señales y tareas cuando la app esté lista
        """
        import audit.signals  # Importar señales
        import audit.tasks    # Importar tareas