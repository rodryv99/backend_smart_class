from django.apps import AppConfig


class MlPredictionsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ml_predictions'
    verbose_name = 'Predicciones ML'
    
    def ready(self):
        # Importar signals cuando la app esté lista
        import ml_predictions.signals