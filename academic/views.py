from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from .models import Period, Subject, Course, Group, Class, Attendance, Participation
from .serializers import (
    PeriodSerializer, SubjectSerializer, CourseSerializer, 
    GroupSerializer, ClassSerializer, ClassStudentSerializer,
    ClassPeriodSerializer, AttendanceSerializer, ParticipationSerializer,
    AttendanceBulkSerializer, ParticipationBulkSerializer,
    AttendanceStatsSerializer, ParticipationStatsSerializer
)
from users.models import StudentProfile
from django.http import JsonResponse
from django.db import connection, transaction
from django.db.models import Q, Count, Avg
from datetime import datetime, date

class IsAdminUser(permissions.BasePermission):
    """
    Permiso personalizado que solo permite acceso a usuarios administradores.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.user_type == 'admin'

class IsAdminOrTeacherForReadOnly(permissions.BasePermission):
    """
    Permiso que permite:
    - Acceso completo a administradores
    - Acceso de solo lectura a profesores
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
            
        # Admin tiene permisos completos
        if request.user.user_type == 'admin':
            return True
            
        # Profesores tienen permisos de solo lectura
        if request.user.user_type == 'teacher' and request.method in permissions.SAFE_METHODS:
            return True
            
        return False

class IsTeacherUser(permissions.BasePermission):
    """
    Permiso personalizado que solo permite acceso a usuarios profesores.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.user_type == 'teacher'

class IsTeacherOwnerOrAdminUser(permissions.BasePermission):
    """
    Permiso que permite acceso completo a administradores y 
    acceso limitado a profesores que son dueños de la clase.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.user.user_type == 'admin' or 
            request.user.user_type == 'teacher'
        )
        
    def has_object_permission(self, request, view, obj):
        # El administrador siempre tiene permiso completo
        if request.user.user_type == 'admin':
            return True
        
        # El profesor solo puede acceder/modificar sus propias clases
        if request.user.user_type == 'teacher':
            try:
                teacher_profile = request.user.teacher_profile
                return obj.teacher == teacher_profile
            except:
                return False
        
        return False

class IsEnrolledStudentTeacherOwnerOrAdmin(permissions.BasePermission):
    """
    Permiso que permite:
    - Acceso completo a administradores
    - Acceso completo a profesores dueños de la clase
    - Acceso de solo lectura a estudiantes inscritos en la clase
    """
    def has_object_permission(self, request, view, obj):
        # El administrador siempre tiene permiso completo
        if request.user.user_type == 'admin':
            return True
        
        # El profesor dueño tiene permiso completo
        if request.user.user_type == 'teacher':
            try:
                teacher_profile = request.user.teacher_profile
                return obj.teacher == teacher_profile
            except:
                return False
        
        # El estudiante inscrito tiene permiso de solo lectura
        if request.user.user_type == 'student' and request.method in permissions.SAFE_METHODS:
            try:
                student_profile = request.user.student_profile
                return student_profile in obj.students.all()
            except:
                return False
        
        return False

class AttendanceParticipationPermission(permissions.BasePermission):
    """
    Permiso para asistencia y participación:
    - Admin: acceso completo
    - Profesor: solo sus clases
    - Estudiante: solo lectura de sus propios datos
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        if request.user.user_type == 'admin':
            return True
        
        if request.user.user_type == 'teacher':
            try:
                teacher_profile = request.user.teacher_profile
                return obj.class_instance.teacher == teacher_profile
            except:
                return False
        
        if request.user.user_type == 'student':
            if request.method in permissions.SAFE_METHODS:
                try:
                    student_profile = request.user.student_profile
                    return obj.student == student_profile
                except:
                    return False
        
        return False

class PeriodViewSet(viewsets.ModelViewSet):
    queryset = Period.objects.all()
    serializer_class = PeriodSerializer
    permission_classes = [IsAdminOrTeacherForReadOnly]

class SubjectViewSet(viewsets.ModelViewSet):
    queryset = Subject.objects.all()
    serializer_class = SubjectSerializer
    permission_classes = [IsAdminOrTeacherForReadOnly]

class CourseViewSet(viewsets.ModelViewSet):
    queryset = Course.objects.all()
    serializer_class = CourseSerializer
    permission_classes = [IsAdminOrTeacherForReadOnly]

class GroupViewSet(viewsets.ModelViewSet):
    queryset = Group.objects.all()
    serializer_class = GroupSerializer
    permission_classes = [IsAdminOrTeacherForReadOnly]

class ClassViewSet(viewsets.ModelViewSet):
    queryset = Class.objects.all()
    serializer_class = ClassSerializer
    
    def get_permissions(self):
        """
        Permisos según la acción:
        - list/retrieve: Estudiantes inscritos, profesor dueño o admin
        - create: Solo profesores o admin
        - update/delete: Solo profesor dueño o admin
        """
        if self.action in ['update', 'partial_update', 'destroy']:
            permission_classes = [permissions.IsAuthenticated, IsTeacherOwnerOrAdminUser]
        elif self.action == 'create':
            permission_classes = [permissions.IsAuthenticated, IsTeacherUser]
        else:
            permission_classes = [permissions.IsAuthenticated]
            
        if self.action in ['add_students', 'remove_students', 'available_students', 'add_periods', 'remove_periods']:
            permission_classes = [permissions.IsAuthenticated, IsTeacherOwnerOrAdminUser]
        
        return [permission() for permission in permission_classes]
    
    def get_queryset(self):
        """
        Filtrar clases según el tipo de usuario:
        - Admin: Todas las clases
        - Profesor: Solo sus clases
        - Estudiante: Solo clases donde está inscrito
        """
        user = self.request.user
        
        if user.user_type == 'admin':
            return Class.objects.all()
        
        elif user.user_type == 'teacher':
            try:
                teacher_profile = user.teacher_profile
                return Class.objects.filter(teacher=teacher_profile)
            except Exception as e:
                print(f"Error obteniendo clases para profesor {user.id}: {str(e)}")
                return Class.objects.none()
        
        elif user.user_type == 'student':
            try:
                student_profile = user.student_profile
                # Verificar que student_profile existe
                if not student_profile:
                    print(f"No se encontró perfil de estudiante para el usuario {user.id}")
                    return Class.objects.none()
                
                # Intentar obtener clases directamente con SQL para depuración
                from django.db import connection
                cursor = connection.cursor()
                cursor.execute("""
                    SELECT c.id, c.name 
                    FROM academic_class c
                    JOIN academic_class_students cs ON c.id = cs.class_id
                    WHERE cs.studentprofile_id = %s
                """, [student_profile.id])
                direct_classes = cursor.fetchall()
                print(f"Clases encontradas con SQL directo: {direct_classes}")
                
                # Obtener las clases y hacer log para depuración
                classes = Class.objects.filter(students=student_profile)
                print(f"Usuario: {user.username}, ID de perfil de estudiante: {student_profile.id}")
                print(f"Clases encontradas con ORM: {[(c.id, c.name) for c in classes]}")
                
                # Si no hay clases en el ORM pero hay en SQL directo, cargarlas manualmente
                if not classes and direct_classes:
                    print("Cargando clases manualmente desde SQL directo")
                    class_ids = [row[0] for row in direct_classes]
                    return Class.objects.filter(id__in=class_ids)
                
                return classes
            except Exception as e:
                print(f"Error obteniendo clases para estudiante {user.id}: {str(e)}")
                return Class.objects.none()
        
        return Class.objects.none()
    
    def perform_create(self, serializer):
        """Al crear una clase, asignar automáticamente el profesor actual"""
        if self.request.user.user_type == 'teacher':
            teacher_profile = self.request.user.teacher_profile
            # Pasar el contexto para la validación en el serializador
            serializer.context['request'] = self.request
            serializer.save(teacher=teacher_profile)
        else:
            serializer.context['request'] = self.request
            serializer.save()
    
    def update(self, request, *args, **kwargs):
        """Sobrescribimos update para verificar permisos manualmente"""
        instance = self.get_object()
        
        # Verificar si el usuario tiene permisos para editar esta clase
        if request.user.user_type == 'admin' or (
            request.user.user_type == 'teacher' and 
            hasattr(request.user, 'teacher_profile') and
            instance.teacher == request.user.teacher_profile
        ):
            # El usuario tiene permisos, procedemos con la actualización
            return super().update(request, *args, **kwargs)
        
        # El usuario no tiene permisos
        return Response(
            {"detail": "No tienes permisos para editar esta clase."}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    def destroy(self, request, *args, **kwargs):
        """Sobrescribimos destroy para verificar permisos manualmente"""
        instance = self.get_object()
        
        # Verificar si el usuario tiene permisos para eliminar esta clase
        if request.user.user_type == 'admin' or (
            request.user.user_type == 'teacher' and 
            hasattr(request.user, 'teacher_profile') and
            instance.teacher == request.user.teacher_profile
        ):
            # El usuario tiene permisos, procedemos con la eliminación
            return super().destroy(request, *args, **kwargs)
        
        # El usuario no tiene permisos
        return Response(
            {"detail": "No tienes permisos para eliminar esta clase."}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    def get_serializer_context(self):
        """
        Pasar el contexto al serializador, incluyendo la solicitud
        """
        context = super().get_serializer_context()
        return context
    
    @action(detail=True, methods=['get'])
    def available_students(self, request, pk=None):
        """Obtener la lista de estudiantes disponibles para añadir a la clase"""
        class_obj = self.get_object()
        
        # Obtener todos los estudiantes que no están ya en la clase
        enrolled_students_ids = [s.id for s in class_obj.students.all()]
        available_students = StudentProfile.objects.exclude(id__in=enrolled_students_ids)
        
        from .serializers import StudentSerializer
        serializer = StudentSerializer(available_students, many=True)
        
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'])
    def add_students(self, request, pk=None):
        """Añadir estudiantes a una clase"""
        class_obj = self.get_object()
        serializer = ClassStudentSerializer(data=request.data)
        
        if serializer.is_valid():
            student_ids = serializer.validated_data['student_ids']
            print(f"Añadiendo estudiantes a la clase {pk}: {student_ids}")
            
            students = StudentProfile.objects.filter(id__in=student_ids)
            print(f"Estudiantes encontrados: {[s.id for s in students]}")
            
            try:
                # Limpiar la relación primero para evitar problemas con la BD
                for student in students:
                    # Remover primero (por si acaso hay algún conflicto)
                    class_obj.students.remove(student)
                    # Luego añadir
                    class_obj.students.add(student)
                    print(f"Estudiante {student.id} ({student.first_name} {student.last_name}) añadido a la clase {class_obj.id} ({class_obj.name})")
                    
                    # Verificar que la relación se estableció correctamente
                    if not class_obj.students.filter(id=student.id).exists():
                        print(f"⚠️ Error: La relación no se guardó para el estudiante {student.id}")
                        
                        # Intentar inserción directa en la tabla de relación
                        from django.db import connection
                        cursor = connection.cursor()
                        try:
                            # Verificar si la tabla tiene nombre personalizado
                            table_name = class_obj._meta.get_field('students').m2m_db_table()
                            print(f"Nombre de tabla M2M: {table_name}")
                            
                            # Obtener nombres de campos
                            class_field = class_obj._meta.get_field('students').m2m_column_name()
                            student_field = class_obj._meta.get_field('students').m2m_reverse_name()
                            
                            print(f"Campos M2M: clase={class_field}, estudiante={student_field}")
                            
                            # Insertar directo en la BD
                            cursor.execute(f"""
                                INSERT INTO {table_name} ({class_field}, {student_field})
                                VALUES (%s, %s)
                            """, [class_obj.id, student.id])
                            
                            print(f"Inserción directa realizada para estudiante {student.id}")
                        except Exception as e:
                            print(f"Error en inserción directa: {str(e)}")
                    else:
                        print(f"✅ Relación verificada para estudiante {student.id}")
                        
                # Refrescar el objeto para obtener los cambios
                class_obj.refresh_from_db()
                
                # Verificar que los estudiantes realmente se añadieron
                students_after = list(class_obj.students.all())
                print(f"Estudiantes en la clase después de añadir: {[s.id for s in students_after]}")
                
                # Verificar directamente en la BD
                from django.db import connection
                cursor = connection.cursor()
                cursor.execute("""
                    SELECT * FROM academic_class_students 
                    WHERE class_id=%s
                """, [class_obj.id])
                relations = cursor.fetchall()
                print(f"Relaciones encontradas en BD: {relations}")
                
                # Si hay estudiantes en student_ids que no están en la relación, volver a intentar
                missing_students = []
                for student_id in student_ids:
                    if not any(s.id == student_id for s in students_after):
                        missing_students.append(student_id)
                
                if missing_students:
                    print(f"⚠️ Estudiantes faltantes después del primer intento: {missing_students}")
                    # Usar SQL directo para los estudiantes faltantes
                    table_name = class_obj._meta.get_field('students').m2m_db_table()
                    class_field = class_obj._meta.get_field('students').m2m_column_name()
                    student_field = class_obj._meta.get_field('students').m2m_reverse_name()
                    
                    for student_id in missing_students:
                        try:
                            cursor.execute(f"""
                                INSERT INTO {table_name} ({class_field}, {student_field})
                                VALUES (%s, %s)
                            """, [class_obj.id, student_id])
                            print(f"Inserción directa adicional para estudiante {student_id}")
                        except Exception as e:
                            print(f"Error en inserción adicional: {str(e)}")
                
                # Obtener la clase actualizada para la respuesta
                updated_class = Class.objects.get(id=pk)
                return Response(
                    ClassSerializer(updated_class).data,
                    status=status.HTTP_200_OK
                )
            except Exception as e:
                print(f"Error al añadir estudiantes: {str(e)}")
                import traceback
                print(traceback.format_exc())
                return Response(
                    {"error": f"Error al añadir estudiantes: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def remove_students(self, request, pk=None):
        """Quitar estudiantes de una clase"""
        class_obj = self.get_object()
        serializer = ClassStudentSerializer(data=request.data)
        
        if serializer.is_valid():
            student_ids = serializer.validated_data['student_ids']
            print(f"Removiendo estudiantes de la clase {pk}: {student_ids}")
            
            students = StudentProfile.objects.filter(id__in=student_ids)
            print(f"Estudiantes encontrados para remover: {[s.id for s in students]}")
            
            # Quitar estudiantes de la clase
            for student in students:
                class_obj.students.remove(student)
                print(f"Estudiante {student.id} removido de la clase {class_obj.id}")
            
            # Verificar que los estudiantes realmente se removieron
            updated_class = Class.objects.get(id=pk)
            print(f"Estudiantes en la clase después de remover: {[s.id for s in updated_class.students.all()]}")
            
            return Response(
                ClassSerializer(updated_class).data,
                status=status.HTTP_200_OK
            )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['get'])
    def periods(self, request, pk=None):
        """Obtener los períodos asignados a la clase"""
        class_obj = self.get_object()
        periods = class_obj.periods.all().order_by('year', 'period_type', 'number')
        
        return Response(
            PeriodSerializer(periods, many=True).data,
            status=status.HTTP_200_OK
        )
    
    @action(detail=True, methods=['get'])
    def available_periods(self, request, pk=None):
        """Obtener la lista de períodos disponibles para añadir a la clase"""
        class_obj = self.get_object()
        
        # Obtener todos los períodos del mismo año que no están ya en la clase
        assigned_periods_ids = [p.id for p in class_obj.periods.all()]
        available_periods = Period.objects.filter(
            year=class_obj.year
        ).exclude(id__in=assigned_periods_ids).order_by('period_type', 'number')
        
        serializer = PeriodSerializer(available_periods, many=True)
        
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'])
    def add_periods(self, request, pk=None):
        """Añadir períodos a una clase"""
        class_obj = self.get_object()
        serializer = ClassPeriodSerializer(data=request.data)
        
        if serializer.is_valid():
            period_ids = serializer.validated_data['period_ids']
            print(f"Añadiendo períodos a la clase {pk}: {period_ids}")
            
            periods = Period.objects.filter(id__in=period_ids, year=class_obj.year)
            print(f"Períodos encontrados: {[p.id for p in periods]}")
            
            # Verificar que todos los períodos son del mismo año que la clase
            invalid_periods = Period.objects.filter(id__in=period_ids).exclude(year=class_obj.year)
            if invalid_periods.exists():
                return Response(
                    {"error": f"Los períodos deben corresponder al año {class_obj.year} de la clase"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            try:
                # Añadir períodos a la clase
                for period in periods:
                    class_obj.periods.add(period)
                    print(f"Período {period.id} ({period}) añadido a la clase {class_obj.id}")
                
                # Obtener la clase actualizada para la respuesta
                updated_class = Class.objects.get(id=pk)
                return Response(
                    ClassSerializer(updated_class).data,
                    status=status.HTTP_200_OK
                )
            except Exception as e:
                print(f"Error al añadir períodos: {str(e)}")
                return Response(
                    {"error": f"Error al añadir períodos: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def remove_periods(self, request, pk=None):
        """Quitar períodos de una clase"""
        class_obj = self.get_object()
        serializer = ClassPeriodSerializer(data=request.data)
        
        if serializer.is_valid():
            period_ids = serializer.validated_data['period_ids']
            print(f"Removiendo períodos de la clase {pk}: {period_ids}")
            
            periods = Period.objects.filter(id__in=period_ids)
            print(f"Períodos encontrados para remover: {[p.id for p in periods]}")
            
            # Verificar que no hay registros de asistencia o participación en estos períodos
            for period in periods:
                attendance_count = Attendance.objects.filter(
                    class_instance=class_obj, 
                    period=period
                ).count()
                participation_count = Participation.objects.filter(
                    class_instance=class_obj, 
                    period=period
                ).count()
                
                if attendance_count > 0 or participation_count > 0:
                    return Response(
                        {"error": f"No se puede remover el período {period} porque tiene registros de asistencia o participación"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # Quitar períodos de la clase
            for period in periods:
                class_obj.periods.remove(period)
                print(f"Período {period.id} removido de la clase {class_obj.id}")
            
            # Verificar que los períodos realmente se removieron
            updated_class = Class.objects.get(id=pk)
            print(f"Períodos en la clase después de remover: {[p.id for p in updated_class.periods.all()]}")
            
            return Response(
                ClassSerializer(updated_class).data,
                status=status.HTTP_200_OK
            )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AttendanceViewSet(viewsets.ModelViewSet):
    queryset = Attendance.objects.all()
    serializer_class = AttendanceSerializer
    permission_classes = [AttendanceParticipationPermission]
    
    def get_queryset(self):
        """Filtrar asistencias según el tipo de usuario"""
        user = self.request.user
        
        if user.user_type == 'admin':
            return Attendance.objects.all()
        
        elif user.user_type == 'teacher':
            try:
                teacher_profile = user.teacher_profile
                return Attendance.objects.filter(class_instance__teacher=teacher_profile)
            except:
                return Attendance.objects.none()
        
        elif user.user_type == 'student':
            try:
                student_profile = user.student_profile
                return Attendance.objects.filter(student=student_profile)
            except:
                return Attendance.objects.none()
        
        return Attendance.objects.none()
    
    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        """Crear múltiples registros de asistencia para un día"""
        serializer = AttendanceBulkSerializer(data=request.data)
        
        if serializer.is_valid():
            class_id = serializer.validated_data['class_instance']
            period_id = serializer.validated_data['period']
            date = serializer.validated_data['date']
            attendances_data = serializer.validated_data['attendances']
            
            try:
                # Verificar permisos
                class_instance = Class.objects.get(id=class_id)
                if request.user.user_type == 'teacher':
                    teacher_profile = request.user.teacher_profile
                    if class_instance.teacher != teacher_profile:
                        return Response(
                            {"error": "No tienes permisos para esta clase"},
                            status=status.HTTP_403_FORBIDDEN
                        )
                elif request.user.user_type != 'admin':
                    return Response(
                        {"error": "No tienes permisos para realizar esta acción"},
                        status=status.HTTP_403_FORBIDDEN
                    )
                
                period = Period.objects.get(id=period_id)
                
                # Verificar que el período está asignado a la clase
                if not class_instance.periods.filter(id=period.id).exists():
                    return Response(
                        {"error": "El período no está asignado a esta clase"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                # Mapeo de estados frontend -> backend
                status_mapping = {
                    'present': 'presente',
                    'absent': 'falta',
                    'late': 'tardanza'
                }
                
                with transaction.atomic():
                    created_attendances = []
                    
                    for attendance_data in attendances_data:
                        student_id = attendance_data['student_id']
                        frontend_status = attendance_data['status']
                        
                        # Convertir estado de frontend a backend
                        backend_status = status_mapping.get(frontend_status, frontend_status)
                        
                        # Crear o actualizar asistencia
                        attendance, created = Attendance.objects.update_or_create(
                            class_instance=class_instance,
                            student_id=student_id,
                            period=period,
                            date=date,
                            defaults={'status': backend_status}
                        )
                        
                        created_attendances.append(attendance)
                
                # Serializar respuesta con mapeo inverso
                response_data = []
                backend_to_frontend = {
                    'presente': 'present',
                    'falta': 'absent',
                    'tardanza': 'late'
                }
                
                for attendance in created_attendances:
                    attendance_dict = AttendanceSerializer(attendance).data
                    # Convertir estado de backend a frontend para la respuesta
                    attendance_dict['status'] = backend_to_frontend.get(attendance_dict['status'], attendance_dict['status'])
                    response_data.append(attendance_dict)
                
                return Response(response_data, status=status.HTTP_201_CREATED)
                
            except Class.DoesNotExist:
                return Response(
                    {"error": "Clase no encontrada"},
                    status=status.HTTP_404_NOT_FOUND
                )
            except Period.DoesNotExist:
                return Response(
                    {"error": "Período no encontrado"},
                    status=status.HTTP_404_NOT_FOUND
                )
            except Exception as e:
                return Response(
                    {"error": f"Error al crear asistencias: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def by_class_and_period(self, request):
        """Obtener asistencias por clase y período"""
        class_id = request.query_params.get('class_id')
        period_id = request.query_params.get('period_id')
        date_param = request.query_params.get('date')
        
        if not class_id or not period_id:
            return Response(
                {"error": "class_id y period_id son requeridos"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        queryset = self.get_queryset().filter(
            class_instance_id=class_id,
            period_id=period_id
        )
        
        if date_param:
            try:
                date_obj = datetime.strptime(date_param, '%Y-%m-%d').date()
                queryset = queryset.filter(date=date_obj)
            except ValueError:
                return Response(
                    {"error": "Formato de fecha inválido. Use YYYY-MM-DD"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Mapeo de estados backend -> frontend
        backend_to_frontend = {
            'presente': 'present',
            'falta': 'absent', 
            'tardanza': 'late'
        }
        
        # Obtener datos y mapear estados
        response_data = []
        for attendance in queryset:
            attendance_dict = self.get_serializer(attendance).data
            # Convertir estado de backend a frontend
            attendance_dict['status'] = backend_to_frontend.get(attendance_dict['status'], attendance_dict['status'])
            response_data.append(attendance_dict)
        
        return Response(response_data)
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Obtener estadísticas de asistencia"""
        class_id = request.query_params.get('class_id')
        period_id = request.query_params.get('period_id')
        
        if not class_id:
            return Response(
                {"error": "class_id es requerido"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        print(f"=== DEBUG STATS PERMISSIONS ===")
        print(f"User ID: {request.user.id}")
        print(f"User type: {request.user.user_type}")
        print(f"Class ID: {class_id}")
        
        # Verificar permisos
        try:
            class_instance = Class.objects.get(id=class_id)
            print(f"Class teacher ID: {class_instance.teacher.id if class_instance.teacher else 'None'}")
            
            if request.user.user_type == 'teacher':
                try:
                    teacher_profile = request.user.teacher_profile
                    print(f"Teacher profile ID: {teacher_profile.id}")
                    print(f"Teacher profile user ID: {teacher_profile.user_id}")
                    
                    if class_instance.teacher != teacher_profile:
                        print(f"❌ Permission denied: {class_instance.teacher.id} != {teacher_profile.id}")
                        return Response(
                            {"error": "No tienes permisos para esta clase"},
                            status=status.HTTP_403_FORBIDDEN
                        )
                    else:
                        print(f"✅ Permission granted: Teacher owns this class")
                except Exception as e:
                    print(f"❌ Error verificando permisos de profesor: {str(e)}")
                    import traceback
                    print(traceback.format_exc())
                    return Response(
                        {"error": f"Error de permisos: {str(e)}"},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
            elif request.user.user_type == 'student':
                try:
                    student_profile = request.user.student_profile
                    print(f"Student profile ID: {student_profile.id}")
                    
                    if not class_instance.students.filter(id=student_profile.id).exists():
                        print(f"❌ Permission denied: Student not enrolled in class")
                        return Response(
                            {"error": "No estás inscrito en esta clase"},
                            status=status.HTTP_403_FORBIDDEN
                        )
                    else:
                        print(f"✅ Permission granted: Student enrolled in class")
                except Exception as e:
                    print(f"❌ Error verificando permisos de estudiante: {str(e)}")
                    import traceback
                    print(traceback.format_exc())
                    return Response(
                        {"error": f"Error de permisos: {str(e)}"},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
            elif request.user.user_type != 'admin':
                print(f"❌ Permission denied: Invalid user type {request.user.user_type}")
                return Response(
                    {"error": "No tienes permisos para realizar esta acción"},
                    status=status.HTTP_403_FORBIDDEN
                )
            else:
                print(f"✅ Permission granted: Admin user")
                
        except Class.DoesNotExist:
            print(f"❌ Class not found: {class_id}")
            return Response(
                {"error": "Clase no encontrada"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            print(f"❌ Unexpected error in stats permissions: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return Response(
                {"error": f"Error interno: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        print(f"=== PROCESSING STATS ===")
        print(f"Period ID: {period_id}")
        print(f"Base queryset count: {Attendance.objects.filter(class_instance_id=class_id).count()}")
        
        # Construir query base
        queryset = Attendance.objects.filter(class_instance_id=class_id)
        
        if period_id:
            queryset = queryset.filter(period_id=period_id)
            print(f"Filtered queryset count: {queryset.count()}")
        
        # Si es estudiante, filtrar solo sus datos
        if request.user.user_type == 'student':
            try:
                queryset = queryset.filter(student=request.user.student_profile)
                print(f"Student filtered queryset count: {queryset.count()}")
            except Exception as e:
                print(f"❌ Error filtrando datos de estudiante: {str(e)}")
                return Response(
                    {"error": "Error accediendo a datos de estudiante"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        # Calcular estadísticas por estudiante
        stats = []
        students = class_instance.students.all()
        print(f"Total students in class: {students.count()}")
        
        # Si es estudiante, solo mostrar sus estadísticas
        if request.user.user_type == 'student':
            try:
                students = students.filter(id=request.user.student_profile.id)
                print(f"Filtered students count: {students.count()}")
            except Exception as e:
                print(f"❌ Error filtrando estudiantes: {str(e)}")
                return Response(
                    {"error": "Error accediendo a datos de estudiante"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        for student in students:
            try:
                student_attendances = queryset.filter(student=student)
                print(f"Processing student {student.id}: {student.first_name} {student.last_name}")
                print(f"Student attendances count: {student_attendances.count()}")
                
                # CORRECCIÓN: Usar estados de BD correctos
                present_count = student_attendances.filter(status='presente').count()
                absent_count = student_attendances.filter(status='falta').count()
                late_count = student_attendances.filter(status='tardanza').count()
                total_days = student_attendances.count()
                
                print(f"Counts - Present: {present_count}, Absent: {absent_count}, Late: {late_count}, Total: {total_days}")
                
                if total_days > 0:
                    # Considerar presente y tardanza como asistencia efectiva
                    attendance_percentage = ((present_count + late_count) * 100) / total_days
                else:
                    attendance_percentage = 0
                
                print(f"Attendance percentage: {attendance_percentage}")
                
                stats.append({
                    'student_id': student.id,
                    'student_name': f"{student.first_name} {student.last_name}",
                    'present_count': present_count,
                    'absent_count': absent_count,
                    'late_count': late_count,
                    'total_days': total_days,
                    'attendance_percentage': round(attendance_percentage, 2)
                })
                
            except Exception as e:
                print(f"❌ Error processing student {student.id}: {str(e)}")
                import traceback
                print(traceback.format_exc())
                continue
        
        print(f"Final stats count: {len(stats)}")
        serializer = AttendanceStatsSerializer(stats, many=True)
        return Response(serializer.data)


class ParticipationViewSet(viewsets.ModelViewSet):
    queryset = Participation.objects.all()
    serializer_class = ParticipationSerializer
    permission_classes = [AttendanceParticipationPermission]
    
    def get_queryset(self):
        """Filtrar participaciones según el tipo de usuario"""
        user = self.request.user
        
        if user.user_type == 'admin':
            return Participation.objects.all()
        
        elif user.user_type == 'teacher':
            try:
                teacher_profile = user.teacher_profile
                return Participation.objects.filter(class_instance__teacher=teacher_profile)
            except:
                return Participation.objects.none()
        
        elif user.user_type == 'student':
            try:
                student_profile = user.student_profile
                return Participation.objects.filter(student=student_profile)
            except:
                return Participation.objects.none()
        
        return Participation.objects.none()
    
    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        """Crear múltiples registros de participación para un día - CORREGIDO"""
        serializer = ParticipationBulkSerializer(data=request.data)
        
        if serializer.is_valid():
            class_id = serializer.validated_data['class_instance']
            period_id = serializer.validated_data['period']
            date = serializer.validated_data['date']
            participations_data = serializer.validated_data['participations']
            
            try:
                # Verificar permisos
                class_instance = Class.objects.get(id=class_id)
                if request.user.user_type == 'teacher':
                    teacher_profile = request.user.teacher_profile
                    if class_instance.teacher != teacher_profile:
                        return Response(
                            {"error": "No tienes permisos para esta clase"},
                            status=status.HTTP_403_FORBIDDEN
                        )
                elif request.user.user_type != 'admin':
                    return Response(
                        {"error": "No tienes permisos para realizar esta acción"},
                        status=status.HTTP_403_FORBIDDEN
                    )
                
                period = Period.objects.get(id=period_id)
                
                # Verificar que el período está asignado a la clase
                if not class_instance.periods.filter(id=period.id).exists():
                    return Response(
                        {"error": "El período no está asignado a esta clase"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                # CORRECCIÓN: Mapeo más robusto Frontend -> Backend
                level_mapping = {
                    'high': 'alta',
                    'medium': 'media', 
                    'low': 'baja',
                    # También mantener compatibilidad con valores ya en español
                    'alta': 'alta',
                    'media': 'media',
                    'baja': 'baja'
                }
                
                print(f"=== DEBUG PARTICIPATION BULK CREATE ===")
                print(f"Clase: {class_id}, Período: {period_id}, Fecha: {date}")
                print(f"Datos recibidos: {participations_data}")
                
                with transaction.atomic():
                    created_participations = []
                    
                    for participation_data in participations_data:
                        student_id = participation_data['student_id']
                        frontend_level = participation_data['level']
                        
                        # Convertir nivel de frontend a backend
                        backend_level = level_mapping.get(frontend_level, 'media')  # Default a 'media'
                        
                        print(f"Estudiante {student_id}: {frontend_level} -> {backend_level}")
                        
                        # Verificar que el estudiante existe y está inscrito
                        try:
                            student = StudentProfile.objects.get(id=student_id)
                            if not class_instance.students.filter(id=student.id).exists():
                                print(f"⚠️ Estudiante {student_id} no está inscrito en la clase")
                                continue
                        except StudentProfile.DoesNotExist:
                            print(f"⚠️ Estudiante {student_id} no existe")
                            continue
                        
                        # Crear o actualizar participación
                        participation, created = Participation.objects.update_or_create(
                            class_instance=class_instance,
                            student=student,
                            period=period,
                            date=date,
                            defaults={'level': backend_level}
                        )
                        
                        print(f"Participación {'creada' if created else 'actualizada'}: {participation.id}")
                        created_participations.append(participation)
                
                # Serializar respuesta con mapeo inverso Backend -> Frontend
                response_data = []
                backend_to_frontend = {
                    'alta': 'high',
                    'media': 'medium',
                    'baja': 'low'
                }
                
                for participation in created_participations:
                    participation_dict = ParticipationSerializer(participation).data
                    # Convertir nivel de backend a frontend para la respuesta
                    participation_dict['level'] = backend_to_frontend.get(
                        participation_dict['level'], 
                        participation_dict['level']
                    )
                    response_data.append(participation_dict)
                
                print(f"Respuesta enviada: {len(response_data)} participaciones")
                return Response(response_data, status=status.HTTP_201_CREATED)
                
            except Class.DoesNotExist:
                return Response(
                    {"error": "Clase no encontrada"},
                    status=status.HTTP_404_NOT_FOUND
                )
            except Period.DoesNotExist:
                return Response(
                    {"error": "Período no encontrado"},
                    status=status.HTTP_404_NOT_FOUND
                )
            except Exception as e:
                print(f"❌ Error en bulk_create participación: {str(e)}")
                import traceback
                print(traceback.format_exc())
                return Response(
                    {"error": f"Error al crear participaciones: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        print(f"❌ Errores de validación: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def by_class_and_period(self, request):
        """Obtener participaciones por clase y período - CORREGIDO"""
        class_id = request.query_params.get('class_id')
        period_id = request.query_params.get('period_id')
        date_param = request.query_params.get('date')
        
        if not class_id or not period_id:
            return Response(
                {"error": "class_id y period_id son requeridos"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        print(f"=== DEBUG PARTICIPATION BY_CLASS_AND_PERIOD ===")
        print(f"Clase: {class_id}, Período: {period_id}, Fecha: {date_param}")
        
        queryset = self.get_queryset().filter(
            class_instance_id=class_id,
            period_id=period_id
        )
        
        if date_param:
            try:
                date_obj = datetime.strptime(date_param, '%Y-%m-%d').date()
                queryset = queryset.filter(date=date_obj)
            except ValueError:
                return Response(
                    {"error": "Formato de fecha inválido. Use YYYY-MM-DD"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        print(f"Participaciones encontradas: {queryset.count()}")
        
        # CORRECCIÓN: Mapeo consistente backend -> frontend
        backend_to_frontend = {
            'alta': 'high',
            'media': 'medium',
            'baja': 'low'
        }
        
        # Obtener datos y mapear niveles
        response_data = []
        for participation in queryset:
            participation_dict = self.get_serializer(participation).data
            
            # Convertir nivel de backend a frontend
            original_level = participation_dict['level']
            mapped_level = backend_to_frontend.get(original_level, original_level)
            participation_dict['level'] = mapped_level
            
            print(f"Participación ID {participation.id}: {original_level} -> {mapped_level}")
            response_data.append(participation_dict)
        
        print(f"Respuesta mapeada: {len(response_data)} participaciones")
        return Response(response_data)
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Obtener estadísticas de participación - MÉTODO CORREGIDO"""
        class_id = request.query_params.get('class_id')
        period_id = request.query_params.get('period_id')
        
        if not class_id:
            return Response(
                {"error": "class_id es requerido"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        print(f"=== DEBUG PARTICIPATION STATS PERMISSIONS ===")
        print(f"User ID: {request.user.id}")
        print(f"User type: {request.user.user_type}")
        print(f"Class ID: {class_id}")
        print(f"Period ID: {period_id}")
        
        # Verificar permisos
        try:
            class_instance = Class.objects.get(id=class_id)
            print(f"Class teacher ID: {class_instance.teacher.id if class_instance.teacher else 'None'}")
            
            if request.user.user_type == 'teacher':
                try:
                    teacher_profile = request.user.teacher_profile
                    print(f"Teacher profile ID: {teacher_profile.id}")
                    
                    if class_instance.teacher != teacher_profile:
                        print(f"❌ Permission denied: {class_instance.teacher.id} != {teacher_profile.id}")
                        return Response(
                            {"error": "No tienes permisos para esta clase"},
                            status=status.HTTP_403_FORBIDDEN
                        )
                    else:
                        print(f"✅ Permission granted: Teacher owns this class")
                except Exception as e:
                    print(f"❌ Error verificando permisos de profesor: {str(e)}")
                    import traceback
                    print(traceback.format_exc())
                    return Response(
                        {"error": f"Error de permisos: {str(e)}"},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
            elif request.user.user_type == 'student':
                try:
                    student_profile = request.user.student_profile
                    print(f"Student profile ID: {student_profile.id}")
                    
                    if not class_instance.students.filter(id=student_profile.id).exists():
                        print(f"❌ Permission denied: Student not enrolled in class")
                        return Response(
                            {"error": "No estás inscrito en esta clase"},
                            status=status.HTTP_403_FORBIDDEN
                        )
                    else:
                        print(f"✅ Permission granted: Student enrolled in class")
                except Exception as e:
                    print(f"❌ Error verificando permisos de estudiante: {str(e)}")
                    import traceback
                    print(traceback.format_exc())
                    return Response(
                        {"error": f"Error de permisos: {str(e)}"},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
            elif request.user.user_type != 'admin':
                print(f"❌ Permission denied: Invalid user type {request.user.user_type}")
                return Response(
                    {"error": "No tienes permisos para realizar esta acción"},
                    status=status.HTTP_403_FORBIDDEN
                )
            else:
                print(f"✅ Permission granted: Admin user")
                
        except Class.DoesNotExist:
            print(f"❌ Class not found: {class_id}")
            return Response(
                {"error": "Clase no encontrada"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            print(f"❌ Unexpected error in participation stats permissions: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return Response(
                {"error": f"Error interno: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        print(f"=== PROCESSING PARTICIPATION STATS ===")
        
        # Construir query base
        queryset = Participation.objects.filter(class_instance_id=class_id)
        print(f"Base queryset count: {queryset.count()}")
        
        if period_id:
            queryset = queryset.filter(period_id=period_id)
            print(f"Filtered queryset count: {queryset.count()}")
        
        # Si es estudiante, filtrar solo sus datos
        if request.user.user_type == 'student':
            try:
                queryset = queryset.filter(student=request.user.student_profile)
                print(f"Student filtered queryset count: {queryset.count()}")
            except Exception as e:
                print(f"❌ Error filtrando datos de participación de estudiante: {str(e)}")
                return Response(
                    {"error": "Error accediendo a datos de estudiante"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        # Debug: Verificar qué niveles hay en la BD
        levels_in_db = list(queryset.values_list('level', flat=True).distinct())
        print(f"Niveles encontrados en BD: {levels_in_db}")
        
        # DETECCIÓN AUTOMÁTICA: Verificar si la BD usa inglés o español
        has_spanish = any(level in ['alta', 'media', 'baja'] for level in levels_in_db)
        has_english = any(level in ['high', 'medium', 'low'] for level in levels_in_db)
        
        print(f"BD usa español: {has_spanish}, BD usa inglés: {has_english}")
        
        # Calcular estadísticas por estudiante
        stats = []
        students = class_instance.students.all()
        print(f"Total students in class: {students.count()}")
        
        # Si es estudiante, solo mostrar sus estadísticas
        if request.user.user_type == 'student':
            try:
                students = students.filter(id=request.user.student_profile.id)
                print(f"Filtered students count: {students.count()}")
            except Exception as e:
                print(f"❌ Error filtrando estudiantes: {str(e)}")
                return Response(
                    {"error": "Error accediendo a datos de estudiante"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        for student in students:
            try:
                student_participations = queryset.filter(student=student)
                print(f"Processing student {student.id}: {student.first_name} {student.last_name}")
                print(f"Student participations count: {student_participations.count()}")
                
                # ADAPTACIÓN AUTOMÁTICA: Usar los valores correctos según lo que esté en la BD
                if has_spanish:
                    # BD usa español
                    high_count = student_participations.filter(level='alta').count()
                    medium_count = student_participations.filter(level='media').count()
                    low_count = student_participations.filter(level='baja').count()
                    print(f"Usando niveles en español")
                else:
                    # BD usa inglés (mantener compatibilidad)
                    high_count = student_participations.filter(level='high').count()
                    medium_count = student_participations.filter(level='medium').count()
                    low_count = student_participations.filter(level='low').count()
                    print(f"Usando niveles en inglés")
                
                total_days = student_participations.count()
                
                print(f"Counts - High: {high_count}, Medium: {medium_count}, Low: {low_count}, Total: {total_days}")
                
                if total_days > 0:
                    # Calcular promedio según la fórmula: Alta=3, Media=2, Baja=1
                    average_score = ((high_count * 3) + (medium_count * 2) + (low_count * 1)) / total_days
                    
                    # Determinar nivel promedio
                    if 0 <= average_score < 1:
                        average_level = 'Baja'
                    elif 1 <= average_score < 2:
                        average_level = 'Media'
                    elif 2 <= average_score <= 3:
                        average_level = 'Alta'
                else:
                    average_score = 0
                    # Caso extremo (no debería pasar)
                    average_level = 'Sin datos'
                
                print(f"Average score: {average_score}, Average level: {average_level}")
                
                stats.append({
                    'student_id': student.id,
                    'student_name': f"{student.first_name} {student.last_name}",
                    'high_count': high_count,
                    'medium_count': medium_count,
                    'low_count': low_count,
                    'total_days': total_days,
                    'average_score': round(average_score, 2),
                    'average_level': average_level
                })
                
            except Exception as e:
                print(f"❌ Error processing student {student.id}: {str(e)}")
                import traceback
                print(traceback.format_exc())
                continue
        
        print(f"Final participation stats count: {len(stats)}")
        serializer = ParticipationStatsSerializer(stats, many=True)
        return Response(serializer.data)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def debug_student_classes(request):
    """Vista de depuración para verificar las clases de un estudiante"""
    try:
        user = request.user
        if user.user_type != 'student':
            return JsonResponse({
                'error': 'El usuario no es un estudiante',
                'user_type': user.user_type
            })
        
        # Obtener el perfil de estudiante
        try:
            student_profile = user.student_profile
            student_id = student_profile.id
        except Exception as e:
            return JsonResponse({
                'error': f'Error al obtener perfil de estudiante: {str(e)}',
                'user_id': user.id
            })
        
        # Obtener clases directamente
        from .models import Class
        classes = Class.objects.filter(students=student_profile)
        
        class_data = [{
            'id': c.id,
            'name': c.name,
            'code': c.code,
            'subject': c.subject.name if c.subject else None,
            'course': c.course.name if c.course else None,
            'group': c.group.name if c.group else None,
            'year': c.year,
            'teacher': c.teacher.first_name if c.teacher else None
        } for c in classes]
        
        # Verificar la relación many-to-many directamente
        from django.db import connection
        cursor = connection.cursor()
        cursor.execute("""
            SELECT * FROM academic_class_students 
            WHERE studentprofile_id=%s
        """, [student_id])
        relations = cursor.fetchall()
        
        # Verificar problemas de relaciones
        if not relations and student_id:
            print(f"⚠️ No hay relaciones para el estudiante {student_id} en academic_class_students")
            
            # Obtener todas las clases
            cursor.execute("SELECT id, name FROM academic_class")
            all_classes = cursor.fetchall()
            
            print(f"Clases disponibles: {all_classes}")
            
            # Obtener el nombre de la tabla y los campos
            class_model = Class()
            table_name = class_model._meta.get_field('students').m2m_db_table()
            class_field = class_model._meta.get_field('students').m2m_column_name()
            student_field = class_model._meta.get_field('students').m2m_reverse_name()
            
            print(f"Tabla M2M: {table_name}, Campo clase: {class_field}, Campo estudiante: {student_field}")
        
        return JsonResponse({
            'student_id': student_id,
            'username': user.username,
            'classes_count': len(class_data),
            'classes': class_data,
            'raw_relations': relations,
        })
        
    except Exception as e:
        return JsonResponse({
            'error': str(e)
        }, status=500)