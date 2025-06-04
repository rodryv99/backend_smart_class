from django.apps import AppConfig


class GradesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'grades'
    verbose_name = 'Notas y Calificaciones'
    
    def ready(self):
        # Importar signals para activarlos
        try:
            import ml_predictions.signals
        except ImportError:
            # Si la app ml_predictions no está disponible, continuar sin error
            pass