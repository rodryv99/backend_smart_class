from rest_framework import serializers
from .models import User, TeacherProfile, StudentProfile

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password', 'user_type']
        extra_kwargs = {'password': {'write_only': True}}
        
    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
            user_type=validated_data.get('user_type', 'student')
        )
        return user

class TeacherProfileDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeacherProfile
        fields = ['id', 'teacher_code', 'ci', 'first_name', 'last_name', 'phone', 'birth_date']

class StudentProfileDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentProfile
        fields = ['id', 'ci', 'first_name', 'last_name', 'phone', 'birth_date', 'tutor_name', 'tutor_phone']

class UserDetailSerializer(serializers.ModelSerializer):
    teacher_profile = serializers.SerializerMethodField()
    student_profile = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'user_type', 'teacher_profile', 'student_profile']
    
    def get_teacher_profile(self, obj):
        if obj.user_type == 'teacher':
            try:
                teacher_profile = TeacherProfile.objects.get(user=obj)
                return TeacherProfileDetailSerializer(teacher_profile).data
            except TeacherProfile.DoesNotExist:
                return None
        return None
    
    def get_student_profile(self, obj):
        if obj.user_type == 'student':
            try:
                student_profile = StudentProfile.objects.get(user=obj)
                return StudentProfileDetailSerializer(student_profile).data
            except StudentProfile.DoesNotExist:
                return None
        return None

class StudentProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer()
    
    class Meta:
        model = StudentProfile
        fields = ['id', 'user', 'ci', 'first_name', 'last_name', 'phone', 'birth_date', 'tutor_name', 'tutor_phone']
        
    def create(self, validated_data):
        user_data = validated_data.pop('user')
        user_data['user_type'] = 'student'
        user = UserSerializer().create(user_data)
        
        student_profile = StudentProfile.objects.create(
            user=user,
            ci=validated_data['ci'],
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
            phone=validated_data['phone'],
            birth_date=validated_data['birth_date'],
            tutor_name=validated_data['tutor_name'],
            tutor_phone=validated_data['tutor_phone']
        )
        return student_profile

class TeacherProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer()
    
    class Meta:
        model = TeacherProfile
        fields = ['id', 'user', 'teacher_code', 'ci', 'first_name', 'last_name', 'phone', 'birth_date']
        
    def create(self, validated_data):
        user_data = validated_data.pop('user')
        user_data['user_type'] = 'teacher'
        user = UserSerializer().create(user_data)
        
        teacher_profile = TeacherProfile.objects.create(
            user=user,
            teacher_code=validated_data['teacher_code'],
            ci=validated_data['ci'],
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
            phone=validated_data['phone'],
            birth_date=validated_data['birth_date']
        )
        return teacher_profile