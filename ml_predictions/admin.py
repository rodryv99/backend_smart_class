from django.contrib import admin
from .models import Prediction, PredictionHistory, MLModel

@admin.register(Prediction)
class PredictionAdmin(admin.ModelAdmin):
    list_display = (
        'student_name', 'class_name', 'predicted_period_name', 
        'predicted_grade', 'confidence', 'model_version', 'updated_at'
    )
    list_filter = (
        'class_instance__year', 'predicted_period__period_type', 
        'predicted_period__number', 'model_version'
    )
    search_fields = (
        'student__first_name', 'student__last_name', 'student__ci',
        'class_instance__name', 'class_instance__code'
    )
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Información General', {
            'fields': ('student', 'class_instance', 'predicted_period')
        }),
        ('Predicción', {
            'fields': ('predicted_grade', 'confidence', 'model_version'),
            'description': 'Valores calculados automáticamente por el modelo ML'
        }),
        ('Variables Predictoras', {
            'fields': ('avg_previous_grades', 'attendance_percentage', 'participation_average'),
            'classes': ('collapse',)
        }),
        ('Metadatos', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def student_name(self, obj):
        return f"{obj.student.first_name} {obj.student.last_name}"
    student_name.short_description = 'Estudiante'
    student_name.admin_order_field = 'student__first_name'
    
    def class_name(self, obj):
        return obj.class_instance.name
    class_name.short_description = 'Clase'
    class_name.admin_order_field = 'class_instance__name'
    
    def predicted_period_name(self, obj):
        return str(obj.predicted_period)
    predicted_period_name.short_description = 'Período Predicho'
    predicted_period_name.admin_order_field = 'predicted_period__number'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'student', 'class_instance', 'predicted_period',
            'class_instance__subject', 'class_instance__course', 
            'class_instance__group'
        )


@admin.register(PredictionHistory)
class PredictionHistoryAdmin(admin.ModelAdmin):
    list_display = (
        'student_name', 'class_name', 'period_name', 
        'predicted_grade', 'actual_grade', 'absolute_error', 
        'prediction_quality', 'actual_grade_date'
    )
    list_filter = (
        'class_instance__year', 'period__period_type', 
        'period__number', 'prediction_model_version'
    )
    search_fields = (
        'student__first_name', 'student__last_name', 'student__ci',
        'class_instance__name', 'class_instance__code'
    )
    readonly_fields = ('difference', 'absolute_error', 'actual_grade_date')
    
    fieldsets = (
        ('Información General', {
            'fields': ('student', 'class_instance', 'period')
        }),
        ('Comparación Predicción vs Realidad', {
            'fields': ('predicted_grade', 'actual_grade', 'difference', 'absolute_error')
        }),
        ('Información de la Predicción Original', {
            'fields': ('prediction_confidence', 'prediction_model_version', 'prediction_date'),
            'classes': ('collapse',)
        }),
        ('Metadatos', {
            'fields': ('actual_grade_date',),
            'classes': ('collapse',)
        })
    )
    
    actions = ['calculate_accuracy_stats']
    
    def student_name(self, obj):
        return f"{obj.student.first_name} {obj.student.last_name}"
    student_name.short_description = 'Estudiante'
    student_name.admin_order_field = 'student__first_name'
    
    def class_name(self, obj):
        return obj.class_instance.name
    class_name.short_description = 'Clase'
    class_name.admin_order_field = 'class_instance__name'
    
    def period_name(self, obj):
        return str(obj.period)
    period_name.short_description = 'Período'
    period_name.admin_order_field = 'period__number'
    
    def prediction_quality(self, obj):
        if obj.absolute_error <= 5:
            return "Excelente"
        elif obj.absolute_error <= 10:
            return "Buena"
        elif obj.absolute_error <= 15:
            return "Regular"
        else:
            return "Pobre"
    prediction_quality.short_description = 'Calidad de Predicción'
    
    def calculate_accuracy_stats(self, request, queryset):
        """Acción para calcular estadísticas de precisión"""
        total = queryset.count()
        if total == 0:
            self.message_user(request, "No hay registros seleccionados.")
            return
        
        avg_error = sum(h.absolute_error for h in queryset) / total
        excellent = queryset.filter(absolute_error__lte=5).count()
        good = queryset.filter(absolute_error__lte=10, absolute_error__gt=5).count()
        poor = queryset.filter(absolute_error__gt=15).count()
        
        self.message_user(
            request,
            f"Estadísticas de {total} predicciones: "
            f"Error promedio: {avg_error:.2f}, "
            f"Excelentes: {excellent}, Buenas: {good}, Pobres: {poor}"
        )
    calculate_accuracy_stats.short_description = "Calcular estadísticas de precisión"
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'student', 'class_instance', 'period',
            'class_instance__subject', 'class_instance__course', 
            'class_instance__group'
        )


@admin.register(MLModel)
class MLModelAdmin(admin.ModelAdmin):
    list_display = (
        'class_name', 'algorithm', 'model_version', 
        'validation_score', 'mean_absolute_error', 'training_samples',
        'is_active', 'created_at'
    )
    list_filter = (
        'algorithm', 'is_active', 'class_instance__year', 'created_at'
    )
    search_fields = (
        'class_instance__name', 'class_instance__code', 'model_version'
    )
    readonly_fields = ('created_at',)
    
    fieldsets = (
        ('Información del Modelo', {
            'fields': ('class_instance', 'algorithm', 'model_version', 'is_active')
        }),
        ('Métricas de Rendimiento', {
            'fields': ('training_score', 'validation_score', 'mean_absolute_error', 'training_samples')
        }),
        ('Archivo del Modelo', {
            'fields': ('model_file_path',),
            'classes': ('collapse',)
        }),
        ('Metadatos', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        })
    )
    
    actions = ['activate_models', 'deactivate_models']
    
    def class_name(self, obj):
        return obj.class_instance.name
    class_name.short_description = 'Clase'
    class_name.admin_order_field = 'class_instance__name'
    
    def activate_models(self, request, queryset):
        """Activar modelos seleccionados"""
        # Primero desactivar todos los modelos de las clases afectadas
        for model in queryset:
            MLModel.objects.filter(class_instance=model.class_instance).update(is_active=False)
        
        # Luego activar solo los seleccionados
        updated = queryset.update(is_active=True)
        self.message_user(
            request,
            f"Se activaron {updated} modelos. Los demás modelos de las mismas clases fueron desactivados."
        )
    activate_models.short_description = "Activar modelos seleccionados"
    
    def deactivate_models(self, request, queryset):
        """Desactivar modelos seleccionados"""
        updated = queryset.update(is_active=False)
        self.message_user(
            request,
            f"Se desactivaron {updated} modelos."
        )
    deactivate_models.short_description = "Desactivar modelos seleccionados"
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'class_instance', 'class_instance__subject', 
            'class_instance__course', 'class_instance__group'
        )