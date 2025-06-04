from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/users/', include('users.urls')),
    path('api/academic/', include('academic.urls')),
    path('api/grades/', include('grades.urls')),  
    path('api/ml/', include('ml_predictions.urls')),  
    path('api/audit/', include('audit.urls')),
]