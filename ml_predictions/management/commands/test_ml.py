# ml_predictions/management/commands/test_ml.py
# Crear primero los directorios: ml_predictions/management/ y ml_predictions/management/commands/

from django.core.management.base import BaseCommand
from ml_predictions.ml_service import MLPredictionService
from academic.models import Class
from grades.models import Grade
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Prueba el sistema de Machine Learning para una clase específica'

    def add_arguments(self, parser):
        parser.add_argument(
            '--class_id',
            type=int,
            help='ID de la clase para probar (opcional, si no se proporciona usa la primera clase con datos)'
        )
        parser.add_argument(
            '--train_only',
            action='store_true',
            help='Solo entrenar el modelo sin hacer predicciones'
        )
        parser.add_argument(
            '--list_classes',
            action='store_true',
            help='Listar todas las clases disponibles con datos'
        )

    def handle(self, *args, **options):
        if options.get('list_classes'):
            self.list_classes_with_data()
            return

        class_id = options.get('class_id')
        train_only = options.get('train_only', False)

        try:
            # Si no se proporciona class_id, usar la primera clase con datos
            if class_id:
                class_instance = Class.objects.get(id=class_id)
            else:
                # Buscar una clase que tenga notas
                classes_with_grades = Class.objects.filter(grades__isnull=False).distinct()
                if not classes_with_grades.exists():
                    self.stdout.write(
                        self.style.ERROR('No hay clases con datos de notas en el sistema')
                    )
                    return
                
                class_instance = classes_with_grades.first()
                self.stdout.write(
                    self.style.WARNING(f'Usando la primera clase disponible: {class_instance.name} (ID: {class_instance.id})')
                )

            # Mostrar información de la clase
            grades_count = Grade.objects.filter(class_instance=class_instance).count()
            students_count = class_instance.students.count()
            
            self.stdout.write(
                self.style.SUCCESS(f'Probando ML para la clase: {class_instance.name}')
            )
            self.stdout.write(f'  - Estudiantes: {students_count}')
            self.stdout.write(f'  - Notas registradas: {grades_count}')
            self.stdout.write(f'  - Año: {class_instance.year}')

            # Crear servicio de ML
            ml_service = MLPredictionService(class_instance)

            # Entrenar modelo
            self.stdout.write('\n' + '='*50)
            self.stdout.write('ENTRENANDO MODELO...')
            self.stdout.write('='*50)
            
            ml_model = ml_service.train_model()

            if ml_model:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'\n✓ Modelo entrenado exitosamente!\n'
                        f'  - Versión: {ml_model.model_version}\n'
                        f'  - Algoritmo: {ml_model.algorithm}\n'
                        f'  - Score de validación: {ml_model.validation_score:.3f}\n'
                        f'  - Error absoluto medio: {ml_model.mean_absolute_error:.2f}\n'
                        f'  - Muestras de entrenamiento: {ml_model.training_samples}\n'
                        f'  - Archivo: {ml_model.model_file_path}'
                    )
                )

                if not train_only:
                    # Hacer predicciones
                    self.stdout.write('\n' + '='*50)
                    self.stdout.write('GENERANDO PREDICCIONES...')
                    self.stdout.write('='*50)
                    
                    predictions = ml_service.update_predictions_for_class()

                    if predictions:
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'\n✓ Predicciones generadas para {len(predictions)} estudiantes'
                            )
                        )

                        # Mostrar predicciones
                        self.stdout.write('\nDETALLE DE PREDICCIONES:')
                        self.stdout.write('-' * 80)
                        for prediction in predictions:
                            confidence_color = self.style.SUCCESS if prediction.confidence >= 80 else (
                                self.style.WARNING if prediction.confidence >= 60 else self.style.ERROR
                            )
                            
                            grade_indicator = "📈" if prediction.predicted_grade >= 75 else (
                                "📊" if prediction.predicted_grade >= 51 else "📉"
                            )
                            
                            self.stdout.write(
                                f'{grade_indicator} {prediction.student.first_name} {prediction.student.last_name}:\n'
                                f'    Nota predicha: {prediction.predicted_grade:.1f} puntos\n'
                                f'    Confianza: {confidence_color(f"{prediction.confidence:.1f}%")}\n'
                                f'    Período: {prediction.predicted_period}\n'
                                f'    Basado en: {prediction.avg_previous_grades:.1f} promedio anterior\n'
                                f'    Asistencia: {prediction.attendance_percentage:.1f}%\n'
                                f'    Participación: {prediction.participation_average:.1f}/3.0\n'
                            )
                    else:
                        self.stdout.write(
                            self.style.WARNING('No se generaron predicciones (los estudiantes pueden ya tener todos los períodos completados)')
                        )
            else:
                self.stdout.write(
                    self.style.ERROR('❌ No se pudo entrenar el modelo')
                )

        except Class.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'❌ Clase con ID {class_id} no encontrada')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Error durante la prueba: {str(e)}')
            )
            import traceback
            self.stdout.write(traceback.format_exc())

    def list_classes_with_data(self):
        """Lista todas las clases que tienen datos para ML"""
        self.stdout.write(
            self.style.SUCCESS('CLASES DISPONIBLES CON DATOS:')
        )
        self.stdout.write('='*70)
        
        classes_with_grades = Class.objects.filter(grades__isnull=False).distinct()
        
        if not classes_with_grades.exists():
            self.stdout.write(
                self.style.WARNING('No hay clases con datos de notas en el sistema')
            )
            return
        
        for class_instance in classes_with_grades:
            grades_count = Grade.objects.filter(class_instance=class_instance).count()
            students_count = class_instance.students.count()
            periods_count = class_instance.periods.count()
            
            self.stdout.write(
                f'ID: {class_instance.id:3d} | {class_instance.name}\n'
                f'      Año: {class_instance.year} | Estudiantes: {students_count:2d} | '
                f'Períodos: {periods_count} | Notas: {grades_count:3d}\n'
                f'      {class_instance.subject.name} - {class_instance.course.name} - {class_instance.group.name}\n'
            )
        
        self.stdout.write(
            f'\nUsa: python manage.py test_ml --class_id <ID> para probar una clase específica'
        )