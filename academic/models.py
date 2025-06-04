from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from users.models import TeacherProfile, StudentProfile

class Period(models.Model):
    PERIOD_TYPE_CHOICES = [
        ('bimestre', 'Bimestral'),
        ('trimestre', 'Trimestral'),
    ]
    
    period_type = models.CharField(
        max_length=10, 
        choices=PERIOD_TYPE_CHOICES, 
        default='bimestre',
        help_text="Tipo de período: bimestral o trimestral"
    )
    number = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(4)],
        help_text="Número del período (1-4 para bimestres, 1-3 para trimestres)"
    )
    year = models.IntegerField(help_text="Año o gestión")
    start_date = models.DateField()
    end_date = models.DateField()
    
    class Meta:
        unique_together = ['period_type', 'number', 'year']
        verbose_name = "Periodo"
        verbose_name_plural = "Periodos"
        ordering = ['year', 'period_type', 'number']
    
    def __str__(self):
        period_name = "Bimestre" if self.period_type == 'bimestre' else "Trimestre"
        return f"{period_name} {self.number} - {self.year}"
    
    def clean(self):
        from django.core.exceptions import ValidationError
        
        # Validar fecha de inicio anterior a fecha final
        if self.start_date > self.end_date:
            raise ValidationError("La fecha de inicio debe ser anterior a la fecha final")
        
        # Validar número según el tipo de período
        if self.period_type == 'trimestre' and self.number > 3:
            raise ValidationError("Los trimestres solo pueden ser del 1 al 3")
        elif self.period_type == 'bimestre' and self.number > 4:
            raise ValidationError("Los bimestres solo pueden ser del 1 al 4")

class Subject(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    
    class Meta:
        verbose_name = "Materia"
        verbose_name_plural = "Materias"
    
    def __str__(self):
        return f"{self.code} - {self.name}"

class Course(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    
    class Meta:
        verbose_name = "Curso"
        verbose_name_plural = "Cursos"
    
    def __str__(self):
        return f"{self.code} - {self.name}"

class Group(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    
    class Meta:
        verbose_name = "Grupo"
        verbose_name_plural = "Grupos"
    
    def __str__(self):
        return f"{self.code} - {self.name}"
    

class Class(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.CASCADE, related_name='classes')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='classes')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='classes')
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='classes')
    year = models.IntegerField(help_text="Año o gestión")
    periods = models.ManyToManyField(Period, related_name='classes', blank=True, help_text="Períodos asignados a esta clase")
    students = models.ManyToManyField(StudentProfile, related_name='enrolled_classes', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Clase"
        verbose_name_plural = "Clases"
        unique_together = ['subject', 'course', 'group', 'year', 'teacher']
    
    def __str__(self):
        return f"{self.code} - {self.name} ({self.subject.name}, {self.course.name}, {self.group.name})"


class Attendance(models.Model):
    # Estados en español para coincidir con la BD
    ATTENDANCE_CHOICES = [
        ('presente', 'Presente'),
        ('falta', 'Falta'),
        ('tardanza', 'Tardanza'),
    ]
    
    class_instance = models.ForeignKey(
        Class, 
        on_delete=models.CASCADE, 
        related_name='attendances'
    )
    student = models.ForeignKey(
        StudentProfile, 
        on_delete=models.CASCADE, 
        related_name='attendances'
    )
    period = models.ForeignKey(
        Period, 
        on_delete=models.CASCADE, 
        related_name='attendances'
    )
    date = models.DateField()
    status = models.CharField(
        max_length=20, 
        choices=ATTENDANCE_CHOICES, 
        default='presente'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['class_instance', 'student', 'period', 'date']
        verbose_name = "Asistencia"
        verbose_name_plural = "Asistencias"
        ordering = ['-date', 'student__first_name']
    
    def __str__(self):
        return f"{self.student.first_name} {self.student.last_name} - {self.get_status_display()} - {self.date}"
    
    def clean(self):
        from django.core.exceptions import ValidationError
        
        # Verificar que la fecha esté dentro del período
        if self.date < self.period.start_date or self.date > self.period.end_date:
            raise ValidationError(
                f"La fecha debe estar entre {self.period.start_date} y {self.period.end_date}"
            )
        
        # Verificar que el estudiante esté inscrito en la clase
        if not self.class_instance.students.filter(id=self.student.id).exists():
            raise ValidationError(
                "El estudiante no está inscrito en esta clase"
            )
        
        # Verificar que el período esté asignado a la clase
        if not self.class_instance.periods.filter(id=self.period.id).exists():
            raise ValidationError(
                "El período no está asignado a esta clase"
            )


class Participation(models.Model):
    # Estados en español para coincidir con la BD
    PARTICIPATION_CHOICES = [
        ('alta', 'Alta'),
        ('media', 'Media'),
        ('baja', 'Baja'),
    ]
    
    class_instance = models.ForeignKey(
        Class, 
        on_delete=models.CASCADE, 
        related_name='participations'
    )
    student = models.ForeignKey(
        StudentProfile, 
        on_delete=models.CASCADE, 
        related_name='participations'
    )
    period = models.ForeignKey(
        Period, 
        on_delete=models.CASCADE, 
        related_name='participations'
    )
    date = models.DateField()
    level = models.CharField(
        max_length=10, 
        choices=PARTICIPATION_CHOICES, 
        default='media'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['class_instance', 'student', 'period', 'date']
        verbose_name = "Participación"
        verbose_name_plural = "Participaciones"
        ordering = ['-date', 'student__first_name']
    
    def __str__(self):
        return f"{self.student.first_name} {self.student.last_name} - {self.get_level_display()} - {self.date}"
    
    def clean(self):
        from django.core.exceptions import ValidationError
        
        # Verificar que la fecha esté dentro del período
        if self.date < self.period.start_date or self.date > self.period.end_date:
            raise ValidationError(
                f"La fecha debe estar entre {self.period.start_date} y {self.period.end_date}"
            )
        
        # Verificar que el estudiante esté inscrito en la clase
        if not self.class_instance.students.filter(id=self.student.id).exists():
            raise ValidationError(
                "El estudiante no está inscrito en esta clase"
            )
        
        # Verificar que el período esté asignado a la clase
        if not self.class_instance.periods.filter(id=self.period.id).exists():
            raise ValidationError(
                "El período no está asignado a esta clase"
            )