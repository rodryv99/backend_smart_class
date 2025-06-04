from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from users.models import StudentProfile
from academic.models import Class, Period

class Prediction(models.Model):
    """
    Modelo para almacenar predicciones de notas futuras
    """
    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name='predictions',
        verbose_name='Estudiante'
    )
    class_instance = models.ForeignKey(
        Class,
        on_delete=models.CASCADE,
        related_name='predictions',
        verbose_name='Clase'
    )
    predicted_period = models.ForeignKey(
        Period,
        on_delete=models.CASCADE,
        related_name='predictions',
        verbose_name='Período Predicho'
    )
    
    # Predicción de la nota
    predicted_grade = models.FloatField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Nota predicha para el período futuro (0-100 puntos)"
    )
    
    # Confianza del modelo (0-100%)
    confidence = models.FloatField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        default=0,
        help_text="Nivel de confianza de la predicción (0-100%)"
    )
    
    # Variables usadas para la predicción
    avg_previous_grades = models.FloatField(
        default=0,
        help_text="Promedio de notas anteriores usadas"
    )
    attendance_percentage = models.FloatField(
        default=0,
        help_text="Porcentaje de asistencia promedio"
    )
    participation_average = models.FloatField(
        default=0,
        help_text="Promedio de participación (1-3 escala)"
    )
    
    # Metadatos
    model_version = models.CharField(
        max_length=50,
        default="1.0",
        help_text="Versión del modelo usado para la predicción"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['student', 'class_instance', 'predicted_period']
        verbose_name = "Predicción"
        verbose_name_plural = "Predicciones"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Predicción: {self.student.first_name} {self.student.last_name} - {self.class_instance.name} - {self.predicted_period} - {self.predicted_grade:.1f}"


class PredictionHistory(models.Model):
    """
    Modelo para almacenar el historial de comparaciones realidad vs predicción
    """
    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name='prediction_history',
        verbose_name='Estudiante'
    )
    class_instance = models.ForeignKey(
        Class,
        on_delete=models.CASCADE,
        related_name='prediction_history',
        verbose_name='Clase'
    )
    period = models.ForeignKey(
        Period,
        on_delete=models.CASCADE,
        related_name='prediction_history',
        verbose_name='Período'
    )
    
    # Valores de predicción vs realidad
    predicted_grade = models.FloatField(
        help_text="Nota que se había predicho"
    )
    actual_grade = models.FloatField(
        help_text="Nota real obtenida"
    )
    difference = models.FloatField(
        help_text="Diferencia entre predicción y realidad (actual - predicted)"
    )
    absolute_error = models.FloatField(
        help_text="Error absoluto de la predicción"
    )
    
    # Variables que se usaron para la predicción
    prediction_confidence = models.FloatField(
        default=0,
        help_text="Confianza que tenía el modelo"
    )
    prediction_model_version = models.CharField(
        max_length=50,
        default="1.0",
        help_text="Versión del modelo que hizo la predicción"
    )
    
    # Metadatos
    prediction_date = models.DateTimeField(
        help_text="Cuándo se hizo la predicción"
    )
    actual_grade_date = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['student', 'class_instance', 'period']
        verbose_name = "Historial de Predicción"
        verbose_name_plural = "Historiales de Predicción"
        ordering = ['-actual_grade_date']
    
    def save(self, *args, **kwargs):
        # Calcular diferencia y error absoluto automáticamente
        self.difference = self.actual_grade - self.predicted_grade
        self.absolute_error = abs(self.difference)
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"Historial: {self.student.first_name} {self.student.last_name} - {self.period} - Pred: {self.predicted_grade:.1f} Real: {self.actual_grade:.1f}"


class MLModel(models.Model):
    """
    Modelo para almacenar información sobre los modelos de ML entrenados
    """
    class_instance = models.ForeignKey(
        Class,
        on_delete=models.CASCADE,
        related_name='ml_models',
        verbose_name='Clase'
    )
    
    # Información del modelo
    model_version = models.CharField(max_length=50, default="1.0")
    algorithm = models.CharField(
        max_length=50,
        default="RandomForest",
        choices=[
            ('RandomForest', 'Random Forest'),
            ('LinearRegression', 'Regresión Lineal'),
            ('GradientBoosting', 'Gradient Boosting')
        ]
    )
    
    # Métricas de rendimiento
    training_score = models.FloatField(default=0)
    validation_score = models.FloatField(default=0)
    mean_absolute_error = models.FloatField(default=0)
    training_samples = models.IntegerField(default=0)
    
    # Archivo del modelo serializado (ruta relativa)
    model_file_path = models.CharField(
        max_length=255,
        help_text="Ruta al archivo del modelo serializado"
    )
    
    # Metadatos
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(
        default=True,
        help_text="Si este modelo está activo para hacer predicciones"
    )
    
    class Meta:
        verbose_name = "Modelo ML"
        verbose_name_plural = "Modelos ML"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Modelo {self.algorithm} v{self.model_version} - {self.class_instance.name} - Score: {self.validation_score:.3f}"