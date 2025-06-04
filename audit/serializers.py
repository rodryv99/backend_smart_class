# audit/serializers.py
from rest_framework import serializers
from .models import AuditLog, AuditLogSummary

class AuditLogSerializer(serializers.ModelSerializer):
    """
    Serializador para mostrar logs de auditoría
    """
    user_full_name = serializers.SerializerMethodField()
    action_display = serializers.CharField(source='get_action_display', read_only=True)
    timestamp_formatted = serializers.SerializerMethodField()
    
    class Meta:
        model = AuditLog
        fields = [
            'id', 'user', 'username', 'user_full_name', 'action', 'action_display',
            'description', 'ip_address', 'user_agent', 'timestamp', 'timestamp_formatted',
            'content_type', 'object_id', 'object_repr', 'extra_data', 
            'success', 'error_message'
        ]
        read_only_fields = fields  # Todos los campos son de solo lectura
    
    def get_user_full_name(self, obj):
        """
        Obtener nombre completo del usuario si existe
        """
        if obj.user:
            if hasattr(obj.user, 'teacher_profile'):
                try:
                    profile = obj.user.teacher_profile
                    return f"{profile.first_name} {profile.last_name}"
                except:
                    pass
            elif hasattr(obj.user, 'student_profile'):
                try:
                    profile = obj.user.student_profile
                    return f"{profile.first_name} {profile.last_name}"
                except:
                    pass
            return obj.user.get_full_name() or obj.username
        return obj.username or 'Usuario anónimo'
    
    def get_timestamp_formatted(self, obj):
        """
        Formatear timestamp para mostrar
        """
        return obj.timestamp.strftime('%d/%m/%Y %H:%M:%S')


class AuditLogSummarySerializer(serializers.ModelSerializer):
    """
    Serializador para resúmenes de auditoría
    """
    date_formatted = serializers.SerializerMethodField()
    
    class Meta:
        model = AuditLogSummary
        fields = [
            'id', 'date', 'date_formatted', 'total_actions', 'unique_users',
            'failed_actions', 'most_common_action', 'most_active_user',
            'login_count', 'create_count', 'update_count', 'delete_count', 'view_count'
        ]
        read_only_fields = fields
    
    def get_date_formatted(self, obj):
        """
        Formatear fecha para mostrar
        """
        return obj.date.strftime('%d/%m/%Y')


class AuditLogFilterSerializer(serializers.Serializer):
    """
    Serializador para filtros de búsqueda de logs
    """
    user = serializers.IntegerField(required=False, help_text="ID del usuario")
    username = serializers.CharField(required=False, max_length=150, help_text="Nombre de usuario")
    action = serializers.ChoiceField(choices=AuditLog.ACTION_CHOICES, required=False, help_text="Tipo de acción")
    date_from = serializers.DateField(required=False, help_text="Fecha desde (YYYY-MM-DD)")
    date_to = serializers.DateField(required=False, help_text="Fecha hasta (YYYY-MM-DD)")
    ip_address = serializers.IPAddressField(required=False, help_text="Dirección IP")
    success = serializers.BooleanField(required=False, help_text="Acción exitosa")
    content_type = serializers.CharField(required=False, max_length=100, help_text="Tipo de objeto")
    object_id = serializers.CharField(required=False, max_length=100, help_text="ID del objeto")
    search = serializers.CharField(required=False, max_length=255, help_text="Búsqueda en descripción")


class AuditStatsSerializer(serializers.Serializer):
    """
    Serializador para estadísticas de auditoría
    """
    total_logs = serializers.IntegerField()
    total_users = serializers.IntegerField()
    total_actions_today = serializers.IntegerField()
    total_failed_actions = serializers.IntegerField()
    most_common_actions = serializers.ListField(child=serializers.DictField())
    most_active_users = serializers.ListField(child=serializers.DictField())
    actions_by_hour = serializers.ListField(child=serializers.DictField())
    actions_by_day = serializers.ListField(child=serializers.DictField())
    success_rate = serializers.FloatField()
    
    class Meta:
        fields = [
            'total_logs', 'total_users', 'total_actions_today', 'total_failed_actions',
            'most_common_actions', 'most_active_users', 'actions_by_hour',
            'actions_by_day', 'success_rate'
        ]