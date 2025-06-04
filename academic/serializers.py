from rest_framework import serializers
from .models import Period, Subject, Course, Group, Class, Attendance, Participation
from users.serializers import TeacherProfileSerializer, StudentProfileSerializer
from users.models import TeacherProfile, StudentProfile

class PeriodSerializer(serializers.ModelSerializer):
    period_type_display = serializers.CharField(source='get_period_type_display', read_only=True)
    
    class Meta:
        model = Period
        fields = ['id', 'period_type', 'period_type_display', 'number', 'year', 'start_date', 'end_date']
        
    def validate(self, data):
        """
        Verificar que la fecha de inicio es anterior a la fecha de fin
        y que el número del período es válido según el tipo
        """
        if data['start_date'] > data['end_date']:
            raise serializers.ValidationError(
                "La fecha de inicio debe ser anterior a la fecha de fin"
            )
        
        # Validar número según el tipo de período
        if data['period_type'] == 'trimester' and data['number'] > 3:
            raise serializers.ValidationError(
                "Los trimestres solo pueden ser del 1 al 3"
            )
        elif data['period_type'] == 'bimester' and data['number'] > 4:
            raise serializers.ValidationError(
                "Los bimestres solo pueden ser del 1 al 4"
            )
        
        return data

class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ['id', 'code', 'name']

class CourseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = ['id', 'code', 'name']

class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ['id', 'code', 'name']

class StudentSerializer(serializers.ModelSerializer):
    """Serializador simplificado para estudiantes"""
    class Meta:
        model = StudentProfile
        fields = ['id', 'ci', 'first_name', 'last_name']
        read_only_fields = fields

class TeacherSimpleSerializer(serializers.ModelSerializer):
    """Serializador simplificado para profesores"""
    class Meta:
        model = TeacherProfile
        fields = ['id', 'teacher_code', 'ci', 'first_name', 'last_name']
        read_only_fields = fields

class ClassSerializer(serializers.ModelSerializer):
    teacher_detail = TeacherSimpleSerializer(source='teacher', read_only=True)
    subject_detail = SubjectSerializer(source='subject', read_only=True)
    course_detail = CourseSerializer(source='course', read_only=True)
    group_detail = GroupSerializer(source='group', read_only=True)
    students_detail = StudentSerializer(source='students', many=True, read_only=True)
    periods_detail = PeriodSerializer(source='periods', many=True, read_only=True)
    
    class Meta:
        model = Class
        fields = [
            'id', 'code', 'name', 'description', 
            'teacher', 'teacher_detail',
            'subject', 'subject_detail',
            'course', 'course_detail',
            'group', 'group_detail',
            'year', 'students', 'students_detail',
            'periods', 'periods_detail',
            'created_at'
        ]
        read_only_fields = ['created_at', 'teacher']

    def validate(self, data):
        """
        Verificar que el profesor existe y que la combinación de materia, curso y grupo no está duplicada
        """
        # Verificar si estamos creando una nueva clase o actualizando una existente
        instance = getattr(self, 'instance', None)
        request = self.context.get('request')
        
        # Verificar que el año o gestión sea un valor válido (positivo)
        if data.get('year', 0) <= 0:
            raise serializers.ValidationError({"year": "El año o gestión debe ser un valor positivo"})
        
        # Verificar que los campos requeridos existen
        for field, label in [
            ('code', 'El código'),
            ('name', 'El nombre'),
            ('subject', 'La materia'),
            ('course', 'El curso'),
            ('group', 'El grupo')
        ]:
            if not data.get(field):
                raise serializers.ValidationError({field: f"{label} es requerido"})
            
        # Para una nueva clase, verificar que no exista duplicado
        if instance is None:
            # Obtener el profesor actual
            teacher = None
            if request and request.user.user_type == 'teacher':
                try:
                    teacher = request.user.teacher_profile
                except:
                    pass
            
            # Verificar si ya existe una clase con la misma combinación de elementos
            existing_query = Class.objects.filter(
                subject=data.get('subject'),
                course=data.get('course'),
                group=data.get('group'),
                year=data.get('year')
            )
            
            # Si el profesor está definido, agregar al filtro
            if teacher:
                existing_query = existing_query.filter(teacher=teacher)
                
            existing_class = existing_query.first()
            
            if existing_class:
                raise serializers.ValidationError({
                    "non_field_errors": ["Ya existe una clase con esta combinación de materia, curso, grupo y año"]
                })
        
        return data

class ClassStudentSerializer(serializers.Serializer):
    """Serializador para agregar o quitar estudiantes de una clase"""
    student_ids = serializers.ListField(
        child=serializers.IntegerField(),
        help_text="Lista de IDs de estudiantes"
    )

class ClassPeriodSerializer(serializers.Serializer):
    """Serializador para agregar o quitar períodos de una clase"""
    period_ids = serializers.ListField(
        child=serializers.IntegerField(),
        help_text="Lista de IDs de períodos"
    )


class AttendanceSerializer(serializers.ModelSerializer):
    student_detail = StudentSerializer(source='student', read_only=True)
    period_detail = PeriodSerializer(source='period', read_only=True)
    class_detail = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = Attendance
        fields = [
            'id', 'class_instance', 'class_detail', 'student', 'student_detail',
            'period', 'period_detail', 'date', 'status', 'status_display',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']
    
    def get_class_detail(self, obj):
        return {
            'id': obj.class_instance.id,
            'name': obj.class_instance.name,
            'code': obj.class_instance.code
        }
    
    def validate(self, data):
        """Validaciones personalizadas"""
        class_instance = data.get('class_instance')
        student = data.get('student')
        period = data.get('period')
        date = data.get('date')
        
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
        
        # Verificar que la fecha esté dentro del período
        if period and date:
            if date < period.start_date or date > period.end_date:
                raise serializers.ValidationError(
                    f"La fecha debe estar entre {period.start_date} y {period.end_date}"
                )
        
        return data


class ParticipationSerializer(serializers.ModelSerializer):
    student_detail = StudentSerializer(source='student', read_only=True)
    period_detail = PeriodSerializer(source='period', read_only=True)
    class_detail = serializers.SerializerMethodField()
    level_display = serializers.CharField(source='get_level_display', read_only=True)
    
    class Meta:
        model = Participation
        fields = [
            'id', 'class_instance', 'class_detail', 'student', 'student_detail',
            'period', 'period_detail', 'date', 'level', 'level_display',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']
    
    def get_class_detail(self, obj):
        return {
            'id': obj.class_instance.id,
            'name': obj.class_instance.name,
            'code': obj.class_instance.code
        }
    
    def validate(self, data):
        """Validaciones personalizadas"""
        class_instance = data.get('class_instance')
        student = data.get('student')
        period = data.get('period')
        date = data.get('date')
        
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
        
        # Verificar que la fecha esté dentro del período
        if period and date:
            if date < period.start_date or date > period.end_date:
                raise serializers.ValidationError(
                    f"La fecha debe estar entre {period.start_date} y {period.end_date}"
                )
        
        return data


class AttendanceBulkSerializer(serializers.Serializer):
    """Serializador para registrar asistencia masiva por día"""
    class_instance = serializers.IntegerField()
    period = serializers.IntegerField()
    date = serializers.DateField()
    attendances = serializers.ListField(
        child=serializers.DictField(
            child=serializers.CharField()
        )
    )
    
    def validate_attendances(self, value):
        """Validar estructura de asistencias"""
        for attendance in value:
            if 'student_id' not in attendance or 'status' not in attendance:
                raise serializers.ValidationError(
                    "Cada asistencia debe tener 'student_id' y 'status'"
                )
            
            # Aceptar tanto estados de frontend como backend
            valid_statuses = ['present', 'absent', 'late', 'presente', 'falta', 'tardanza']
            if attendance['status'] not in valid_statuses:
                raise serializers.ValidationError(
                    f"Estado inválido: {attendance['status']}. Estados válidos: {valid_statuses}"
                )
        
        return value


class ParticipationBulkSerializer(serializers.Serializer):
    """Serializador para registrar participación masiva por día - CORREGIDO"""
    class_instance = serializers.IntegerField()
    period = serializers.IntegerField()
    date = serializers.DateField()
    participations = serializers.ListField(
        child=serializers.DictField(
            child=serializers.CharField()
        )
    )
    
    def validate_participations(self, value):
        """Validar estructura de participaciones - CORREGIDO"""
        for participation in value:
            if 'student_id' not in participation or 'level' not in participation:
                raise serializers.ValidationError(
                    "Cada participación debe tener 'student_id' y 'level'"
                )
            
            # CORRECCIÓN: Aceptar tanto niveles de frontend como backend
            valid_levels = ['high', 'medium', 'low', 'alta', 'media', 'baja']
            if participation['level'] not in valid_levels:
                raise serializers.ValidationError(
                    f"Nivel inválido: {participation['level']}. Niveles válidos: {valid_levels}"
                )
        
        return value


class AttendanceStatsSerializer(serializers.Serializer):
    """Serializador para estadísticas de asistencia"""
    student_id = serializers.IntegerField()
    student_name = serializers.CharField()
    present_count = serializers.IntegerField()
    absent_count = serializers.IntegerField()
    late_count = serializers.IntegerField()  # Cambiado de absent_with_excuse_count
    total_days = serializers.IntegerField()
    attendance_percentage = serializers.FloatField()


class ParticipationStatsSerializer(serializers.Serializer):
    """Serializador para estadísticas de participación"""
    student_id = serializers.IntegerField()
    student_name = serializers.CharField()
    high_count = serializers.IntegerField()
    medium_count = serializers.IntegerField()
    low_count = serializers.IntegerField()
    total_days = serializers.IntegerField()
    average_score = serializers.FloatField()
    average_level = serializers.CharField()