# audit/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
import json
from .models import AuditLog, AuditLogSummary

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """
    Administración de logs de auditoría
    """
    list_display = [
        'timestamp', 'username_display', 'action_display', 'success_icon', 
        'ip_address', 'object_type_display', 'object_repr_short'
    ]
    list_filter = [
        'action', 'success', 'content_type', 'timestamp'
    ]
    search_fields = [
        'username', 'description', 'object_repr', 'ip_address'
    ]
    readonly_fields = [
        'user', 'username', 'action', 'description', 'ip_address', 
        'user_agent', 'timestamp', 'content_type', 'object_id', 
        'object_repr', 'extra_data_formatted', 'success', 'error_message'
    ]
    date_hierarchy = 'timestamp'
    ordering = ['-timestamp']
    list_per_page = 50
    
    fieldsets = (
        ('Información del Usuario', {
            'fields': ('user', 'username', 'ip_address')
        }),
        ('Acción', {
            'fields': ('action', 'description', 'success', 'error_message')
        }),
        ('Objeto Afectado', {
            'fields': ('content_type', 'object_id', 'object_repr')
        }),
        ('Información Técnica', {
            'fields': ('timestamp', 'user_agent', 'extra_data_formatted'),
            'classes': ('collapse',)
        }),
    )
    
    def has_add_permission(self, request):
        """
        No permitir agregar logs manualmente desde admin
        """
        return False
    
    def has_change_permission(self, request, obj=None):
        """
        No permitir editar logs
        """
        return False
    
    def has_delete_permission(self, request, obj=None):
        """
        Solo super usuarios pueden eliminar logs
        """
        return request.user.is_superuser
    
    def username_display(self, obj):
        """
        Mostrar username con enlace al usuario si existe
        """
        if obj.user:
            url = reverse('admin:users_user_change', args=[obj.user.pk])
            return format_html('<a href="{}">{}</a>', url, obj.username)
        return obj.username or 'Anónimo'
    username_display.short_description = 'Usuario'
    
    def action_display(self, obj):
        """
        Mostrar acción con color según el tipo
        """
        colors = {
            'LOGIN': '#28a745',
            'LOGOUT': '#6c757d',
            'CREATE': '#007bff',
            'UPDATE': '#ffc107',
            'DELETE': '#dc3545',
            'VIEW': '#17a2b8',
        }
        
        action_type = obj.action.split('_')[-1] if '_' in obj.action else obj.action
        color = colors.get(action_type, '#6c757d')
        
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_action_display()
        )
    action_display.short_description = 'Acción'
    
    def success_icon(self, obj):
        """
        Mostrar icono de éxito/error
        """
        if obj.success:
            return format_html(
                '<span style="color: green; font-size: 16px;">✓</span>'
            )
        else:
            return format_html(
                '<span style="color: red; font-size: 16px;">✗</span>'
            )
    success_icon.short_description = 'Estado'
    
    def object_type_display(self, obj):
        """
        Mostrar tipo de objeto con estilo
        """
        if obj.content_type:
            return format_html(
                '<span style="background-color: #e9ecef; padding: 2px 6px; border-radius: 3px; font-size: 11px;">{}</span>',
                obj.content_type
            )
        return '-'
    object_type_display.short_description = 'Tipo'
    
    def object_repr_short(self, obj):
        """
        Mostrar representación corta del objeto
        """
        if obj.object_repr:
            return obj.object_repr[:50] + '...' if len(obj.object_repr) > 50 else obj.object_repr
        return '-'
    object_repr_short.short_description = 'Objeto'
    
    def extra_data_formatted(self, obj):
        """
        Mostrar datos extra formateados
        """
        if obj.extra_data:
            try:
                formatted = json.dumps(obj.extra_data, indent=2, ensure_ascii=False)
                return format_html('<pre style="font-size: 12px;">{}</pre>', formatted)
            except:
                return str(obj.extra_data)
        return 'Sin datos adicionales'
    extra_data_formatted.short_description = 'Datos Extra'


@admin.register(AuditLogSummary)
class AuditLogSummaryAdmin(admin.ModelAdmin):
    """
    Administración de resúmenes de auditoría
    """
    list_display = [
        'date', 'total_actions', 'unique_users', 'failed_actions', 
        'success_rate', 'most_active_user', 'most_common_action'
    ]
    list_filter = ['date']
    search_fields = ['most_active_user', 'most_common_action']
    readonly_fields = [
        'date', 'total_actions', 'unique_users', 'failed_actions',
        'most_common_action', 'most_active_user', 'login_count',
        'create_count', 'update_count', 'delete_count', 'view_count',
        'created_at', 'updated_at'
    ]
    date_hierarchy = 'date'
    ordering = ['-date']
    
    def has_add_permission(self, request):
        """
        No permitir agregar resúmenes manualmente
        """
        return False
    
    def has_change_permission(self, request, obj=None):
        """
        No permitir editar resúmenes
        """
        return False
    
    def success_rate(self, obj):
        """
        Calcular y mostrar tasa de éxito
        """
        if obj.total_actions > 0:
            success_actions = obj.total_actions - obj.failed_actions
            rate = (success_actions / obj.total_actions) * 100
            color = 'green' if rate >= 95 else 'orange' if rate >= 90 else 'red'
            return format_html(
                '<span style="color: {}; font-weight: bold;">{:.1f}%</span>',
                color, rate
            )
        return 'N/A'
    success_rate.short_description = 'Tasa de Éxito'