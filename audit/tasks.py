# audit/tasks.py
from django.utils import timezone
from django.db.models import Count, Q
from datetime import timedelta, date
import logging
import io
import csv

from .models import AuditLog, AuditLogSummary

logger = logging.getLogger('audit')

def generate_daily_summary(target_date=None):
    """
    Generar resumen diario de logs de auditoría
    """
    if target_date is None:
        target_date = timezone.now().date() - timedelta(days=1)  # Ayer por defecto
    
    try:
        # Obtener logs del día
        logs = AuditLog.objects.filter(timestamp__date=target_date)
        
        if not logs.exists():
            logger.info(f"No hay logs para la fecha {target_date}")
            return
        
        # Calcular estadísticas
        total_actions = logs.count()
        unique_users = logs.filter(user__isnull=False).values('user').distinct().count()
        failed_actions = logs.filter(success=False).count()
        
        # Acción más común
        most_common_action_data = logs.values('action').annotate(
            count=Count('action')
        ).order_by('-count').first()
        most_common_action = most_common_action_data['action'] if most_common_action_data else ''
        
        # Usuario más activo
        most_active_user_data = logs.filter(user__isnull=False).values('username').annotate(
            count=Count('username')
        ).order_by('-count').first()
        most_active_user = most_active_user_data['username'] if most_active_user_data else ''
        
        # Contadores por tipo de acción
        login_count = logs.filter(action__in=['LOGIN', 'LOGOUT', 'LOGIN_FAILED']).count()
        create_count = logs.filter(action__icontains='CREATE').count()
        update_count = logs.filter(action__icontains='UPDATE').count()
        delete_count = logs.filter(action__icontains='DELETE').count()
        view_count = logs.filter(action__icontains='VIEW').count()
        
        # Crear o actualizar resumen
        summary, created = AuditLogSummary.objects.update_or_create(
            date=target_date,
            defaults={
                'total_actions': total_actions,
                'unique_users': unique_users,
                'failed_actions': failed_actions,
                'most_common_action': most_common_action,
                'most_active_user': most_active_user,
                'login_count': login_count,
                'create_count': create_count,
                'update_count': update_count,
                'delete_count': delete_count,
                'view_count': view_count,
            }
        )
        
        action = "creado" if created else "actualizado"
        logger.info(f"Resumen diario {action} para {target_date}: {total_actions} acciones")
        
        return summary
        
    except Exception as e:
        logger.error(f"Error generando resumen diario para {target_date}: {str(e)}")
        return None

def cleanup_old_audit_logs(days_to_keep=90):
    """
    Limpiar logs de auditoría antiguos
    """
    try:
        cutoff_date = timezone.now() - timedelta(days=days_to_keep)
        
        # Contar logs a eliminar
        logs_to_delete = AuditLog.objects.filter(timestamp__lt=cutoff_date)
        count_to_delete = logs_to_delete.count()
        
        if count_to_delete == 0:
            logger.info("No hay logs antiguos para eliminar")
            return 0
        
        # Eliminar logs
        deleted_count, _ = logs_to_delete.delete()
        
        # Log de la limpieza
        AuditLog.log_action(
            user=None,
            action='SYSTEM_CLEANUP',
            description=f'Limpieza automática de logs: {deleted_count} registros eliminados',
            extra_data={
                'deleted_count': deleted_count,
                'days_to_keep': days_to_keep,
                'cutoff_date': cutoff_date.isoformat()
            }
        )
        
        logger.info(f"Limpieza completada: {deleted_count} logs eliminados anteriores a {cutoff_date.date()}")
        return deleted_count
        
    except Exception as e:
        logger.error(f"Error en limpieza de logs: {str(e)}")
        return 0

def generate_missing_summaries():
    """
    Generar resúmenes faltantes para días que tienen logs pero no resumen
    """
    try:
        # Obtener fechas con logs
        dates_with_logs = AuditLog.objects.values('timestamp__date').distinct()
        
        # Obtener fechas con resúmenes
        dates_with_summaries = set(
            AuditLogSummary.objects.values_list('date', flat=True)
        )
        
        missing_dates = []
        for item in dates_with_logs:
            log_date = item['timestamp__date']
            if log_date not in dates_with_summaries:
                missing_dates.append(log_date)
        
        logger.info(f"Encontradas {len(missing_dates)} fechas sin resumen")
        
        generated_count = 0
        for missing_date in missing_dates:
            if generate_daily_summary(missing_date):
                generated_count += 1
        
        logger.info(f"Generados {generated_count} resúmenes faltantes")
        return generated_count
        
    except Exception as e:
        logger.error(f"Error generando resúmenes faltantes: {str(e)}")
        return 0

def get_security_alerts():
    """
    Detectar alertas de seguridad basadas en los logs
    """
    try:
        alerts = []
        now = timezone.now()
        last_hour = now - timedelta(hours=1)
        last_24h = now - timedelta(hours=24)
        
        # Múltiples intentos de login fallidos desde la misma IP
        failed_logins = AuditLog.objects.filter(
            action='LOGIN_FAILED',
            timestamp__gte=last_hour
        ).values('ip_address').annotate(
            count=Count('ip_address')
        ).filter(count__gte=5)
        
        for item in failed_logins:
            alerts.append({
                'type': 'MULTIPLE_FAILED_LOGINS',
                'severity': 'HIGH',
                'message': f"Múltiples intentos de login fallidos desde IP {item['ip_address']} ({item['count']} intentos en la última hora)",
                'ip_address': item['ip_address'],
                'count': item['count']
            })
        
        # Accesos no autorizados
        unauthorized_access = AuditLog.objects.filter(
            action='UNAUTHORIZED_ACCESS',
            timestamp__gte=last_24h
        ).count()
        
        if unauthorized_access > 0:
            alerts.append({
                'type': 'UNAUTHORIZED_ACCESS',
                'severity': 'MEDIUM',
                'message': f"{unauthorized_access} intentos de acceso no autorizado en las últimas 24 horas",
                'count': unauthorized_access
            })
        
        # Eliminaciones masivas
        mass_deletions = AuditLog.objects.filter(
            action__icontains='DELETE',
            timestamp__gte=last_24h
        ).values('user').annotate(
            count=Count('user')
        ).filter(count__gte=10)
        
        for item in mass_deletions:
            if item['user']:
                try:
                    from django.contrib.auth import get_user_model
                    User = get_user_model()
                    user = User.objects.get(pk=item['user'])
                    username = user.username
                except:
                    username = f"Usuario ID {item['user']}"
                
                alerts.append({
                    'type': 'MASS_DELETION',
                    'severity': 'HIGH',
                    'message': f"Eliminaciones masivas por {username} ({item['count']} eliminaciones en 24h)",
                    'user_id': item['user'],
                    'count': item['count']
                })
        
        # Errores del sistema frecuentes
        system_errors = AuditLog.objects.filter(
            action='SYSTEM_ERROR',
            timestamp__gte=last_24h
        ).count()
        
        if system_errors > 20:
            alerts.append({
                'type': 'FREQUENT_SYSTEM_ERRORS',
                'severity': 'MEDIUM',
                'message': f"Errores del sistema frecuentes: {system_errors} errores en las últimas 24 horas",
                'count': system_errors
            })
        
        return alerts
        
    except Exception as e:
        logger.error(f"Error detectando alertas de seguridad: {str(e)}")
        return []

def export_audit_logs_csv(start_date=None, end_date=None, user_id=None):
    """
    Exportar logs de auditoría a CSV
    """
    try:
        import csv
        import io
        from django.http import HttpResponse
        
        # Construir queryset
        queryset = AuditLog.objects.all()
        
        if start_date:
            queryset = queryset.filter(timestamp__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(timestamp__date__lte=end_date)
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        
        # Crear CSV en memoria
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Escribir encabezados
        writer.writerow([
            'Fecha/Hora', 'Usuario', 'Acción', 'Descripción', 'IP',
            'Tipo Objeto', 'ID Objeto', 'Objeto', 'Éxito', 'Error'
        ])
        
        # Escribir datos
        for log in queryset.order_by('-timestamp'):
            writer.writerow([
                log.timestamp.strftime('%d/%m/%Y %H:%M:%S'),
                log.username,
                log.get_action_display(),
                log.description,
                log.ip_address or '',
                log.content_type or '',
                log.object_id or '',
                log.object_repr or '',
                'Sí' if log.success else 'No',
                log.error_message or ''
            ])
        
        return output.getvalue()
        
    except Exception as e:
        logger.error(f"Error exportando logs a CSV: {str(e)}")
        return None