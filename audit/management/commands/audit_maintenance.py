# audit/management/commands/audit_maintenance.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta, datetime
import sys

from audit.tasks import (
    generate_daily_summary, cleanup_old_audit_logs, 
    generate_missing_summaries, get_security_alerts
)
from audit.models import AuditLog, AuditLogSummary

class Command(BaseCommand):
    help = 'Comandos de mantenimiento para el sistema de auditoría'

    def add_arguments(self, parser):
        parser.add_argument(
            'action',
            type=str,
            choices=['summary', 'cleanup', 'missing_summaries', 'security_alerts', 'stats'],
            help='Acción a realizar'
        )
        
        parser.add_argument(
            '--date',
            type=str,
            help='Fecha específica (YYYY-MM-DD) para generar resumen'
        )
        
        parser.add_argument(
            '--days',
            type=int,
            default=90,
            help='Días a mantener en cleanup (default: 90)'
        )
        
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostrar qué se haría sin ejecutar'
        )

    def handle(self, *args, **options):
        action = options['action']
        
        if action == 'summary':
            self.generate_summary(options)
        elif action == 'cleanup':
            self.cleanup_logs(options)
        elif action == 'missing_summaries':
            self.generate_missing_summaries(options)
        elif action == 'security_alerts':
            self.check_security_alerts(options)
        elif action == 'stats':
            self.show_stats(options)

    def generate_summary(self, options):
        """
        Generar resumen diario
        """
        target_date = None
        if options['date']:
            try:
                target_date = datetime.strptime(options['date'], '%Y-%m-%d').date()
            except ValueError:
                self.stdout.write(
                    self.style.ERROR('Formato de fecha inválido. Use YYYY-MM-DD')
                )
                return

        if options['dry_run']:
            date_str = target_date or (timezone.now().date() - timedelta(days=1))
            self.stdout.write(f"Se generaría resumen para la fecha: {date_str}")
            return

        self.stdout.write("Generando resumen diario...")
        summary = generate_daily_summary(target_date)
        
        if summary:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Resumen generado exitosamente para {summary.date}: '
                    f'{summary.total_actions} acciones, {summary.unique_users} usuarios únicos'
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING('No se pudo generar el resumen')
            )

    def cleanup_logs(self, options):
        """
        Limpiar logs antiguos
        """
        days = options['days']
        cutoff_date = timezone.now() - timedelta(days=days)
        
        # Contar logs a eliminar
        logs_to_delete = AuditLog.objects.filter(timestamp__lt=cutoff_date).count()
        
        if logs_to_delete == 0:
            self.stdout.write("No hay logs antiguos para eliminar")
            return

        if options['dry_run']:
            self.stdout.write(
                f"Se eliminarían {logs_to_delete} logs anteriores a {cutoff_date.date()}"
            )
            return

        self.stdout.write(f"Eliminando {logs_to_delete} logs antiguos...")
        
        # Confirmar si hay muchos logs
        if logs_to_delete > 1000:
            confirm = input(
                f"¿Está seguro de eliminar {logs_to_delete} logs? (sí/no): "
            )
            if confirm.lower() not in ['sí', 'si', 'yes', 'y']:
                self.stdout.write("Operación cancelada")
                return

        deleted_count = cleanup_old_audit_logs(days)
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Limpieza completada: {deleted_count} logs eliminados'
            )
        )

    def generate_missing_summaries(self, options):
        """
        Generar resúmenes faltantes
        """
        if options['dry_run']:
            # Calcular cuántos resúmenes faltan
            dates_with_logs = AuditLog.objects.values('timestamp__date').distinct()
            dates_with_summaries = set(
                AuditLogSummary.objects.values_list('date', flat=True)
            )
            
            missing_count = 0
            for item in dates_with_logs:
                if item['timestamp__date'] not in dates_with_summaries:
                    missing_count += 1
            
            self.stdout.write(f"Se generarían {missing_count} resúmenes faltantes")
            return

        self.stdout.write("Generando resúmenes faltantes...")
        generated_count = generate_missing_summaries()
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Generados {generated_count} resúmenes faltantes'
            )
        )

    def check_security_alerts(self, options):
        """
        Verificar alertas de seguridad
        """
        self.stdout.write("Verificando alertas de seguridad...")
        alerts = get_security_alerts()
        
        if not alerts:
            self.stdout.write(
                self.style.SUCCESS("No se encontraron alertas de seguridad")
            )
            return

        self.stdout.write(
            self.style.WARNING(f"Se encontraron {len(alerts)} alertas:")
        )
        
        for alert in alerts:
            severity_style = self.style.ERROR if alert['severity'] == 'HIGH' else self.style.WARNING
            self.stdout.write(
                severity_style(f"[{alert['severity']}] {alert['message']}")
            )

    def show_stats(self, options):
        """
        Mostrar estadísticas generales
        """
        self.stdout.write("=== ESTADÍSTICAS DE AUDITORÍA ===")
        
        # Estadísticas básicas
        total_logs = AuditLog.objects.count()
        total_users = AuditLog.objects.values('user').distinct().count()
        total_summaries = AuditLogSummary.objects.count()
        
        self.stdout.write(f"Total de logs: {total_logs:,}")
        self.stdout.write(f"Usuarios únicos: {total_users:,}")
        self.stdout.write(f"Resúmenes diarios: {total_summaries:,}")
        
        # Estadísticas de hoy
        today = timezone.now().date()
        today_logs = AuditLog.objects.filter(timestamp__date=today).count()
        self.stdout.write(f"Logs de hoy: {today_logs:,}")
        
        # Últimas 24 horas
        last_24h = timezone.now() - timedelta(hours=24)
        last_24h_logs = AuditLog.objects.filter(timestamp__gte=last_24h).count()
        failed_24h = AuditLog.objects.filter(
            timestamp__gte=last_24h, success=False
        ).count()
        
        self.stdout.write(f"Logs últimas 24h: {last_24h_logs:,}")
        self.stdout.write(f"Fallos últimas 24h: {failed_24h:,}")
        
        # Tasa de éxito
        if total_logs > 0:
            successful_logs = AuditLog.objects.filter(success=True).count()
            success_rate = (successful_logs / total_logs) * 100
            self.stdout.write(f"Tasa de éxito global: {success_rate:.2f}%")
        
        # Log más antiguo y más reciente
        oldest_log = AuditLog.objects.order_by('timestamp').first()
        newest_log = AuditLog.objects.order_by('-timestamp').first()
        
        if oldest_log:
            self.stdout.write(f"Log más antiguo: {oldest_log.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        if newest_log:
            self.stdout.write(f"Log más reciente: {newest_log.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Acciones más comunes (últimos 7 días)
        seven_days_ago = timezone.now() - timedelta(days=7)
        common_actions = AuditLog.objects.filter(
            timestamp__gte=seven_days_ago
        ).values('action').annotate(
            count=Count('action')
        ).order_by('-count')[:5]
        
        if common_actions:
            self.stdout.write("\nAcciones más comunes (últimos 7 días):")
            for action in common_actions:
                action_display = dict(AuditLog.ACTION_CHOICES).get(
                    action['action'], action['action']
                )
                self.stdout.write(f"  {action_display}: {action['count']:,}")

# Importar Count para el comando
from django.db.models import Count