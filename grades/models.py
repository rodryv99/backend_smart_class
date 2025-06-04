from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from users.models import StudentProfile
from academic.models import Class, Period

class Grade(models.Model):
    """
    Modelo para gestionar las notas de los estudiantes por período.
    Incluye los campos: Ser, Saber, Hacer, Decidir, Autoevaluación
    """
    STATUS_CHOICES = [
        ('approved', 'Aprobado'),
        ('failed', 'Reprobado'),
    ]
    
    # Relaciones
    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name='grades',
        verbose_name='Estudiante'
    )
    class_instance = models.ForeignKey(
        Class,
        on_delete=models.CASCADE,
        related_name='grades',
        verbose_name='Clase'
    )
    period = models.ForeignKey(
        Period,
        on_delete=models.CASCADE,
        related_name='grades',
        verbose_name='Período'
    )
    
    # Campos de calificación (según especificaciones)
    ser = models.FloatField(
        validators=[MinValueValidator(0), MaxValueValidator(5)],
        default=0,
        help_text="Nota de Ser (0-5 puntos)"
    )
    saber = models.FloatField(
        validators=[MinValueValidator(0), MaxValueValidator(45)],
        default=0,
        help_text="Nota de Saber (0-45 puntos)"
    )
    hacer = models.FloatField(
        validators=[MinValueValidator(0), MaxValueValidator(40)],
        default=0,
        help_text="Nota de Hacer (0-40 puntos)"
    )
    decidir = models.FloatField(
        validators=[MinValueValidator(0), MaxValueValidator(5)],
        default=0,
        help_text="Nota de Decidir (0-5 puntos)"
    )
    autoevaluacion = models.FloatField(
        validators=[MinValueValidator(0), MaxValueValidator(5)],
        default=0,
        help_text="Autoevaluación (0-5 puntos)"
    )
    
    # Campos calculados
    nota_total = models.FloatField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        default=0,
        help_text="Nota total (suma de todos los campos, 0-100 puntos)"
    )
    estado = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='failed',
        help_text="Estado: Aprobado (≥51) o Reprobado (<51)"
    )
    
    # Metadatos
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['student', 'class_instance', 'period']
        verbose_name = "Nota"
        verbose_name_plural = "Notas"
        ordering = ['-period__year', 'period__period_type', 'period__number', 'student__first_name']
    
    def __str__(self):
        return f"{self.student.first_name} {self.student.last_name} - {self.class_instance.name} - {self.period} - {self.nota_total}"
    
    def save(self, *args, **kwargs):
        """Calcular nota total y estado automáticamente al guardar"""
        # Calcular nota total
        self.nota_total = self.ser + self.saber + self.hacer + self.decidir + self.autoevaluacion
        
        # Determinar estado según la nota total
        self.estado = 'approved' if self.nota_total >= 51 else 'failed'
        
        super().save(*args, **kwargs)
    
    def clean(self):
        """Validaciones personalizadas"""
        # Verificar que el estudiante esté inscrito en la clase
        if self.class_instance and self.student:
            if not self.class_instance.students.filter(id=self.student.id).exists():
                raise ValidationError(
                    "El estudiante no está inscrito en esta clase"
                )
        
        # Verificar que el período esté asignado a la clase
        if self.class_instance and self.period:
            if not self.class_instance.periods.filter(id=self.period.id).exists():
                raise ValidationError(
                    "El período no está asignado a esta clase"
                )
    
    @property
    def grade_breakdown(self):
        """Retorna un diccionario con el desglose de notas"""
        return {
            'ser': self.ser,
            'saber': self.saber,
            'hacer': self.hacer,
            'decidir': self.decidir,
            'autoevaluacion': self.autoevaluacion,
            'total': self.nota_total,
            'estado': self.get_estado_display()
        }


class FinalGrade(models.Model):
    """
    Modelo para almacenar la nota final de la clase (promedio de todos los períodos)
    """
    STATUS_CHOICES = [
        ('approved', 'Aprobado'),
        ('failed', 'Reprobado'),
    ]
    
    # Relaciones
    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name='final_grades',
        verbose_name='Estudiante'
    )
    class_instance = models.ForeignKey(
        Class,
        on_delete=models.CASCADE,
        related_name='final_grades',
        verbose_name='Clase'
    )
    
    # Campos de calificación final
    nota_final = models.FloatField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        default=0,
        help_text="Nota final promedio de todos los períodos (0-100 puntos)"
    )
    estado_final = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='failed',
        help_text="Estado final: Aprobado (≥51) o Reprobado (<51)"
    )
    
    # Metadatos
    periods_count = models.IntegerField(
        default=0,
        help_text="Cantidad de períodos considerados en el promedio"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['student', 'class_instance']
        verbose_name = "Nota Final"
        verbose_name_plural = "Notas Finales"
        ordering = ['-class_instance__year', 'student__first_name']
    
    def __str__(self):
        return f"{self.student.first_name} {self.student.last_name} - {self.class_instance.name} - Final: {self.nota_final}"
    
    def calculate_final_grade(self):
        """Calcular la nota final basada en las notas de todos los períodos"""
        # Obtener todas las notas del estudiante en esta clase
        period_grades = Grade.objects.filter(
            student=self.student,
            class_instance=self.class_instance
        ).values_list('nota_total', flat=True)
        
        if period_grades:
            # Calcular promedio
            self.nota_final = sum(period_grades) / len(period_grades)
            self.periods_count = len(period_grades)
            
            # Determinar estado final
            self.estado_final = 'approved' if self.nota_final >= 51 else 'failed'
        else:
            self.nota_final = 0
            self.periods_count = 0
            self.estado_final = 'failed'
        
        self.save()
        return self.nota_final
    
    @classmethod
    def update_final_grade_for_student(cls, student, class_instance):
        """Método de clase para actualizar o crear la nota final de un estudiante"""
        final_grade, created = cls.objects.get_or_create(
            student=student,
            class_instance=class_instance
        )
        return final_grade.calculate_final_grade()

# NOTA: Los signals se importan en apps.py para evitar importaciones circulares