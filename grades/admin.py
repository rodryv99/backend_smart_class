from django.contrib import admin
from .models import Grade, FinalGrade

@admin.register(Grade)
class GradeAdmin(admin.ModelAdmin):
    list_display = (
        'student_name', 'class_name', 'period_name', 
        'ser', 'saber', 'hacer', 'decidir', 'autoevaluacion', 
        'nota_total', 'estado', 'updated_at'
    )
    list_filter = (
        'estado', 'class_instance__year', 'period__period_type', 
        'period__number', 'class_instance__subject'
    )
    search_fields = (
        'student__first_name', 'student__last_name', 'student__ci',
        'class_instance__name', 'class_instance__code'
    )
    readonly_fields = ('nota_total', 'estado', 'created_at', 'updated_at')
    
    fieldsets = (
        ('Información General', {
            'fields': ('student', 'class_instance', 'period')
        }),
        ('Calificaciones', {
            'fields': ('ser', 'saber', 'hacer', 'decidir', 'autoevaluacion'),
            'description': 'Ser (0-5), Saber (0-45), Hacer (0-40), Decidir (0-5), Autoevaluación (0-5)'
        }),
        ('Resultados (Calculados Automáticamente)', {
            'fields': ('nota_total', 'estado'),
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
    
    def period_name(self, obj):
        return str(obj.period)
    period_name.short_description = 'Período'
    period_name.admin_order_field = 'period__number'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'student', 'class_instance', 'period',
            'class_instance__subject', 'class_instance__course', 
            'class_instance__group'
        )


@admin.register(FinalGrade)
class FinalGradeAdmin(admin.ModelAdmin):
    list_display = (
        'student_name', 'class_name', 'nota_final', 
        'estado_final', 'periods_count', 'updated_at'
    )
    list_filter = (
        'estado_final', 'class_instance__year', 
        'class_instance__subject', 'periods_count'
    )
    search_fields = (
        'student__first_name', 'student__last_name', 'student__ci',
        'class_instance__name', 'class_instance__code'
    )
    readonly_fields = ('nota_final', 'estado_final', 'periods_count', 'created_at', 'updated_at')
    
    fieldsets = (
        ('Información General', {
            'fields': ('student', 'class_instance')
        }),
        ('Resultados Finales (Calculados Automáticamente)', {
            'fields': ('nota_final', 'estado_final', 'periods_count'),
            'description': 'Estos campos se calculan automáticamente basados en las notas de todos los períodos'
        }),
        ('Metadatos', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    actions = ['recalculate_final_grades']
    
    def student_name(self, obj):
        return f"{obj.student.first_name} {obj.student.last_name}"
    student_name.short_description = 'Estudiante'
    student_name.admin_order_field = 'student__first_name'
    
    def class_name(self, obj):
        return obj.class_instance.name
    class_name.short_description = 'Clase'
    class_name.admin_order_field = 'class_instance__name'
    
    def recalculate_final_grades(self, request, queryset):
        """Acción para recalcular notas finales seleccionadas"""
        updated_count = 0
        for final_grade in queryset:
            final_grade.calculate_final_grade()
            updated_count += 1
        
        self.message_user(
            request,
            f"Se recalcularon {updated_count} notas finales exitosamente."
        )
    recalculate_final_grades.short_description = "Recalcular notas finales seleccionadas"
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'student', 'class_instance',
            'class_instance__subject', 'class_instance__course', 
            'class_instance__group'
        )