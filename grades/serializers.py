from rest_framework import serializers
from .models import Grade, FinalGrade
from users.models import StudentProfile
from academic.models import Class, Period
from academic.serializers import StudentSerializer, PeriodSerializer

class GradeSerializer(serializers.ModelSerializer):
    """Serializador para el modelo Grade"""
    student_detail = StudentSerializer(source='student', read_only=True)
    period_detail = PeriodSerializer(source='period', read_only=True)
    class_detail = serializers.SerializerMethodField()
    estado_display = serializers.CharField(source='get_estado_display', read_only=True)
    grade_breakdown = serializers.ReadOnlyField()
    
    class Meta:
        model = Grade
        fields = [
            'id', 'student', 'student_detail', 'class_instance', 'class_detail',
            'period', 'period_detail', 'ser', 'saber', 'hacer', 'decidir',
            'autoevaluacion', 'nota_total', 'estado', 'estado_display',
            'grade_breakdown', 'created_at', 'updated_at'
        ]
        read_only_fields = ['nota_total', 'estado', 'created_at', 'updated_at']
    
    def get_class_detail(self, obj):
        """Obtener detalles básicos de la clase"""
        return {
            'id': obj.class_instance.id,
            'name': obj.class_instance.name,
            'code': obj.class_instance.code,
            'subject': obj.class_instance.subject.name if obj.class_instance.subject else None,
            'course': obj.class_instance.course.name if obj.class_instance.course else None,
            'group': obj.class_instance.group.name if obj.class_instance.group else None,
            'year': obj.class_instance.year
        }
    
    def validate(self, data):
        """Validaciones personalizadas"""
        class_instance = data.get('class_instance')
        student = data.get('student')
        period = data.get('period')
        
        # Verificar que el estudiante esté inscrito en la clase
        if class_instance and student:
            if not class_instance.students.filter(id=student.id).exists():
                raise serializers.ValidationError(
                    "El estudiante no está inscrito en esta clase"
                )
        
        # Verificar que el período esté asignado a la clase
        if class_instance and period:
            if not class_instance.periods.filter(id=period.id).exists():
                raise serializers.ValidationError(
                    "El período no está asignado a esta clase"
                )
        
        # Validar rangos de notas
        validations = [
            ('ser', 0, 5),
            ('saber', 0, 45),
            ('hacer', 0, 40),
            ('decidir', 0, 5),
            ('autoevaluacion', 0, 5)
        ]
        
        for field, min_val, max_val in validations:
            value = data.get(field, 0)
            if value < min_val or value > max_val:
                raise serializers.ValidationError({
                    field: f"El valor debe estar entre {min_val} y {max_val}"
                })
        
        return data


class GradeBulkSerializer(serializers.Serializer):
    """Serializador para crear/actualizar notas masivamente"""
    class_instance = serializers.IntegerField()
    period = serializers.IntegerField()
    grades = serializers.ListField(
        child=serializers.DictField()
    )
    
    def validate_grades(self, value):
        """Validar estructura de notas"""
        for grade_data in value:
            required_fields = ['student_id', 'ser', 'saber', 'hacer', 'decidir', 'autoevaluacion']
            for field in required_fields:
                if field not in grade_data:
                    raise serializers.ValidationError(
                        f"Cada nota debe incluir: {', '.join(required_fields)}"
                    )
            
            # Validar rangos
            validations = [
                ('ser', 0, 5),
                ('saber', 0, 45),
                ('hacer', 0, 40),
                ('decidir', 0, 5),
                ('autoevaluacion', 0, 5)
            ]
            
            for field, min_val, max_val in validations:
                try:
                    value_to_check = float(grade_data[field])
                    if value_to_check < min_val or value_to_check > max_val:
                        raise serializers.ValidationError(
                            f"{field} debe estar entre {min_val} y {max_val}"
                        )
                except (ValueError, TypeError):
                    raise serializers.ValidationError(
                        f"{field} debe ser un número válido"
                    )
        
        return value


class FinalGradeSerializer(serializers.ModelSerializer):
    """Serializador para el modelo FinalGrade"""
    student_detail = StudentSerializer(source='student', read_only=True)
    class_detail = serializers.SerializerMethodField()
    estado_final_display = serializers.CharField(source='get_estado_final_display', read_only=True)
    period_grades = serializers.SerializerMethodField()
    
    class Meta:
        model = FinalGrade
        fields = [
            'id', 'student', 'student_detail', 'class_instance', 'class_detail',
            'nota_final', 'estado_final', 'estado_final_display', 'periods_count',
            'period_grades', 'created_at', 'updated_at'
        ]
        read_only_fields = ['nota_final', 'estado_final', 'periods_count', 'created_at', 'updated_at']
    
    def get_class_detail(self, obj):
        """Obtener detalles básicos de la clase"""
        return {
            'id': obj.class_instance.id,
            'name': obj.class_instance.name,
            'code': obj.class_instance.code,
            'subject': obj.class_instance.subject.name if obj.class_instance.subject else None,
            'course': obj.class_instance.course.name if obj.class_instance.course else None,
            'group': obj.class_instance.group.name if obj.class_instance.group else None,
            'year': obj.class_instance.year
        }
    
    def get_period_grades(self, obj):
        """Obtener todas las notas por período"""
        grades = Grade.objects.filter(
            student=obj.student,
            class_instance=obj.class_instance
        ).order_by('period__period_type', 'period__number')
        
        return [
            {
                'period': {
                    'id': grade.period.id,
                    'period_type': grade.period.period_type,
                    'number': grade.period.number,
                    'year': grade.period.year
                },
                'ser': grade.ser,
                'saber': grade.saber,
                'hacer': grade.hacer,
                'decidir': grade.decidir,
                'autoevaluacion': grade.autoevaluacion,
                'nota_total': grade.nota_total,
                'estado': grade.get_estado_display()
            }
            for grade in grades
        ]


class GradeStatsSerializer(serializers.Serializer):
    """Serializador para estadísticas de notas"""
    student_id = serializers.IntegerField()
    student_name = serializers.CharField()
    period_id = serializers.IntegerField()
    period_name = serializers.CharField()
    ser = serializers.FloatField()
    saber = serializers.FloatField()
    hacer = serializers.FloatField()
    decidir = serializers.FloatField()
    autoevaluacion = serializers.FloatField()
    nota_total = serializers.FloatField()
    estado = serializers.CharField()


class ClassGradesSummarySerializer(serializers.Serializer):
    """Serializador para resumen de notas de una clase"""
    class_id = serializers.IntegerField()
    class_name = serializers.CharField()
    period_id = serializers.IntegerField()
    period_name = serializers.CharField()
    total_students = serializers.IntegerField()
    students_with_grades = serializers.IntegerField()
    approved_count = serializers.IntegerField()
    failed_count = serializers.IntegerField()
    average_grade = serializers.FloatField()
    highest_grade = serializers.FloatField()
    lowest_grade = serializers.FloatField()


class StudentGradesSerializer(serializers.Serializer):
    """Serializador para todas las notas de un estudiante en una clase"""
    student_id = serializers.IntegerField()
    student_name = serializers.CharField()
    class_id = serializers.IntegerField()
    class_name = serializers.CharField()
    period_grades = GradeSerializer(many=True, read_only=True)
    final_grade = FinalGradeSerializer(read_only=True)
    can_view_details = serializers.BooleanField(default=False)
    can_edit_grades = serializers.BooleanField(default=False)