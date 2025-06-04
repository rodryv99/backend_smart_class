from django.contrib import admin
from .models import Period, Subject, Course, Group, Class, Attendance, Participation

@admin.register(Period)
class PeriodAdmin(admin.ModelAdmin):
    list_display = ('period_type', 'number', 'year', 'start_date', 'end_date')
    search_fields = ('number', 'year', 'period_type')
    list_filter = ('period_type', 'number', 'year')

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('code', 'name')
    search_fields = ('code', 'name')

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('code', 'name')
    search_fields = ('code', 'name')

@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ('code', 'name')
    search_fields = ('code', 'name')

@admin.register(Class)
class ClassAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'teacher', 'subject', 'course', 'group', 'year')
    search_fields = ('code', 'name')
    list_filter = ('year', 'subject', 'course', 'group')
    filter_horizontal = ('students', 'periods')

@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('student', 'class_instance', 'period', 'date', 'status')
    search_fields = ('student__first_name', 'student__last_name')
    list_filter = ('status', 'date', 'period')

@admin.register(Participation)
class ParticipationAdmin(admin.ModelAdmin):
    list_display = ('student', 'class_instance', 'period', 'date', 'level')
    search_fields = ('student__first_name', 'student__last_name')
    list_filter = ('level', 'date', 'period')