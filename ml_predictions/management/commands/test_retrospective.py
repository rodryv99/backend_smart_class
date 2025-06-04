# ml_predictions/management/commands/test_retrospective.py

from django.core.management.base import BaseCommand
from ml_predictions.ml_service import MLPredictionService
from academic.models import Class, Period
from grades.models import Grade
from ml_predictions.models import PredictionHistory
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Prueba las predicciones retrospectivas del sistema de ML'

    def add_arguments(self, parser):
        parser.add_argument(
            '--class_id',
            type=int,
            help='ID de la clase para probar (opcional, si no se proporciona usa clases de 2024)'
        )
        parser.add_argument(
            '--period_number',
            type=int,
            default=3,
            help='Número del período a predecir retrospectivamente (por defecto: 3)'
        )
        parser.add_argument(
            '--year',
            type=int,
            default=2024,
            help='Año de las clases a probar (por defecto: 2024)'
        )

    def handle(self, *args, **options):
        class_id = options.get('class_id')
        period_number = options.get('period_number', 3)
        year = options.get('year', 2024)

        try:
            if class_id:
                # Probar clase específica
                class_instance = Class.objects.get(id=class_id)
                self.test_retrospective_for_class(class_instance, period_number)
            else:
                # Probar todas las clases del año especificado que tengan datos completos
                classes_to_test = Class.objects.filter(
                    year=year,
                    grades__isnull=False
                ).distinct()
                
                if not classes_to_test.exists():
                    self.stdout.write(
                        self.style.ERROR(f'No hay clases del año {year} con datos')
                    )
                    return
                
                self.stdout.write(
                    self.style.SUCCESS(f'Probando predicciones retrospectivas para {classes_to_test.count()} clases del año {year}')
                )
                
                for class_instance in classes_to_test[:5]:  # Probar solo las primeras 5
                    self.test_retrospective_for_class(class_instance, period_number)
                    self.stdout.write('-' * 80)

        except Class.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'Clase con ID {class_id} no encontrada')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error durante la prueba: {str(e)}')
            )
            import traceback
            self.stdout.write(traceback.format_exc())

    def test_retrospective_for_class(self, class_instance, period_number):
        """Prueba predicciones retrospectivas para una clase específica"""
        
        self.stdout.write(
            self.style.SUCCESS(f'\n📊 PROBANDO: {class_instance.name} (ID: {class_instance.id})')
        )
        
        # Verificar que la clase tiene el período solicitado
        target_period = class_instance.periods.filter(number=period_number).first()
        
        if not target_period:
            self.stdout.write(
                self.style.WARNING(f'❌ La clase no tiene período número {period_number}')
            )
            return
        
        # Verificar que hay notas en el período objetivo
        target_grades = Grade.objects.filter(
            class_instance=class_instance,
            period=target_period
        )
        
        if not target_grades.exists():
            self.stdout.write(
                self.style.WARNING(f'❌ No hay notas en el período {period_number} para comparar')
            )
            return
        
        self.stdout.write(f'✅ Período objetivo: {target_period} ({target_grades.count()} notas reales)')
        
        # Verificar que hay notas en períodos anteriores
        previous_periods = class_instance.periods.filter(number__lt=period_number)
        previous_grades = Grade.objects.filter(
            class_instance=class_instance,
            period__in=previous_periods
        )
        
        if not previous_grades.exists():
            self.stdout.write(
                self.style.WARNING(f'❌ No hay notas en períodos anteriores para entrenar')
            )
            return
        
        self.stdout.write(f'✅ Períodos de entrenamiento: {previous_periods.count()} períodos, {previous_grades.count()} notas')
        
        # Crear servicio ML y generar predicciones retrospectivas
        try:
            ml_service = MLPredictionService(class_instance)
            
            self.stdout.write('\n🤖 Generando predicciones retrospectivas...')
            predictions = ml_service.generate_retrospective_predictions(target_period)
            
            if not predictions:
                self.stdout.write(
                    self.style.WARNING('❌ No se generaron predicciones')
                )
                return
            
            self.stdout.write(
                self.style.SUCCESS(f'✅ Se generaron {len(predictions)} predicciones retrospectivas')
            )
            
            # Crear comparaciones con la realidad
            self.stdout.write('\n📈 Creando comparaciones con la realidad...')
            comparisons_created = 0
            total_error = 0
            
            for prediction in predictions:
                # Buscar la nota real
                real_grade = Grade.objects.filter(
                    student=prediction.student,
                    class_instance=class_instance,
                    period=target_period
                ).first()
                
                if real_grade:
                    # Crear historial de comparación
                    history = ml_service.create_prediction_history(
                        prediction.student,
                        target_period,
                        real_grade.nota_total
                    )
                    
                    if history:
                        comparisons_created += 1
                        total_error += history.absolute_error
                        
                        # Mostrar comparación individual
                        accuracy = 100 - min(100, (history.absolute_error / real_grade.nota_total) * 100) if real_grade.nota_total > 0 else 0
                        
                        color = self.style.SUCCESS if history.absolute_error <= 5 else (
                            self.style.WARNING if history.absolute_error <= 10 else self.style.ERROR
                        )
                        
                        self.stdout.write(
                            f'  📊 {prediction.student.first_name} {prediction.student.last_name}:\n'
                            f'      Predicción: {history.predicted_grade:.1f} | '
                            f'      Realidad: {history.actual_grade:.1f} | '
                            f'      Error: {color(f"±{history.absolute_error:.1f}")} | '
                            f'      Precisión: {accuracy:.1f}%'
                        )
            
            # Mostrar estadísticas finales
            if comparisons_created > 0:
                avg_error = total_error / comparisons_created
                self.stdout.write(
                    self.style.SUCCESS(
                        f'\n📋 RESUMEN DE PRECISIÓN:\n'
                        f'   Comparaciones creadas: {comparisons_created}\n'
                        f'   Error promedio: ±{avg_error:.2f} puntos\n'
                        f'   Precisión general: {100 - min(100, avg_error):.1f}%'
                    )
                )
                
                # Mostrar calidad de predicciones
                excellent = sum(1 for p in PredictionHistory.objects.filter(
                    class_instance=class_instance, period=target_period, absolute_error__lte=5
                ))
                good = sum(1 for p in PredictionHistory.objects.filter(
                    class_instance=class_instance, period=target_period, 
                    absolute_error__lte=10, absolute_error__gt=5
                ))
                poor = sum(1 for p in PredictionHistory.objects.filter(
                    class_instance=class_instance, period=target_period, absolute_error__gt=15
                ))
                
                self.stdout.write(
                    f'   Calidad de predicciones:\n'
                    f'     🟢 Excelentes (≤5 pts): {excellent}\n'
                    f'     🟡 Buenas (≤10 pts): {good}\n'
                    f'     🔴 Pobres (>15 pts): {poor}'
                )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Error generando predicciones retrospectivas: {str(e)}')
            )
            import traceback
            self.stdout.write(traceback.format_exc())