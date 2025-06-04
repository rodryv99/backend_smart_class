from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, TeacherProfile, StudentProfile

admin.site.register(User, UserAdmin)
admin.site.register(TeacherProfile)
admin.site.register(StudentProfile)