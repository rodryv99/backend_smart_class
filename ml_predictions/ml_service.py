import os
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import mean_absolute_error, r2_score
import joblib
from django.conf import settings
from django.db.models import Avg, Count
from django.db import transaction
from datetime import datetime, timedelta
import random
import logging

from .models import Prediction, PredictionHistory, MLModel
from grades.models import Grade
from academic.models import Attendance, Participation, Period

# Configurar logging
logger = logging.getLogger(__name__)

class MLPredictionService:
    """
    Servicio principal para manejar predicciones de notas usando Machine Learning
    """
    
    def __init__(self, class_instance):
        self.class_instance = class_instance
        self.model_dir = os.path.join(settings.BASE_DIR, 'ml_models')
        os.makedirs(self.model_dir, exist_ok=True)
    
    def generate_synthetic_data(self, num_samples=200):
        """
        Genera datos sintéticos realistas para entrenar el modelo
        basándose en patrones educativos reales
        """
        synthetic_data = []
        
        for _ in range(num_samples):
            # Simular patrones realistas
            base_performance = random.uniform(0.3, 0.95)  # Rendimiento base del estudiante
            
            # Generar asistencia (correlacionada con rendimiento)
            attendance = max(0.4, min(1.0, base_performance + np.random.normal(0, 0.1)))
            attendance_pct = attendance * 100
            
            # Generar participación (correlacionada con rendimiento y asistencia)
            participation_base = (base_performance + attendance) / 2
            participation = max(1.0, min(3.0, participation_base * 3 + np.random.normal(0, 0.3)))
            
            # Generar notas anteriores (ser, saber, hacer, decidir, autoevaluacion)
            noise = np.random.normal(0, 0.05)
            performance_with_noise = max(0.2, min(0.95, base_performance + noise))
            
            ser = performance_with_noise * 5
            saber = performance_with_noise * 45
            hacer = performance_with_noise * 40
            decidir = performance_with_noise * 5
            autoevaluacion = max(0, min(5, performance_with_noise * 5 + np.random.normal(0, 0.5)))
            
            avg_previous_grade = ser + saber + hacer + decidir + autoevaluacion
            
            # Generar nota objetivo (con algo de variación natural)
            # La nota futura depende del rendimiento histórico pero con variación
            trend = random.uniform(-0.05, 0.05)  # Tendencia de mejora/empeoramiento
            target_performance = max(0.2, min(0.95, base_performance + trend + np.random.normal(0, 0.03)))
            
            target_grade = target_performance * 100
            
            # Añadir algunos casos extremos para robustez
            if random.random() < 0.05:  # 5% de casos extremos
                if random.random() < 0.5:
                    target_grade = max(target_grade - 20, 20)  # Caída brusca
                else:
                    target_grade = min(target_grade + 15, 95)   # Mejora notable
            
            synthetic_data.append({
                'avg_previous_grades': avg_previous_grade,
                'attendance_percentage': attendance_pct,
                'participation_average': participation,
                'target_grade': target_grade
            })
        
        return pd.DataFrame(synthetic_data)
    
    def collect_student_data(self, student):
        """
        Recolecta datos históricos de un estudiante para hacer predicciones
        """
        try:
            # Obtener todas las notas del estudiante en esta clase
            grades = Grade.objects.filter(
                student=student,
                class_instance=self.class_instance
            ).order_by('period__period_type', 'period__number')
            
            if not grades.exists():
                logger.warning(f"No hay notas para el estudiante {student.first_name} {student.last_name}")
                return None
            
            # Calcular promedio de notas anteriores
            avg_previous_grades = grades.aggregate(avg=Avg('nota_total'))['avg'] or 0
            
            # Calcular porcentaje de asistencia promedio
            attendances = Attendance.objects.filter(
                student=student,
                class_instance=self.class_instance
            )
            
            if attendances.exists():
                total_days = attendances.count()
                present_days = attendances.filter(status__in=['presente', 'tardanza']).count()
                attendance_percentage = (present_days / total_days) * 100 if total_days > 0 else 0
            else:
                attendance_percentage = 85  # Valor por defecto
            
            # Calcular promedio de participación
            participations = Participation.objects.filter(
                student=student,
                class_instance=self.class_instance
            )
            
            if participations.exists():
                # Convertir niveles a números: alta=3, media=2, baja=1
                participation_scores = []
                for p in participations:
                    if p.level in ['alta', 'high']:
                        participation_scores.append(3)
                    elif p.level in ['media', 'medium']:
                        participation_scores.append(2)
                    else:
                        participation_scores.append(1)
                
                participation_average = sum(participation_scores) / len(participation_scores)
            else:
                participation_average = 2.0  # Valor por defecto (media)
            
            return {
                'avg_previous_grades': avg_previous_grades,
                'attendance_percentage': attendance_percentage,
                'participation_average': participation_average,
                'grades_count': grades.count()
            }
            
        except Exception as e:
            logger.error(f"Error collecting student data for {student.first_name} {student.last_name}: {str(e)}")
            return None
    
    def prepare_training_data(self):
        """
        Prepara datos de entrenamiento combinando datos reales y sintéticos
        """
        real_data = []
        
        try:
            # Obtener datos reales de la clase usando SQL más eficiente
            grades_queryset = Grade.objects.filter(
                class_instance=self.class_instance
            ).select_related('student', 'period').order_by(
                'student__id', 'period__period_type', 'period__number'
            )
            
            # Agrupar por estudiante de manera más eficiente
            current_student_id = None
            current_student_grades = []
            
            for grade in grades_queryset:
                if current_student_id != grade.student_id:
                    # Procesar el estudiante anterior si tenía suficientes datos
                    if current_student_id is not None and len(current_student_grades) >= 2:
                        self._process_student_for_training(current_student_grades, real_data)
                    
                    # Iniciar nuevo estudiante
                    current_student_id = grade.student_id
                    current_student_grades = [grade]
                else:
                    current_student_grades.append(grade)
            
            # Procesar el último estudiante
            if current_student_id is not None and len(current_student_grades) >= 2:
                self._process_student_for_training(current_student_grades, real_data)
            
            # Convertir datos reales a DataFrame
            real_df = pd.DataFrame(real_data) if real_data else pd.DataFrame()
            
            # Generar datos sintéticos
            synthetic_df = self.generate_synthetic_data(150)
            
            # Combinar datos reales y sintéticos
            if not real_df.empty:
                combined_df = pd.concat([real_df, synthetic_df], ignore_index=True)
                logger.info(f"Datos combinados: {len(real_df)} reales + {len(synthetic_df)} sintéticos = {len(combined_df)} total")
            else:
                combined_df = synthetic_df
                logger.info(f"Solo datos sintéticos: {len(synthetic_df)} muestras")
            
            return combined_df
            
        except Exception as e:
            logger.error(f"Error preparing training data: {str(e)}")
            # En caso de error, devolver solo datos sintéticos
            return self.generate_synthetic_data(150)
    
    def _process_student_for_training(self, student_grades, real_data):
        """
        Procesa las notas de un estudiante para datos de entrenamiento
        """
        try:
            # Usar los primeros N-1 períodos para predecir el último
            training_grades = student_grades[:-1]  # Todos menos el último
            target_grade = student_grades[-1]  # El último
            
            # Calcular características de entrenamiento
            avg_grades = sum(g.nota_total for g in training_grades) / len(training_grades)
            
            # Obtener student_id y periods para consultas
            student_id = training_grades[0].student_id
            training_period_ids = [g.period_id for g in training_grades]
            
            # Calcular asistencia
            attendances = Attendance.objects.filter(
                student_id=student_id,
                class_instance=self.class_instance,
                period_id__in=training_period_ids
            )
            
            if attendances.exists():
                total_days = attendances.count()
                present_days = attendances.filter(status__in=['presente', 'tardanza']).count()
                attendance_pct = (present_days / total_days) * 100
            else:
                attendance_pct = 85
            
            # Calcular participación
            participations = Participation.objects.filter(
                student_id=student_id,
                class_instance=self.class_instance,
                period_id__in=training_period_ids
            )
            
            if participations.exists():
                participation_scores = []
                for p in participations:
                    if p.level in ['alta', 'high']:
                        participation_scores.append(3)
                    elif p.level in ['media', 'medium']:
                        participation_scores.append(2)
                    else:
                        participation_scores.append(1)
                participation_avg = sum(participation_scores) / len(participation_scores)
            else:
                participation_avg = 2.0
            
            real_data.append({
                'avg_previous_grades': avg_grades,
                'attendance_percentage': attendance_pct,
                'participation_average': participation_avg,
                'target_grade': target_grade.nota_total
            })
            
        except Exception as e:
            logger.error(f"Error processing student for training: {str(e)}")
    
    @transaction.atomic
    def train_model(self):
        """
        Entrena un nuevo modelo con los datos disponibles
        """
        try:
            logger.info(f"Entrenando modelo para la clase: {self.class_instance.name}")
            
            # Preparar datos de entrenamiento
            training_data = self.prepare_training_data()
            
            if len(training_data) < 20:
                logger.warning("No hay suficientes datos para entrenar el modelo")
                return None
            
            # Preparar características (X) y objetivo (y)
            feature_columns = ['avg_previous_grades', 'attendance_percentage', 'participation_average']
            X = training_data[feature_columns]
            y = training_data['target_grade']
            
            # Validar que no hay valores NaN
            if X.isnull().any().any() or y.isnull().any():
                logger.warning("Hay valores NaN en los datos, rellenando con valores por defecto")
                X = X.fillna(X.mean())
                y = y.fillna(y.mean())
            
            # Dividir datos para entrenamiento y validación
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42
            )
            
            # Entrenar modelo Random Forest
            model = RandomForestRegressor(
                n_estimators=100,
                max_depth=10,
                min_samples_split=5,
                min_samples_leaf=2,
                random_state=42
            )
            
            model.fit(X_train, y_train)
            
            # Evaluar modelo
            train_score = model.score(X_train, y_train)
            val_score = model.score(X_test, y_test)
            
            y_pred = model.predict(X_test)
            mae = mean_absolute_error(y_test, y_pred)
            
            logger.info(f"Training Score: {train_score:.3f}")
            logger.info(f"Validation Score: {val_score:.3f}")
            logger.info(f"Mean Absolute Error: {mae:.2f}")
            
            # Guardar modelo
            model_filename = f"model_{self.class_instance.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.joblib"
            model_path = os.path.join(self.model_dir, model_filename)
            joblib.dump(model, model_path)
            
            # Desactivar modelos anteriores
            MLModel.objects.filter(class_instance=self.class_instance).update(is_active=False)
            
            # Guardar información del modelo en la base de datos
            ml_model = MLModel.objects.create(
                class_instance=self.class_instance,
                model_version=f"RF_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                algorithm="RandomForest",
                training_score=train_score,
                validation_score=val_score,
                mean_absolute_error=mae,
                training_samples=len(training_data),
                model_file_path=model_path,
                is_active=True
            )
            
            logger.info(f"Modelo guardado: {model_path}")
            return ml_model
            
        except Exception as e:
            logger.error(f"Error training model: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None
    
    def get_active_model(self):
        """
        Obtiene el modelo activo para la clase
        """
        try:
            ml_model = MLModel.objects.filter(
                class_instance=self.class_instance,
                is_active=True
            ).latest('created_at')
            
            if os.path.exists(ml_model.model_file_path):
                model = joblib.load(ml_model.model_file_path)
                return model, ml_model
            else:
                logger.warning(f"Archivo de modelo no encontrado: {ml_model.model_file_path}")
                return None, None
        except MLModel.DoesNotExist:
            logger.info("No hay modelo activo para esta clase")
            return None, None
        except Exception as e:
            logger.error(f"Error loading model: {str(e)}")
            return None, None
    
    def predict_next_period(self, student):
        """
        Predice la nota del próximo período para un estudiante
        """
        try:
            # Obtener datos del estudiante
            student_data = self.collect_student_data(student)
            
            if not student_data:
                logger.warning(f"No hay datos suficientes para el estudiante {student.first_name} {student.last_name}")
                return None
            
            # Determinar el próximo período a predecir
            student_grades = Grade.objects.filter(
                student=student,
                class_instance=self.class_instance
            ).select_related('period').order_by('period__period_type', 'period__number')
            
            if not student_grades.exists():
                logger.warning("El estudiante no tiene notas registradas")
                return None
            
            # Obtener todos los períodos de la clase
            class_periods = self.class_instance.periods.all().order_by('period_type', 'number')
            completed_periods = set(grade.period_id for grade in student_grades)
            
            # Encontrar el próximo período no completado
            next_period = None
            for period in class_periods:
                if period.id not in completed_periods:
                    next_period = period
                    break
            
            if not next_period:
                logger.info(f"No hay próximo período para predecir para {student.first_name} {student.last_name}")
                return None
            
            # Obtener o entrenar modelo
            model, ml_model = self.get_active_model()
            
            if model is None:
                logger.info("Entrenando nuevo modelo...")
                ml_model = self.train_model()
                if ml_model:
                    model, ml_model = self.get_active_model()
                else:
                    logger.error("No se pudo entrenar el modelo")
                    return None
            
            # Hacer predicción
            features = np.array([[
                student_data['avg_previous_grades'],
                student_data['attendance_percentage'],
                student_data['participation_average']
            ]])
            
            predicted_grade = model.predict(features)[0]
            
            # Calcular confianza basada en la calidad del modelo y cantidad de datos
            base_confidence = ml_model.validation_score * 100
            data_confidence = min(100, (student_data['grades_count'] / 3) * 100)
            confidence = (base_confidence + data_confidence) / 2
            
            # Crear o actualizar predicción
            prediction, created = Prediction.objects.update_or_create(
                student=student,
                class_instance=self.class_instance,
                predicted_period=next_period,
                defaults={
                    'predicted_grade': max(0, min(100, predicted_grade)),
                    'confidence': confidence,
                    'avg_previous_grades': student_data['avg_previous_grades'],
                    'attendance_percentage': student_data['attendance_percentage'],
                    'participation_average': student_data['participation_average'],
                    'model_version': ml_model.model_version
                }
            )
            
            logger.info(f"Predicción {'creada' if created else 'actualizada'} para {student.first_name} {student.last_name}: {predicted_grade:.1f}")
            return prediction
            
        except Exception as e:
            logger.error(f"Error predicting for student {student.first_name} {student.last_name}: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None
    
    def predict_specific_period(self, student, target_period, retrospective=False):
        """
        Predice la nota de un período específico para un estudiante
        
        Args:
            student: El estudiante
            target_period: El período a predecir
            retrospective: Si True, hace predicción retrospectiva (ignora si ya existe la nota)
        """
        try:
            # Obtener todas las notas del estudiante en esta clase
            all_grades = Grade.objects.filter(
                student=student,
                class_instance=self.class_instance
            ).select_related('period').order_by('period__period_type', 'period__number')
            
            if not all_grades.exists():
                logger.warning(f"No hay notas para el estudiante {student.first_name} {student.last_name}")
                return None
            
            # En modo retrospectivo, excluir el período objetivo del entrenamiento
            if retrospective:
                training_grades = all_grades.exclude(period=target_period)
                # Verificar que el período objetivo realmente tiene nota
                target_grade_exists = all_grades.filter(period=target_period).exists()
                if not target_grade_exists:
                    logger.warning(f"El período {target_period} no tiene nota real para comparar")
                    return None
            else:
                training_grades = all_grades
                # Verificar que el período objetivo NO tiene nota
                target_grade_exists = all_grades.filter(period=target_period).exists()
                if target_grade_exists:
                    logger.info(f"El período {target_period} ya tiene nota registrada")
                    return None
            
            if not training_grades.exists():
                logger.warning(f"No hay suficientes datos históricos para predecir")
                return None
            
            # Calcular promedio de notas de entrenamiento
            avg_previous_grades = training_grades.aggregate(avg=Avg('nota_total'))['avg'] or 0
            
            # Obtener períodos de entrenamiento para asistencia y participación
            training_period_ids = [grade.period_id for grade in training_grades]
            
            # Calcular porcentaje de asistencia promedio
            attendances = Attendance.objects.filter(
                student=student,
                class_instance=self.class_instance,
                period_id__in=training_period_ids
            )
            
            if attendances.exists():
                total_days = attendances.count()
                present_days = attendances.filter(status__in=['presente', 'tardanza']).count()
                attendance_percentage = (present_days / total_days) * 100 if total_days > 0 else 0
            else:
                attendance_percentage = 85  # Valor por defecto
            
            # Calcular promedio de participación
            participations = Participation.objects.filter(
                student=student,
                class_instance=self.class_instance,
                period_id__in=training_period_ids
            )
            
            if participations.exists():
                participation_scores = []
                for p in participations:
                    if p.level in ['alta', 'high']:
                        participation_scores.append(3)
                    elif p.level in ['media', 'medium']:
                        participation_scores.append(2)
                    else:
                        participation_scores.append(1)
                participation_average = sum(participation_scores) / len(participation_scores)
            else:
                participation_average = 2.0  # Valor por defecto (media)
            
            # Obtener o entrenar modelo
            model, ml_model = self.get_active_model()
            
            if model is None:
                logger.info("Entrenando nuevo modelo...")
                ml_model = self.train_model()
                if ml_model:
                    model, ml_model = self.get_active_model()
                else:
                    logger.error("No se pudo entrenar el modelo")
                    return None
            
            # Hacer predicción
            features = np.array([[
                avg_previous_grades,
                attendance_percentage,
                participation_average
            ]])
            
            predicted_grade = model.predict(features)[0]
            
            # Calcular confianza basada en la calidad del modelo y cantidad de datos
            base_confidence = ml_model.validation_score * 100
            data_confidence = min(100, (training_grades.count() / 2) * 100)
            confidence = (base_confidence + data_confidence) / 2
            
            # Crear o actualizar predicción
            prediction, created = Prediction.objects.update_or_create(
                student=student,
                class_instance=self.class_instance,
                predicted_period=target_period,
                defaults={
                    'predicted_grade': max(0, min(100, predicted_grade)),
                    'confidence': confidence,
                    'avg_previous_grades': avg_previous_grades,
                    'attendance_percentage': attendance_percentage,
                    'participation_average': participation_average,
                    'model_version': ml_model.model_version
                }
            )
            
            logger.info(f"Predicción {'retrospectiva' if retrospective else 'futura'} {'creada' if created else 'actualizada'} para {student.first_name} {student.last_name}: {predicted_grade:.1f}")
            return prediction
            
        except Exception as e:
            logger.error(f"Error predicting for student {student.first_name} {student.last_name}: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None

    def generate_retrospective_predictions(self, target_period=None):
        """
        Genera predicciones retrospectivas para comparar con la realidad
        
        Args:
            target_period: Período específico a predecir. Si es None, usa el último período con datos
        """
        logger.info(f"Generando predicciones retrospectivas para la clase: {self.class_instance.name}")
        
        # Si no se especifica período, usar el último período con notas
        if target_period is None:
            last_grade = Grade.objects.filter(
                class_instance=self.class_instance
            ).select_related('period').order_by('period__period_type', 'period__number').last()
            
            if not last_grade:
                logger.warning("No hay notas para generar predicciones retrospectivas")
                return []
            
            target_period = last_grade.period
        
        logger.info(f"Generando predicciones retrospectivas para el período: {target_period}")
        
        # Obtener estudiantes que tienen notas en el período objetivo
        students_with_target_grade = Grade.objects.filter(
            class_instance=self.class_instance,
            period=target_period
        ).values_list('student_id', flat=True)
        
        students = self.class_instance.students.filter(id__in=students_with_target_grade)
        
        retrospective_predictions = []
        
        for student in students:
            try:
                prediction = self.predict_specific_period(student, target_period, retrospective=True)
                if prediction:
                    retrospective_predictions.append(prediction)
            except Exception as e:
                logger.error(f"Error generando predicción retrospectiva para {student.first_name} {student.last_name}: {str(e)}")
        
        logger.info(f"Predicciones retrospectivas generadas: {len(retrospective_predictions)}")
        return retrospective_predictions

    def update_predictions_for_class(self, include_retrospective=False, target_period=None):
        """
        Actualiza predicciones para todos los estudiantes de la clase
        
        Args:
            include_retrospective: Si incluir predicciones retrospectivas
            target_period: Período específico para predicciones retrospectivas
        """
        logger.info(f"Actualizando predicciones para la clase: {self.class_instance.name}")
        
        updated_predictions = []
        
        # Predicciones futuras (modo normal)
        students = self.class_instance.students.all()
        
        for student in students:
            try:
                prediction = self.predict_next_period(student)
                if prediction:
                    updated_predictions.append(prediction)
            except Exception as e:
                logger.error(f"Error prediciendo para {student.first_name} {student.last_name}: {str(e)}")
        
        # Predicciones retrospectivas (si se solicita)
        if include_retrospective:
            retrospective_predictions = self.generate_retrospective_predictions(target_period)
            updated_predictions.extend(retrospective_predictions)
        
        logger.info(f"Predicciones actualizadas: {len(updated_predictions)}")
        return updated_predictions
    
    def create_prediction_history(self, student, period, actual_grade):
        """
        Crea un registro en el historial cuando se registra una nota real
        """
        try:
            # Buscar si había una predicción para este estudiante y período
            prediction = Prediction.objects.filter(
                student=student,
                class_instance=self.class_instance,
                predicted_period=period
            ).first()
            
            if prediction:
                # Crear registro de historial
                history = PredictionHistory.objects.create(
                    student=student,
                    class_instance=self.class_instance,
                    period=period,
                    predicted_grade=prediction.predicted_grade,
                    actual_grade=actual_grade,
                    prediction_confidence=prediction.confidence,
                    prediction_model_version=prediction.model_version,
                    prediction_date=prediction.created_at
                )
                
                # Eliminar la predicción ya que se convirtió en realidad
                prediction.delete()
                
                logger.info(f"Historial creado: {history}")
                return history
        except Exception as e:
            logger.error(f"Error creando historial: {str(e)}")
        
        return None