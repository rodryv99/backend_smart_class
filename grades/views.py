# grades/views.py
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from django.db import transaction, connection
from django.db.models import Avg, Count, Max, Min
from django.core.cache import cache
from .models import Grade, FinalGrade
from .serializers import (
    GradeSerializer, GradeBulkSerializer, FinalGradeSerializer,
    GradeStatsSerializer, ClassGradesSummarySerializer, StudentGradesSerializer
)
from academic.models import Class, Period
from users.models import StudentProfile
import time
import hashlib

class GradePermission(permissions.BasePermission):
    """
    Permiso personalizado para notas:
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


def clear_grade_cache(class_id, period_id=None):
    """Función helper para limpiar caché relacionado con notas"""
    cache_keys = [
        f'grade_stats_{class_id}',
        f'final_grades_{class_id}',
        f'grade_data_{class_id}_{period_id}' if period_id else None,
    ]
    
    # Limpiar las claves específicas
    for key in cache_keys:
        if key:
            cache.delete(key)
    
    # Limpiar también todas las claves que contengan el class_id
    if hasattr(cache, '_cache'):
        keys_to_delete = []
        for key in cache._cache.keys():
            if str(class_id) in str(key):
                keys_to_delete.append(key)
        for key in keys_to_delete:
            cache.delete(key)


class GradeViewSet(viewsets.ModelViewSet):
    queryset = Grade.objects.all()
    serializer_class = GradeSerializer
    permission_classes = [GradePermission]
    
    def get_queryset(self):
        """Filtrar notas según el tipo de usuario"""
        user = self.request.user
        
        if user.user_type == 'admin':
            return Grade.objects.all()
        
        elif user.user_type == 'teacher':
            try:
                teacher_profile = user.teacher_profile
                return Grade.objects.filter(class_instance__teacher=teacher_profile)
            except:
                return Grade.objects.none()
        
        elif user.user_type == 'student':
            try:
                student_profile = user.student_profile
                return Grade.objects.filter(student=student_profile)
            except:
                return Grade.objects.none()
        
        return Grade.objects.none()
    
    def perform_create(self, serializer):
        """Al crear una nota, actualizar automáticamente la nota final"""
        grade = serializer.save()
        # Limpiar caché
        clear_grade_cache(grade.class_instance.id, grade.period.id)
        # Actualizar nota final del estudiante
        FinalGrade.update_final_grade_for_student(
            grade.student, 
            grade.class_instance
        )
    
    def perform_update(self, serializer):
        """Al actualizar una nota, actualizar automáticamente la nota final"""
        grade = serializer.save()
        # Limpiar caché
        clear_grade_cache(grade.class_instance.id, grade.period.id)
        # Actualizar nota final del estudiante
        FinalGrade.update_final_grade_for_student(
            grade.student, 
            grade.class_instance
        )
    
    def perform_destroy(self, instance):
        """Al eliminar una nota, actualizar automáticamente la nota final"""
        student = instance.student
        class_instance = instance.class_instance
        class_id = class_instance.id
        period_id = instance.period.id
        
        super().perform_destroy(instance)
        
        # Limpiar caché
        clear_grade_cache(class_id, period_id)
        # Actualizar nota final del estudiante
        FinalGrade.update_final_grade_for_student(student, class_instance)
    
    @action(detail=False, methods=['post'])
    def bulk_create_update(self, request):
        """Crear o actualizar múltiples notas para una clase y período"""
        serializer = GradeBulkSerializer(data=request.data)
        
        if serializer.is_valid():
            class_id = serializer.validated_data['class_instance']
            period_id = serializer.validated_data['period']
            grades_data = serializer.validated_data['grades']
            
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
                
                # LIMPIAR CACHÉ ANTES DE LA OPERACIÓN
                clear_grade_cache(class_id, period_id)
                
                with transaction.atomic():
                    created_grades = []
                    updated_students = set()
                    
                    for grade_data in grades_data:
                        student_id = grade_data['student_id']
                        
                        # Verificar que el estudiante está inscrito en la clase
                        if not class_instance.students.filter(id=student_id).exists():
                            return Response(
                                {"error": f"El estudiante {student_id} no está inscrito en esta clase"},
                                status=status.HTTP_400_BAD_REQUEST
                            )
                        
                        # CORRECCIÓN CRÍTICA: Convertir student_id a entero y usar get_or_create
                        try:
                            student_profile = StudentProfile.objects.get(id=int(student_id))
                        except StudentProfile.DoesNotExist:
                            return Response(
                                {"error": f"Estudiante {student_id} no encontrado"},
                                status=status.HTTP_400_BAD_REQUEST
                            )
                        
                        # Primero intentar obtener el registro existente
                        try:
                            grade = Grade.objects.get(
                                class_instance=class_instance,
                                student=student_profile,
                                period=period
                            )
                            # Actualizar valores existentes
                            grade.ser = float(grade_data['ser'])
                            grade.saber = float(grade_data['saber'])
                            grade.hacer = float(grade_data['hacer'])
                            grade.decidir = float(grade_data['decidir'])
                            grade.autoevaluacion = float(grade_data['autoevaluacion'])
                            grade.save()
                            created = False
                            print(f"DEBUG BULK: Nota ACTUALIZADA para estudiante {student_id}: {grade.nota_total}")
                        except Grade.DoesNotExist:
                            # Crear nuevo registro
                            grade = Grade.objects.create(
                                class_instance=class_instance,
                                student=student_profile,
                                period=period,
                                ser=float(grade_data['ser']),
                                saber=float(grade_data['saber']),
                                hacer=float(grade_data['hacer']),
                                decidir=float(grade_data['decidir']),
                                autoevaluacion=float(grade_data['autoevaluacion'])
                            )
                            created = True
                            print(f"DEBUG BULK: Nota CREADA para estudiante {student_id}: {grade.nota_total}")
                        
                        created_grades.append(grade)
                        updated_students.add(grade.student)
                
                # FUNCIÓN PARA EJECUTAR DESPUÉS DEL COMMIT
                def post_commit_actions():
                    try:
                        print("DEBUG BULK: Ejecutando acciones post-commit...")
                        time.sleep(0.2)  # Dar tiempo para que se procesen los signals
                        
                        # Limpiar caché otra vez después del commit
                        clear_grade_cache(class_id, period_id)
                        
                        # Forzar recálculo de notas finales
                        for student in updated_students:
                            final_value = FinalGrade.update_final_grade_for_student(student, class_instance)
                            print(f"DEBUG BULK: {student.first_name} {student.last_name} - Nota final: {final_value}")
                        
                        print(f"DEBUG BULK: Post-commit completado para {len(updated_students)} estudiantes")
                    except Exception as e:
                        print(f"ERROR BULK POST-COMMIT: {str(e)}")
                
                # Programar acciones post-commit
                transaction.on_commit(post_commit_actions)
                
                # Serializar respuesta
                response_serializer = GradeSerializer(created_grades, many=True)
                print(f"DEBUG BULK: Operación completada exitosamente para {len(created_grades)} notas")
                return Response(response_serializer.data, status=status.HTTP_201_CREATED)
                
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
                print(f"ERROR BULK: Error al procesar notas: {str(e)}")
                return Response(
                    {"error": f"Error al procesar notas: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def by_class_and_period(self, request):
        """Obtener notas por clase y período"""
        class_id = request.query_params.get('class_id')
        period_id = request.query_params.get('period_id')
        
        if not class_id or not period_id:
            return Response(
                {"error": "class_id y period_id son requeridos"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Verificar permisos
        try:
            class_instance = Class.objects.get(id=class_id)
            if request.user.user_type == 'teacher':
                teacher_profile = request.user.teacher_profile
                if class_instance.teacher != teacher_profile:
                    return Response(
                        {"error": "No tienes permisos para esta clase"},
                        status=status.HTTP_403_FORBIDDEN
                    )
            elif request.user.user_type == 'student':
                student_profile = request.user.student_profile
                if not class_instance.students.filter(id=student_profile.id).exists():
                    return Response(
                        {"error": "No estás inscrito en esta clase"},
                        status=status.HTTP_403_FORBIDDEN
                    )
            elif request.user.user_type != 'admin':
                return Response(
                    {"error": "No tienes permisos para realizar esta acción"},
                    status=status.HTTP_403_FORBIDDEN
                )
        except Class.DoesNotExist:
            return Response(
                {"error": "Clase no encontrada"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # FORZAR REFRESH DE BD
        connection.close()
        
        queryset = self.get_queryset().filter(
            class_instance_id=class_id,
            period_id=period_id
        )
        
        # Si es estudiante, filtrar solo sus datos
        if request.user.user_type == 'student':
            queryset = queryset.filter(student=request.user.student_profile)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Obtener estadísticas de notas"""
        class_id = request.query_params.get('class_id')
        period_id = request.query_params.get('period_id')
        force_fresh = request.query_params.get('_t')  # Cache bust parameter
        
        print(f"DEBUG STATS: Solicitando estadísticas para clase {class_id}, período {period_id}, force_fresh: {force_fresh}")
        
        if not class_id:
            return Response(
                {"error": "class_id es requerido"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Verificar permisos
        try:
            class_instance = Class.objects.get(id=class_id)
            if request.user.user_type == 'teacher':
                teacher_profile = request.user.teacher_profile
                if class_instance.teacher != teacher_profile:
                    return Response(
                        {"error": "No tienes permisos para esta clase"},
                        status=status.HTTP_403_FORBIDDEN
                    )
            elif request.user.user_type == 'student':
                student_profile = request.user.student_profile
                if not class_instance.students.filter(id=student_profile.id).exists():
                    return Response(
                        {"error": "No estás inscrito en esta clase"},
                        status=status.HTTP_403_FORBIDDEN
                    )
            elif request.user.user_type != 'admin':
                return Response(
                    {"error": "No tienes permisos para realizar esta acción"},
                    status=status.HTTP_403_FORBIDDEN
                )
        except Class.DoesNotExist:
            return Response(
                {"error": "Clase no encontrada"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Si se solicita datos frescos, limpiar caché
        if force_fresh:
            clear_grade_cache(class_id, period_id)
            time.sleep(0.1)  # Pequeña pausa después de limpiar caché
        
        # CAMBIO CRÍTICO: FORZAR NUEVA CONEXIÓN Y REFRESH DESDE BD
        from django.db import connections
        connections.close_all()  # Cerrar todas las conexiones
        
        # USAR RAW SQL PARA EVITAR CUALQUIER CACHE DEL ORM
        from django.db import connection
        
        # Construir query SQL directo
        if period_id:
            sql = """
                SELECT 
                    g.student_id,
                    CONCAT(s.first_name, ' ', s.last_name) as student_name,
                    AVG(g.ser) as avg_ser,
                    AVG(g.saber) as avg_saber,
                    AVG(g.hacer) as avg_hacer,
                    AVG(g.decidir) as avg_decidir,
                    AVG(g.autoevaluacion) as avg_autoevaluacion,
                    AVG(g.nota_total) as avg_total,
                    SUM(CASE WHEN g.estado = 'approved' THEN 1 ELSE 0 END) as approved_count,
                    SUM(CASE WHEN g.estado = 'failed' THEN 1 ELSE 0 END) as failed_count,
                    COUNT(*) as total_periods
                FROM grades_grade g
                JOIN users_studentprofile s ON g.student_id = s.id
                WHERE g.class_instance_id = %s AND g.period_id = %s
                GROUP BY g.student_id, s.first_name, s.last_name
                ORDER BY s.first_name
            """
            params = [class_id, period_id]
        else:
            sql = """
                SELECT 
                    g.student_id,
                    CONCAT(s.first_name, ' ', s.last_name) as student_name,
                    AVG(g.ser) as avg_ser,
                    AVG(g.saber) as avg_saber,
                    AVG(g.hacer) as avg_hacer,
                    AVG(g.decidir) as avg_decidir,
                    AVG(g.autoevaluacion) as avg_autoevaluacion,
                    AVG(g.nota_total) as avg_total,
                    SUM(CASE WHEN g.estado = 'approved' THEN 1 ELSE 0 END) as approved_count,
                    SUM(CASE WHEN g.estado = 'failed' THEN 1 ELSE 0 END) as failed_count,
                    COUNT(*) as total_periods
                FROM grades_grade g
                JOIN users_studentprofile s ON g.student_id = s.id
                WHERE g.class_instance_id = %s
                GROUP BY g.student_id, s.first_name, s.last_name
                ORDER BY s.first_name
            """
            params = [class_id]
        
        # Si es estudiante, filtrar solo sus datos
        if request.user.user_type == 'student':
            sql += " AND g.student_id = %s"
            params.append(request.user.student_profile.id)
        
        print(f"DEBUG STATS: Ejecutando SQL directo: {sql}")
        print(f"DEBUG STATS: Parámetros: {params}")
        
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            columns = [col[0] for col in cursor.description]
            results = cursor.fetchall()
        
        print(f"DEBUG STATS: SQL devolvió {len(results)} filas")
        
        # Convertir resultados a formato esperado
        stats = []
        for row in results:
            row_dict = dict(zip(columns, row))
            student_stat = {
                'student_id': int(row_dict['student_id']),
                'student_name': row_dict['student_name'],
                'avg_ser': round(float(row_dict['avg_ser'] or 0), 2),
                'avg_saber': round(float(row_dict['avg_saber'] or 0), 2),
                'avg_hacer': round(float(row_dict['avg_hacer'] or 0), 2),
                'avg_decidir': round(float(row_dict['avg_decidir'] or 0), 2),
                'avg_autoevaluacion': round(float(row_dict['avg_autoevaluacion'] or 0), 2),
                'avg_total': round(float(row_dict['avg_total'] or 0), 2),
                'approved_count': int(row_dict['approved_count'] or 0),
                'failed_count': int(row_dict['failed_count'] or 0),
                'total_periods': int(row_dict['total_periods'] or 0)
            }
            
            print(f"DEBUG STATS: {student_stat['student_name']} - Promedio SQL directo: {student_stat['avg_total']:.2f}")
            stats.append(student_stat)
        
        print(f"DEBUG STATS: Devolviendo estadísticas para {len(stats)} estudiantes (SQL directo)")
        return Response(stats)


class FinalGradeViewSet(viewsets.ModelViewSet):
    queryset = FinalGrade.objects.all()
    serializer_class = FinalGradeSerializer
    permission_classes = [GradePermission]
    
    def get_queryset(self):
        """Filtrar notas finales según el tipo de usuario"""
        user = self.request.user
        
        if user.user_type == 'admin':
            return FinalGrade.objects.all()
        
        elif user.user_type == 'teacher':
            try:
                teacher_profile = user.teacher_profile
                return FinalGrade.objects.filter(class_instance__teacher=teacher_profile)
            except:
                return FinalGrade.objects.none()
        
        elif user.user_type == 'student':
            try:
                student_profile = user.student_profile
                return FinalGrade.objects.filter(student=student_profile)
            except:
                return FinalGrade.objects.none()
        
        return FinalGrade.objects.none()
    
    @action(detail=False, methods=['get'])
    def by_class(self, request):
        """Obtener notas finales por clase"""
        class_id = request.query_params.get('class_id')
        force_fresh = request.query_params.get('_t')  # Cache bust parameter
        
        # FORZAR REFRESH DE CONEXIÓN
        connection.close()
        
        print(f"DEBUG FINAL: Solicitando notas finales para clase {class_id}, force_fresh: {force_fresh}")
        
        if not class_id:
            return Response(
                {"error": "class_id es requerido"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Verificar permisos
        try:
            class_instance = Class.objects.get(id=class_id)
            if request.user.user_type == 'teacher':
                teacher_profile = request.user.teacher_profile
                if class_instance.teacher != teacher_profile:
                    return Response(
                        {"error": "No tienes permisos para esta clase"},
                        status=status.HTTP_403_FORBIDDEN
                    )
            elif request.user.user_type == 'student':
                student_profile = request.user.student_profile
                if not class_instance.students.filter(id=student_profile.id).exists():
                    return Response(
                        {"error": "No estás inscrito en esta clase"},
                        status=status.HTTP_403_FORBIDDEN
                    )
            elif request.user.user_type != 'admin':
                return Response(
                    {"error": "No tienes permisos para realizar esta acción"},
                    status=status.HTTP_403_FORBIDDEN
                )
        except Class.DoesNotExist:
            return Response(
                {"error": "Clase no encontrada"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Si se solicita datos frescos, limpiar caché
        if force_fresh:
            clear_grade_cache(class_id)
            time.sleep(0.1)  # Pequeña pausa después de limpiar caché
        
        queryset = self.get_queryset().filter(class_instance_id=class_id)
        
        # Si es estudiante, filtrar solo sus datos
        if request.user.user_type == 'student':
            queryset = queryset.filter(student=request.user.student_profile)
        
        print(f"DEBUG FINAL: Encontradas {queryset.count()} notas finales")
        
        # Forzar evaluación y mostrar debug
        final_grades = list(queryset)
        for fg in final_grades[:3]:
            print(f"DEBUG FINAL: {fg.student.first_name} {fg.student.last_name} - Nota final: {fg.nota_final}")
        
        serializer = self.get_serializer(final_grades, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def recalculate_all(self, request):
        """Recalcular todas las notas finales de una clase"""
        class_id = request.data.get('class_id')
        
        if not class_id:
            return Response(
                {"error": "class_id es requerido"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
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
            
            print(f"DEBUG RECALC: Recalculando todas las notas finales para clase {class_id}")
            
            # Limpiar caché antes del recálculo
            clear_grade_cache(class_id)
            
            # Recalcular notas finales para todos los estudiantes de la clase
            students = class_instance.students.all()
            updated_count = 0
            
            with transaction.atomic():
                for student in students:
                    final_value = FinalGrade.update_final_grade_for_student(student, class_instance)
                    print(f"DEBUG RECALC: {student.first_name} {student.last_name} - Nota final: {final_value}")
                    updated_count += 1
            
            # Limpiar caché después del recálculo
            clear_grade_cache(class_id)
            
            print(f"DEBUG RECALC: Recalculadas {updated_count} notas finales")
            
            return Response({
                "message": f"Se recalcularon {updated_count} notas finales",
                "class_id": class_id,
                "updated_count": updated_count
            })
            
        except Class.DoesNotExist:
            return Response(
                {"error": "Clase no encontrada"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            print(f"ERROR RECALC: Error al recalcular notas: {str(e)}")
            return Response(
                {"error": f"Error al recalcular notas: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def student_grades_summary(request, class_id, student_id=None):
    """Vista para obtener resumen completo de notas de un estudiante en una clase"""
    try:
        # Verificar permisos
        class_instance = Class.objects.get(id=class_id)
        
        # Si no se proporciona student_id, usar el del usuario actual (para estudiantes)
        if not student_id:
            if request.user.user_type == 'student':
                student_id = request.user.student_profile.id
            else:
                return Response(
                    {"error": "student_id es requerido"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Verificar permisos específicos
        if request.user.user_type == 'teacher':
            teacher_profile = request.user.teacher_profile
            if class_instance.teacher != teacher_profile:
                return Response(
                    {"error": "No tienes permisos para esta clase"},
                    status=status.HTTP_403_FORBIDDEN
                )
        elif request.user.user_type == 'student':
            if request.user.student_profile.id != int(student_id):
                return Response(
                    {"error": "Solo puedes ver tus propias notas"},
                    status=status.HTTP_403_FORBIDDEN
                )
            if not class_instance.students.filter(id=student_id).exists():
                return Response(
                    {"error": "No estás inscrito en esta clase"},
                    status=status.HTTP_403_FORBIDDEN
                )
        elif request.user.user_type != 'admin':
            return Response(
                {"error": "No tienes permisos para realizar esta acción"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Obtener estudiante
        student = StudentProfile.objects.get(id=student_id)
        
        # Verificar que el estudiante está inscrito en la clase
        if not class_instance.students.filter(id=student.id).exists():
            return Response(
                {"error": "El estudiante no está inscrito en esta clase"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # FORZAR REFRESH DE BD
        connection.close()
        
        # Obtener todas las notas del estudiante en esta clase
        period_grades = Grade.objects.filter(
            student=student,
            class_instance=class_instance
        ).order_by('period__period_type', 'period__number')
        
        # Obtener nota final
        try:
            final_grade = FinalGrade.objects.get(
                student=student,
                class_instance=class_instance
            )
        except FinalGrade.DoesNotExist:
            # Si no existe, crearla
            final_grade = FinalGrade.objects.create(
                student=student,
                class_instance=class_instance
            )
            final_grade.calculate_final_grade()
        
        # Preparar respuesta
        response_data = {
            'student_id': student.id,
            'student_name': f"{student.first_name} {student.last_name}",
            'class_id': class_instance.id,
            'class_name': class_instance.name,
            'period_grades': GradeSerializer(period_grades, many=True).data,
            'final_grade': FinalGradeSerializer(final_grade).data,
            'can_view_details': True,
            'can_edit_grades': request.user.user_type in ['admin', 'teacher']
        }
        
        return Response(response_data)
        
    except Class.DoesNotExist:
        return Response(
            {"error": "Clase no encontrada"},
            status=status.HTTP_404_NOT_FOUND
        )
    except StudentProfile.DoesNotExist:
        return Response(
            {"error": "Estudiante no encontrado"},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {"error": f"Error al obtener datos: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def class_grades_summary(request, class_id):
    """Vista para obtener resumen de notas de toda una clase"""
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
        elif request.user.user_type == 'student':
            return Response(
                {"error": "Los estudiantes no pueden ver el resumen completo de la clase"},
                status=status.HTTP_403_FORBIDDEN
            )
        elif request.user.user_type != 'admin':
            return Response(
                {"error": "No tienes permisos para realizar esta acción"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        period_id = request.query_params.get('period_id')
        
        # FORZAR REFRESH DE BD
        connection.close()
        
        # Obtener todas las notas de la clase
        grades_query = Grade.objects.filter(class_instance=class_instance)
        if period_id:
            grades_query = grades_query.filter(period_id=period_id)
        
        # Calcular estadísticas generales
        total_students = class_instance.students.count()
        students_with_grades = grades_query.values('student').distinct().count()
        approved_count = grades_query.filter(estado='approved').count()
        failed_count = grades_query.filter(estado='failed').count()
        
        # Calcular promedios
        stats = grades_query.aggregate(
            avg_grade=Avg('nota_total'),
            max_grade=Max('nota_total'),
            min_grade=Min('nota_total')
        )
        
        response_data = {
            'class_id': class_instance.id,
            'class_name': class_instance.name,
            'period_id': period_id,
            'period_name': None,
            'total_students': total_students,
            'students_with_grades': students_with_grades,
            'approved_count': approved_count,
            'failed_count': failed_count,
            'average_grade': round(stats['avg_grade'] or 0, 2),
            'highest_grade': stats['max_grade'] or 0,
            'lowest_grade': stats['min_grade'] or 0
        }
        
        # Si se especifica un período, agregar información del período
        if period_id:
            try:
                period = Period.objects.get(id=period_id)
                response_data['period_name'] = f"{period.get_period_type_display()} {period.number} - {period.year}"
            except Period.DoesNotExist:
                pass
        
        return Response(response_data)
        
    except Class.DoesNotExist:
        return Response(
            {"error": "Clase no encontrada"},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {"error": f"Error al obtener resumen: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )