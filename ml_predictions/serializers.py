from rest_framework import serializers
from .models import Prediction, PredictionHistory, MLModel
from academic.serializers import StudentSerializer, PeriodSerializer


class PredictionSerializer(serializers.ModelSerializer):
    """Serializador para predicciones de notas"""
    student_detail = StudentSerializer(source='student', read_only=True)
    period_detail = PeriodSerializer(source='predicted_period', read_only=True)
    class_detail = serializers.SerializerMethodField()
    
    class Meta:
        model = Prediction
        fields = [
            'id', 'student', 'student_detail', 'class_instance', 'class_detail',
            'predicted_period', 'period_detail', 'predicted_grade', 'confidence',
            'avg_previous_grades', 'attendance_percentage', 'participation_average',
            'model_version', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']
    
    def get_class_detail(self, obj):
        return {
            'id': obj.class_instance.id,
            'name': obj.class_instance.name,
            'code': obj.class_instance.code
        }


class PredictionHistorySerializer(serializers.ModelSerializer):
    """Serializador para el historial de predicciones"""
    student_detail = StudentSerializer(source='student', read_only=True)
    period_detail = PeriodSerializer(source='period', read_only=True)
    class_detail = serializers.SerializerMethodField()
    accuracy_percentage = serializers.SerializerMethodField()
    prediction_quality = serializers.SerializerMethodField()
    
    class Meta:
        model = PredictionHistory
        fields = [
            'id', 'student', 'student_detail', 'class_instance', 'class_detail',
            'period', 'period_detail', 'predicted_grade', 'actual_grade',
            'difference', 'absolute_error', 'accuracy_percentage', 'prediction_quality',
            'prediction_confidence', 'prediction_model_version',
            'prediction_date', 'actual_grade_date'
        ]
        read_only_fields = ['difference', 'absolute_error', 'actual_grade_date']
    
    def get_class_detail(self, obj):
        return {
            'id': obj.class_instance.id,
            'name': obj.class_instance.name,
            'code': obj.class_instance.code
        }
    
    def get_accuracy_percentage(self, obj):
        """Calcula qué tan precisa fue la predicción (100% - error porcentual)"""
        if obj.actual_grade == 0:
            return 0
        error_percentage = (obj.absolute_error / obj.actual_grade) * 100
        return max(0, 100 - error_percentage)
    
    def get_prediction_quality(self, obj):
        """Determina la calidad de la predicción basada en el error absoluto"""
        if obj.absolute_error <= 5:
            return "Excelente"
        elif obj.absolute_error <= 10:
            return "Buena"
        elif obj.absolute_error <= 15:
            return "Regular"
        else:
            return "Pobre"


class MLModelSerializer(serializers.ModelSerializer):
    """Serializador para información de modelos ML"""
    class_detail = serializers.SerializerMethodField()
    
    class Meta:
        model = MLModel
        fields = [
            'id', 'class_instance', 'class_detail', 'model_version', 'algorithm',
            'training_score', 'validation_score', 'mean_absolute_error',
            'training_samples', 'created_at', 'is_active'
        ]
        read_only_fields = ['created_at']
    
    def get_class_detail(self, obj):
        return {
            'id': obj.class_instance.id,
            'name': obj.class_instance.name,
            'code': obj.class_instance.code
        }


class PredictionStatsSerializer(serializers.Serializer):
    """Serializador para estadísticas de predicciones por clase"""
    class_id = serializers.IntegerField()
    class_name = serializers.CharField()
    total_students = serializers.IntegerField()
    students_with_predictions = serializers.IntegerField()
    avg_predicted_grade = serializers.FloatField()
    avg_confidence = serializers.FloatField()
    model_version = serializers.CharField()
    predictions_count = serializers.IntegerField()


class ComparisonStatsSerializer(serializers.Serializer):
    """Serializador para estadísticas de comparación realidad vs predicción"""
    class_id = serializers.IntegerField()
    class_name = serializers.CharField()
    total_comparisons = serializers.IntegerField()
    avg_absolute_error = serializers.FloatField()
    avg_accuracy_percentage = serializers.FloatField()
    excellent_predictions = serializers.IntegerField()  # Error <= 5
    good_predictions = serializers.IntegerField()       # Error <= 10
    poor_predictions = serializers.IntegerField()       # Error > 15