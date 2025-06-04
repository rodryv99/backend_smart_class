# audit/views.py
from django.db.models import Q, Count, Avg
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from datetime import datetime, timedelta
import logging

from .models import AuditLog, AuditLogSummary
from .serializers import (
    AuditLogSerializer, AuditLogSummarySerializer, 
    AuditLogFilterSerializer, AuditStatsSerializer
)

logger = logging.getLogger('audit')

class AuditLogPagination(PageNumberPagination):
    """
    Paginación personalizada para logs de auditoría
    """
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200

class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet para gestionar logs de auditoría (solo lectura para admins)
    """
    queryset = AuditLog.objects.all()
    serializer_class = AuditLogSerializer
    pagination_class = AuditLogPagination
    permission_classes = [permissions.IsAuthenticated]
    
    def get_permissions(self):
        """
        Solo administradores pueden acceder a los logs de auditoría
        """
        if self.request.user.user_type != 'admin':
            self.permission_denied(
                self.request,
                message="Solo los administradores pueden acceder a los logs de auditoría"
            )
        return super().get_permissions()
    
    def get_queryset(self):
        """
        Filtrar queryset basado en parámetros de consulta
        """
        queryset = AuditLog.objects.all().select_related('user')
        
        # Aplicar filtros
        user_id = self.request.query_params.get('user', None)
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        
        username = self.request.query_params.get('username', None)
        if username:
            queryset = queryset.filter(username__icontains=username)
        
        action = self.request.query_params.get('action', None)
        if action:
            queryset = queryset.filter(action=action)
        
        date_from = self.request.query_params.get('date_from', None)
        if date_from:
            try:
                date_from_parsed = parse_date(date_from)
                if date_from_parsed:
                    queryset = queryset.filter(timestamp__date__gte=date_from_parsed)
            except ValueError:
                pass
        
        date_to = self.request.query_params.get('date_to', None)
        if date_to:
            try:
                date_to_parsed = parse_date(date_to)
                if date_to_parsed:
                    queryset = queryset.filter(timestamp__date__lte=date_to_parsed)
            except ValueError:
                pass
        
        ip_address = self.request.query_params.get('ip_address', None)
        if ip_address:
            queryset = queryset.filter(ip_address=ip_address)
        
        success = self.request.query_params.get('success', None)
        if success is not None:
            success_bool = success.lower() in ['true', '1', 'yes']
            queryset = queryset.filter(success=success_bool)
        
        content_type = self.request.query_params.get('content_type', None)
        if content_type:
            queryset = queryset.filter(content_type__icontains=content_type)
        
        object_id = self.request.query_params.get('object_id', None)
        if object_id:
            queryset = queryset.filter(object_id=object_id)
        
        search = self.request.query_params.get('search', None)
        if search:
            queryset = queryset.filter(
                Q(description__icontains=search) |
                Q(object_repr__icontains=search) |
                Q(error_message__icontains=search)
            )
        
        return queryset.order_by('-timestamp')
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """
        Obtener estadísticas de auditoría
        """
        try:
            # Calcular estadísticas básicas
            total_logs = AuditLog.objects.count()
            total_users = AuditLog.objects.values('user').distinct().count()
            
            # Acciones de hoy
            today = timezone.now().date()
            total_actions_today = AuditLog.objects.filter(timestamp__date=today).count()
            
            # Acciones fallidas
            total_failed_actions = AuditLog.objects.filter(success=False).count()
            
            # Acciones más comunes (últimos 30 días)
            thirty_days_ago = timezone.now() - timedelta(days=30)
            most_common_actions = list(
                AuditLog.objects.filter(timestamp__gte=thirty_days_ago)
                .values('action', 'action')
                .annotate(count=Count('action'))
                .order_by('-count')[:10]
            )
            
            # Usuarios más activos (últimos 30 días)
            most_active_users = list(
                AuditLog.objects.filter(timestamp__gte=thirty_days_ago, user__isnull=False)
                .values('user__username', 'username')
                .annotate(count=Count('user'))
                .order_by('-count')[:10]
            )
            
            # Acciones por hora (últimas 24 horas)
            twenty_four_hours_ago = timezone.now() - timedelta(hours=24)
            actions_by_hour = []
            for i in range(24):
                hour_start = twenty_four_hours_ago + timedelta(hours=i)
                hour_end = hour_start + timedelta(hours=1)
                count = AuditLog.objects.filter(
                    timestamp__gte=hour_start,
                    timestamp__lt=hour_end
                ).count()
                actions_by_hour.append({
                    'hour': hour_start.strftime('%H:00'),
                    'count': count
                })
            
            # Acciones por día (últimos 7 días)
            actions_by_day = []
            for i in range(7):
                day = timezone.now().date() - timedelta(days=i)
                count = AuditLog.objects.filter(timestamp__date=day).count()
                actions_by_day.append({
                    'date': day.strftime('%Y-%m-%d'),
                    'count': count
                })
            actions_by_day.reverse()  # Ordenar de más antiguo a más reciente
            
            # Tasa de éxito
            success_rate = 0
            if total_logs > 0:
                successful_actions = AuditLog.objects.filter(success=True).count()
                success_rate = (successful_actions / total_logs) * 100
            
            stats_data = {
                'total_logs': total_logs,
                'total_users': total_users,
                'total_actions_today': total_actions_today,
                'total_failed_actions': total_failed_actions,
                'most_common_actions': most_common_actions,
                'most_active_users': most_active_users,
                'actions_by_hour': actions_by_hour,
                'actions_by_day': actions_by_day,
                'success_rate': round(success_rate, 2)
            }
            
            serializer = AuditStatsSerializer(stats_data)
            return Response(serializer.data)
            
        except Exception as e:
            logger.error(f"Error calculando estadísticas de auditoría: {str(e)}")
            return Response(
                {"error": "Error al calcular estadísticas"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def export(self, request):
        """
        Exportar logs de auditoría (básico)
        """
        try:
            # Aplicar los mismos filtros que en get_queryset
            queryset = self.get_queryset()
            
            # Limitar exportación para evitar problemas de memoria
            limit = int(request.query_params.get('limit', 1000))
            if limit > 5000:
                limit = 5000
            
            logs = queryset[:limit]
            serializer = self.get_serializer(logs, many=True)
            
            return Response({
                'count': len(logs),
                'results': serializer.data
            })
            
        except Exception as e:
            logger.error(f"Error exportando logs: {str(e)}")
            return Response(
                {"error": "Error al exportar logs"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AuditLogSummaryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet para resúmenes de auditoría
    """
    queryset = AuditLogSummary.objects.all()
    serializer_class = AuditLogSummarySerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_permissions(self):
        """
        Solo administradores pueden acceder
        """
        if self.request.user.user_type != 'admin':
            self.permission_denied(
                self.request,
                message="Solo los administradores pueden acceder a los resúmenes de auditoría"
            )
        return super().get_permissions()


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def log_manual_action(request):
    """
    Endpoint para crear logs de auditoría manuales
    """
    if request.user.user_type != 'admin':
        return Response(
            {"error": "Solo los administradores pueden crear logs manuales"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        action = request.data.get('action')
        description = request.data.get('description', '')
        object_type = request.data.get('object_type', '')
        object_id = request.data.get('object_id', '')
        object_repr = request.data.get('object_repr', '')
        extra_data = request.data.get('extra_data', {})
        
        if not action:
            return Response(
                {"error": "El campo 'action' es requerido"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Obtener IP del cliente
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        
        # Crear el log
        audit_log = AuditLog.log_action(
            user=request.user,
            action=action,
            description=description,
            ip_address=ip,
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            object_type=object_type,
            object_id=object_id,
            object_repr=object_repr,
            extra_data=extra_data,
            success=True
        )
        
        serializer = AuditLogSerializer(audit_log)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        logger.error(f"Error creando log manual: {str(e)}")
        return Response(
            {"error": "Error al crear log manual"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_action_choices(request):
    """
    Obtener lista de acciones disponibles para filtros
    """
    if request.user.user_type != 'admin':
        return Response(
            {"error": "Solo los administradores pueden acceder a esta información"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    choices = [
        {'value': choice[0], 'label': choice[1]}
        for choice in AuditLog.ACTION_CHOICES
    ]
    
    return Response(choices)


@api_view(['DELETE'])
@permission_classes([permissions.IsAuthenticated])
def cleanup_old_logs(request):
    """
    Limpiar logs antiguos (solo para administradores)
    """
    if request.user.user_type != 'admin':
        return Response(
            {"error": "Solo los administradores pueden limpiar logs"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        days = int(request.data.get('days', 90))
        if days < 30:  # Mínimo 30 días
            days = 30
        
        cutoff_date = timezone.now() - timedelta(days=days)
        deleted_count, _ = AuditLog.objects.filter(timestamp__lt=cutoff_date).delete()
        
        # Log de la acción de limpieza
        AuditLog.log_action(
            user=request.user,
            action='SYSTEM_CLEANUP',
            description=f"Limpieza de logs antiguos: {deleted_count} registros eliminados",
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            extra_data={'deleted_count': deleted_count, 'days': days}
        )
        
        return Response({
            'message': f'Se eliminaron {deleted_count} logs anteriores a {cutoff_date.date()}',
            'deleted_count': deleted_count
        })
        
    except Exception as e:
        logger.error(f"Error limpiando logs: {str(e)}")
        return Response(
            {"error": "Error al limpiar logs"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )