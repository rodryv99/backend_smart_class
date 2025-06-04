from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from grades.models import Grade
from .ml_service import MLPredictionService
import threading


def update_predictions_async(class_instance, student=None):
    """
    Función para actualizar predicciones en un hilo separado
    """
    try:
        ml_service = MLPredictionService(class_instance)
        
        if student:
            # Actualizar predicción solo para un estudiante específico
            ml_service.predict_next_period(student)
        else:
            # Actualizar predicciones para toda la clase
            ml_service.update_predictions_for_class()
    except Exception as e:
        print(f"Error en update_predictions_async: {str(e)}")


@receiver(post_save, sender=Grade)
def grade_saved_handler(sender, instance, created, **kwargs):
    """
    Signal que se ejecuta cuando se guarda una nota (nueva o modificada)
    """
    print(f"Signal: Nota {'creada' if created else 'actualizada'} para {instance.student.first_name} {instance.student.last_name}")
    
    try:
        ml_service = MLPredictionService(instance.class_instance)
        
        # Si es una nota nueva, crear historial si había predicción
        if created:
            ml_service.create_prediction_history(
                instance.student,
                instance.period,
                instance.nota_total
            )
        
        # Actualizar predicciones para este estudiante específico en un hilo separado
        # para no bloquear la respuesta HTTP
        thread = threading.Thread(
            target=update_predictions_async,
            args=(instance.class_instance, instance.student)
        )
        thread.daemon = True
        thread.start()
        
    except Exception as e:
        print(f"Error en grade_saved_handler: {str(e)}")


@receiver(post_delete, sender=Grade)
def grade_deleted_handler(sender, instance, **kwargs):
    """
    Signal que se ejecuta cuando se elimina una nota
    """
    print(f"Signal: Nota eliminada para {instance.student.first_name} {instance.student.last_name}")
    
    try:
        # Actualizar predicciones para este estudiante en un hilo separado
        thread = threading.Thread(
            target=update_predictions_async,
            args=(instance.class_instance, instance.student)
        )
        thread.daemon = True
        thread.start()
        
    except Exception as e:
        print(f"Error en grade_deleted_handler: {str(e)}")