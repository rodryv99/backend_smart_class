from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from django.db.models import Avg, Count
from django.db import transaction
import logging

from .models import Prediction, PredictionHistory, MLModel
from .serializers import (
    PredictionSerializer, PredictionHistorySerializer, MLModelSerializer,
    PredictionStatsSerializer, ComparisonStatsSerializer
)
from .ml_service import MLPredictionService
from academic.models import Class
from users.models import StudentProfile
from grades.models import Grade

# Configurar logging
logger = logging.getLogger(__name__)

class PredictionPermission(permissions.BasePermission):
    """
    Permiso personalizado para predicciones:
    - Admin: acceso completo
    - Profesor: solo sus clases
    - Estudiante: solo lectura de sus propias predicciones
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


class PredictionViewSet(viewsets.ModelViewSet):
    queryset = Prediction.objects.all()
    serializer_class = PredictionSerializer
    permission_classes = [PredictionPermission]
    
    def get_queryset(self):
        """Filtrar predicciones según el tipo de usuario"""
        user = self.request.user
        
        if user.user_type == 'admin':
            return Prediction.objects.all()
        
        elif user.user_type == 'teacher':
            try:
                teacher_profile = user.teacher_profile
                return Prediction.objects.filter(class_instance__teacher=teacher_profile)
            except:
                return Prediction.objects.none()
        
        elif user.user_type == 'student':
            try:
                student_profile = user.student_profile
                return Prediction.objects.filter(student=student_profile)
            except:
                return Prediction.objects.none()
        
        return Prediction.objects.none()
    
    @action(detail=False, methods=['get'])
    def by_class(self, request):
        """Obtener predicciones por clase"""
        class_id = request.query_params.get('class_id')
        
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
        
        queryset = self.get_queryset().filter(class_instance_id=class_id)
        
        # Si es estudiante, filtrar solo sus predicciones
        if request.user.user_type == 'student':
            queryset = queryset.filter(student=request.user.student_profile)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def generate_retrospective_predictions(self, request):
        """Generar predicciones retrospectivas para comparar con la realidad"""
        class_id = request.data.get('class_id')
        period_id = request.data.get('period_id')  # Opcional
        
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
            
            # Obtener período objetivo si se especifica
            target_period = None
            if period_id:
                try:
                    from academic.models import Period
                    target_period = Period.objects.get(id=period_id)
                    
                    # Verificar que el período esté asignado a la clase
                    if not class_instance.periods.filter(id=period_id).exists():
                        return Response(
                            {"error": "El período no está asignado a esta clase"},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                except Period.DoesNotExist:
                    return Response(
                        {"error": "Período no encontrado"},
                        status=status.HTTP_404_NOT_FOUND
                    )
            
            # Generar predicciones retrospectivas
            try:
                ml_service = MLPredictionService(class_instance)
                predictions = ml_service.generate_retrospective_predictions(target_period)
                
                # También crear el historial inmediatamente para comparación
                history_created = 0
                for prediction in predictions:
                    # Buscar la nota real para este estudiante y período
                    real_grade = Grade.objects.filter(
                        student=prediction.student,
                        class_instance=class_instance,
                        period=prediction.predicted_period
                    ).first()
                    
                    if real_grade:
                        history = ml_service.create_prediction_history(
                            prediction.student,
                            prediction.predicted_period,
                            real_grade.nota_total
                        )
                        if history:
                            history_created += 1
                
                return Response({
                    "message": f"Predicciones retrospectivas generadas para {len(predictions)} estudiantes",
                    "class_id": class_id,
                    "target_period": str(target_period) if target_period else "último período",
                    "predictions_count": len(predictions),
                    "comparisons_created": history_created
                })
            except Exception as e:
                logger.error(f"Error generating retrospective predictions: {str(e)}")
                return Response(
                    {"error": f"Error al generar predicciones retrospectivas: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
        except Class.DoesNotExist:
            return Response(
                {"error": "Clase no encontrada"},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=False, methods=['post'])
    def update_class_predictions(self, request):
        """Actualizar predicciones para toda una clase (mejorado)"""
        class_id = request.data.get('class_id')
        include_retrospective = request.data.get('include_retrospective', False)
        period_id = request.data.get('period_id')  # Para predicciones retrospectivas
        
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
            
            # Obtener período objetivo si se especifica
            target_period = None
            if include_retrospective and period_id:
                try:
                    from academic.models import Period
                    target_period = Period.objects.get(id=period_id)
                except Period.DoesNotExist:
                    return Response(
                        {"error": "Período no encontrado"},
                        status=status.HTTP_404_NOT_FOUND
                    )
            
            # Actualizar predicciones
            try:
                ml_service = MLPredictionService(class_instance)
                predictions = ml_service.update_predictions_for_class(
                    include_retrospective=include_retrospective,
                    target_period=target_period
                )
                
                return Response({
                    "message": f"Predicciones actualizadas para {len(predictions)} estudiantes",
                    "class_id": class_id,
                    "updated_count": len(predictions),
                    "includes_retrospective": include_retrospective
                })
            except Exception as e:
                logger.error(f"Error updating predictions: {str(e)}")
                return Response(
                    {"error": f"Error al actualizar predicciones: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
        except Class.DoesNotExist:
            return Response(
                {"error": "Clase no encontrada"},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=False, methods=['post'])
    def retrain_model(self, request):
        """Reentrenar el modelo para una clase"""
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
            
            # Reentrenar modelo
            try:
                ml_service = MLPredictionService(class_instance)
                ml_model = ml_service.train_model()
                
                if ml_model:
                    # Actualizar predicciones con el nuevo modelo
                    predictions = ml_service.update_predictions_for_class()
                    
                    return Response({
                        "message": "Modelo reentrenado exitosamente",
                        "model_version": ml_model.model_version,
                        "validation_score": ml_model.validation_score,
                        "mean_absolute_error": ml_model.mean_absolute_error,
                        "updated_predictions": len(predictions)
                    })
                else:
                    return Response(
                        {"error": "No se pudo entrenar el modelo. Verifique que hay suficientes datos históricos."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            except Exception as e:
                logger.error(f"Error retraining model: {str(e)}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                return Response(
                    {"error": f"Error al reentrenar modelo: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
        except Class.DoesNotExist:
            return Response(
                {"error": "Clase no encontrada"},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Obtener estadísticas de predicciones"""
        class_id = request.query_params.get('class_id')
        
        if not class_id:
            return Response(
                {"error": "class_id es requerido"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Verificar permisos (mismo código que en by_class)
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
        
        queryset = self.get_queryset().filter(class_instance_id=class_id)
        
        # Si es estudiante, filtrar solo sus predicciones
        if request.user.user_type == 'student':
            queryset = queryset.filter(student=request.user.student_profile)
        
        # Calcular estadísticas
        stats = queryset.aggregate(
            avg_predicted_grade=Avg('predicted_grade'),
            avg_confidence=Avg('confidence'),
            predictions_count=Count('id')
        )
        
        # Obtener información del modelo activo
        try:
            active_model = MLModel.objects.filter(
                class_instance_id=class_id,
                is_active=True
            ).latest('created_at')
            model_version = active_model.model_version
        except MLModel.DoesNotExist:
            model_version = "Sin modelo"
        
        stats_data = {
            'class_id': int(class_id),
            'class_name': class_instance.name,
            'total_students': class_instance.students.count(),
            'students_with_predictions': queryset.values('student').distinct().count(),
            'avg_predicted_grade': round(stats['avg_predicted_grade'] or 0, 2),
            'avg_confidence': round(stats['avg_confidence'] or 0, 2),
            'model_version': model_version,
            'predictions_count': stats['predictions_count']
        }
        
        serializer = PredictionStatsSerializer(stats_data)
        return Response(serializer.data)


class PredictionHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PredictionHistory.objects.all()
    serializer_class = PredictionHistorySerializer
    permission_classes = [PredictionPermission]
    
    def get_queryset(self):
        """Filtrar historial según el tipo de usuario"""
        user = self.request.user
        
        if user.user_type == 'admin':
            return PredictionHistory.objects.all()
        
        elif user.user_type == 'teacher':
            try:
                teacher_profile = user.teacher_profile
                return PredictionHistory.objects.filter(class_instance__teacher=teacher_profile)
            except:
                return PredictionHistory.objects.none()
        
        elif user.user_type == 'student':
            try:
                student_profile = user.student_profile
                return PredictionHistory.objects.filter(student=student_profile)
            except:
                return PredictionHistory.objects.none()
        
        return PredictionHistory.objects.none()
    
    @action(detail=False, methods=['get'])
    def by_class(self, request):
        """Obtener historial de predicciones por clase"""
        class_id = request.query_params.get('class_id')
        
        if not class_id:
            return Response(
                {"error": "class_id es requerido"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Verificar permisos (mismo código que en PredictionViewSet)
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
        
        queryset = self.get_queryset().filter(class_instance_id=class_id)
        
        # Si es estudiante, filtrar solo su historial
        if request.user.user_type == 'student':
            queryset = queryset.filter(student=request.user.student_profile)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def comparison_stats(self, request):
        """Obtener estadísticas de comparación realidad vs predicción"""
        class_id = request.query_params.get('class_id')
        
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
        
        queryset = self.get_queryset().filter(class_instance_id=class_id)
        
        # Si es estudiante, filtrar solo su historial
        if request.user.user_type == 'student':
            queryset = queryset.filter(student=request.user.student_profile)
        
        # Calcular estadísticas de comparación
        stats = queryset.aggregate(
            avg_absolute_error=Avg('absolute_error'),
            total_comparisons=Count('id')
        )
        
        # Contar predicciones por calidad
        excellent_count = queryset.filter(absolute_error__lte=5).count()
        good_count = queryset.filter(absolute_error__lte=10, absolute_error__gt=5).count()
        poor_count = queryset.filter(absolute_error__gt=15).count()
        
        # Calcular precisión promedio
        total_comparisons = stats['total_comparisons']
        if total_comparisons > 0:
            # Calcular precisión promedio basada en el error porcentual
            accuracy_sum = 0
            for history in queryset:
                if history.actual_grade > 0:
                    error_percentage = (history.absolute_error / history.actual_grade) * 100
                    accuracy = max(0, 100 - error_percentage)
                    accuracy_sum += accuracy
            avg_accuracy = accuracy_sum / total_comparisons if total_comparisons > 0 else 0
        else:
            avg_accuracy = 0
        
        stats_data = {
            'class_id': int(class_id),
            'class_name': class_instance.name,
            'total_comparisons': total_comparisons,
            'avg_absolute_error': round(stats['avg_absolute_error'] or 0, 2),
            'avg_accuracy_percentage': round(avg_accuracy, 2),
            'excellent_predictions': excellent_count,
            'good_predictions': good_count,
            'poor_predictions': poor_count
        }
        
        serializer = ComparisonStatsSerializer(stats_data)
        return Response(serializer.data)