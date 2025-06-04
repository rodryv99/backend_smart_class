# grades/signals.py
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db import transaction
from .models import Grade, FinalGrade
import logging
import time

logger = logging.getLogger(__name__)

print("DEBUG: grades/signals.py se está importando")

@receiver(post_save, sender=Grade)
def grade_saved_handler(sender, instance, created, **kwargs):
    """
    Signal que se ejecuta cuando se guarda una nota (nueva o modificada)
    Recalcula automáticamente las notas finales
    """
    action = 'creada' if created else 'actualizada'
    print(f"DEBUG GRADES SIGNAL: Nota {action} para {instance.student.first_name} {instance.student.last_name}")
    logger.info(f"Signal Grades: Nota {action} para {instance.student.first_name} {instance.student.last_name}")
    
    # Usar transaction.on_commit para asegurar que se ejecute después del commit
    def update_final_grade():
        try:
            # Pequeña pausa para asegurar que la transacción se complete
            time.sleep(0.1)
            
            # Obtener nota final anterior
            old_final = FinalGrade.objects.filter(
                student=instance.student, 
                class_instance=instance.class_instance
            ).first()
            
            old_value = old_final.nota_final if old_final else 0
            
            # Actualizar nota final del estudiante
            final_grade_value = FinalGrade.update_final_grade_for_student(
                instance.student, 
                instance.class_instance
            )
            
            print(f"DEBUG SIGNAL: Nota final cambió de {old_value} a {final_grade_value}")
            # CAMBIO CRÍTICO: Usar -> en lugar de → para evitar errores Unicode
            logger.info(f"Nota final recalculada para {instance.student.first_name} {instance.student.last_name}: {old_value} -> {final_grade_value}")
            
        except Exception as e:
            print(f"ERROR en grade_saved_handler: {str(e)}")
            logger.error(f"Error en grade_saved_handler: {str(e)}")
    
    # Ejecutar después del commit de la transacción
    transaction.on_commit(update_final_grade)


@receiver(post_delete, sender=Grade)
def grade_deleted_handler(sender, instance, **kwargs):
    """
    Signal que se ejecuta cuando se elimina una nota
    Recalcula automáticamente las notas finales
    """
    print(f"DEBUG GRADES SIGNAL: Nota eliminada para {instance.student.first_name} {instance.student.last_name}")
    logger.info(f"Signal Grades: Nota eliminada para {instance.student.first_name} {instance.student.last_name}")
    
    # Usar transaction.on_commit para asegurar que se ejecute después del commit
    def update_final_grade():
        try:
            # Pequeña pausa para asegurar que la transacción se complete
            time.sleep(0.1)
            
            # Actualizar nota final del estudiante automáticamente
            final_grade_value = FinalGrade.update_final_grade_for_student(
                instance.student, 
                instance.class_instance
            )
            
            print(f"DEBUG SIGNAL: Nota final recalculada después de eliminar: {final_grade_value}")
            logger.info(f"Nota final recalculada después de eliminar nota para {instance.student.first_name} {instance.student.last_name}: {final_grade_value}")
            
        except Exception as e:
            print(f"ERROR en grade_deleted_handler: {str(e)}")
            logger.error(f"Error en grade_deleted_handler: {str(e)}")
    
    # Ejecutar después del commit de la transacción
    transaction.on_commit(update_final_grade)

print("DEBUG: Signals de grades registrados con transaction.on_commit")