from rest_framework import viewsets, status, permissions
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.generics import UpdateAPIView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from .models import User, TeacherProfile, StudentProfile
from .serializers import (
    UserSerializer, TeacherProfileSerializer, StudentProfileSerializer,
    UserDetailSerializer, TeacherProfileDetailSerializer, StudentProfileDetailSerializer
)

@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def register_student(request):
    serializer = StudentProfileSerializer(data=request.data)
    if serializer.is_valid():
        student = serializer.save()
        refresh = RefreshToken.for_user(student.user)
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': UserSerializer(student.user).data
        }, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def register_teacher(request):
    # Solo el administrador puede crear profesores
    if request.user.user_type != 'admin':
        return Response({'error': 'No tienes permisos para realizar esta acción'}, 
                        status=status.HTTP_403_FORBIDDEN)
    
    serializer = TeacherProfileSerializer(data=request.data)
    if serializer.is_valid():
        teacher = serializer.save()
        return Response(
            UserSerializer(teacher.user).data,
            status=status.HTTP_201_CREATED
        )
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def login_view(request):
    username = request.data.get('username')
    password = request.data.get('password')
    
    user = authenticate(username=username, password=password)
    
    if user is not None:
        refresh = RefreshToken.for_user(user)
        
        # Obtener todos los datos del usuario incluyendo su perfil completo
        user_data = UserDetailSerializer(user).data
        
        # Si es un estudiante, asegurarse de que el perfil esté completo
        if user.user_type == 'student' and not user_data.get('student_profile'):
            try:
                # Intentar obtener el perfil de estudiante
                student_profile = StudentProfile.objects.get(user=user)
                # Añadir manualmente al resultado
                user_data['student_profile'] = StudentProfileDetailSerializer(student_profile).data
                print(f"Añadido perfil de estudiante para {user.username}: {user_data['student_profile']}")
            except StudentProfile.DoesNotExist:
                print(f"No se encontró perfil de estudiante para el usuario {user.id}")
        
        # Similar para profesores
        if user.user_type == 'teacher' and not user_data.get('teacher_profile'):
            try:
                teacher_profile = TeacherProfile.objects.get(user=user)
                user_data['teacher_profile'] = TeacherProfileDetailSerializer(teacher_profile).data
                print(f"Añadido perfil de profesor para {user.username}")
            except TeacherProfile.DoesNotExist:
                print(f"No se encontró perfil de profesor para el usuario {user.id}")
        
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': user_data
        })
    else:
        return Response({'error': 'Credenciales inválidas'}, status=status.HTTP_401_UNAUTHORIZED)

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        # Usar el serializador detallado para listar y recuperar
        if self.action in ['list', 'retrieve']:
            return UserDetailSerializer
        # Usar el serializador básico para crear y actualizar
        return UserSerializer
    
    def get_queryset(self):
        # Solo el administrador puede ver todos los usuarios
        if self.request.user.user_type == 'admin':
            return User.objects.all()
        # Los demás usuarios solo pueden ver su propia información
        return User.objects.filter(id=self.request.user.id)
    
    def update(self, request, *args, **kwargs):
        # Solo el administrador puede editar usuarios
        if request.user.user_type != 'admin':
            return Response({'error': 'No tienes permisos para realizar esta acción'}, 
                        status=status.HTTP_403_FORBIDDEN)
        
        return super().update(request, *args, **kwargs)
    
    def destroy(self, request, *args, **kwargs):
        # Solo el administrador puede eliminar usuarios
        if request.user.user_type != 'admin':
            return Response({'error': 'No tienes permisos para realizar esta acción'}, 
                        status=status.HTTP_403_FORBIDDEN)
        
        return super().destroy(request, *args, **kwargs)

# Nuevos endpoints para actualizar perfiles
@api_view(['PUT'])
@permission_classes([permissions.IsAuthenticated])
def update_teacher_profile(request, pk):
    # Solo el administrador puede actualizar perfiles
    if request.user.user_type != 'admin':
        return Response({'error': 'No tienes permisos para realizar esta acción'}, 
                    status=status.HTTP_403_FORBIDDEN)
    
    try:
        profile = TeacherProfile.objects.get(pk=pk)
    except TeacherProfile.DoesNotExist:
        return Response({'error': 'Perfil no encontrado'}, status=status.HTTP_404_NOT_FOUND)
    
    serializer = TeacherProfileSerializer(profile, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['PUT'])
@permission_classes([permissions.IsAuthenticated])
def update_student_profile(request, pk):
    # Solo el administrador puede actualizar perfiles
    if request.user.user_type != 'admin':
        return Response({'error': 'No tienes permisos para realizar esta acción'}, 
                    status=status.HTTP_403_FORBIDDEN)
    
    try:
        profile = StudentProfile.objects.get(pk=pk)
    except StudentProfile.DoesNotExist:
        return Response({'error': 'Perfil no encontrado'}, status=status.HTTP_404_NOT_FOUND)
    
    serializer = StudentProfileSerializer(profile, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_all_student_profiles(request):
    """
    Obtener todos los perfiles de estudiantes.
    Solo disponible para administradores y profesores.
    """
    if request.user.user_type not in ['admin', 'teacher']:
        return Response({'error': 'No tienes permisos para ver esta información'},
                        status=status.HTTP_403_FORBIDDEN)
    
    students = StudentProfile.objects.all()
    serializer = StudentProfileSerializer(students, many=True)
    return Response(serializer.data)

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_teacher_profile(request, user_id):
    """
    Obtener el perfil de un profesor por ID de usuario.
    """
    try:
        # Verificar permisos
        if request.user.id != int(user_id) and request.user.user_type != 'admin':
            return Response({'error': 'No tienes permisos para ver esta información'},
                        status=status.HTTP_403_FORBIDDEN)
            
        user = User.objects.get(id=user_id)
        if user.user_type != 'teacher':
            return Response({'error': 'El usuario no es un profesor'},
                        status=status.HTTP_400_BAD_REQUEST)
            
        profile = TeacherProfile.objects.get(user=user)
        serializer = TeacherProfileSerializer(profile)
        return Response(serializer.data)
    except User.DoesNotExist:
        return Response({'error': 'Usuario no encontrado'}, status=status.HTTP_404_NOT_FOUND)
    except TeacherProfile.DoesNotExist:
        return Response({'error': 'Perfil de profesor no encontrado'}, status=status.HTTP_404_NOT_FOUND)