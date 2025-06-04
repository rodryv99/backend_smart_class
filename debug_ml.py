# debug_ml.py - Colocar en el directorio raíz del proyecto (junto a manage.py)

import os
import sys
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smart_class_backend.settings')
django.setup()

from ml_predictions.ml_service import MLPredictionService
from academic.models import Class
from grades.models import Grade
from users.models import StudentProfile

def diagnose_ml_system():
    """Diagnostica el sistema de ML paso a paso"""
    
    print("🔍 DIAGNÓSTICO DEL SISTEMA DE MACHINE LEARNING")
    print("=" * 60)
    
    # 1. Verificar que hay clases con datos
    print("\n1. VERIFICANDO CLASES CON DATOS...")
    classes_with_grades = Class.objects.filter(grades__isnull=False).distinct()
    
    if not classes_with_grades.exists():
        print("❌ ERROR: No hay clases con notas en el sistema")
        return False
    
    print(f"✅ Encontradas {classes_with_grades.count()} clases con datos:")
    for clase in classes_with_grades[:5]:  # Mostrar solo las primeras 5
        grades_count = Grade.objects.filter(class_instance=clase).count()
        students_count = clase.students.count()
        print(f"   - {clase.name} (ID: {clase.id}): {students_count} estudiantes, {grades_count} notas")
    
    # 2. Seleccionar una clase para pruebas
    test_class = classes_with_grades.first()
    print(f"\n2. USANDO CLASE DE PRUEBA: {test_class.name} (ID: {test_class.id})")
    
    # 3. Verificar datos de la clase
    students = test_class.students.all()
    grades = Grade.objects.filter(class_instance=test_class)
    periods = test_class.periods.all()
    
    print(f"   - Estudiantes: {students.count()}")
    print(f"   - Notas totales: {grades.count()}")
    print(f"   - Períodos asignados: {periods.count()}")
    
    if not students.exists():
        print("❌ ERROR: La clase no tiene estudiantes")
        return False
    
    if not grades.exists():
        print("❌ ERROR: La clase no tiene notas")
        return False
    
    # 4. Verificar datos por estudiante
    print("\n3. VERIFICANDO DATOS POR ESTUDIANTE...")
    students_with_enough_data = 0
    
    for student in students[:5]:  # Verificar solo los primeros 5
        student_grades = grades.filter(student=student)
        print(f"   - {student.first_name} {student.last_name}: {student_grades.count()} notas")
        if student_grades.count() >= 1:
            students_with_enough_data += 1
    
    print(f"   Estudiantes con datos suficientes: {students_with_enough_data}")
    
    # 5. Probar el servicio de ML
    print("\n4. PROBANDO SERVICIO DE ML...")
    try:
        ml_service = MLPredictionService(test_class)
        print("✅ Servicio ML creado exitosamente")
    except Exception as e:
        print(f"❌ ERROR creando servicio ML: {e}")
        return False
    
    # 6. Probar generación de datos sintéticos
    print("\n5. PROBANDO GENERACIÓN DE DATOS SINTÉTICOS...")
    try:
        synthetic_data = ml_service.generate_synthetic_data(10)
        print(f"✅ Datos sintéticos generados: {len(synthetic_data)} muestras")
        print(f"   Columnas: {list(synthetic_data.columns)}")
    except Exception as e:
        print(f"❌ ERROR generando datos sintéticos: {e}")
        return False
    
    # 7. Probar recolección de datos de estudiante
    print("\n6. PROBANDO RECOLECCIÓN DE DATOS DE ESTUDIANTE...")
    test_student = students.first()
    try:
        student_data = ml_service.collect_student_data(test_student)
        if student_data:
            print(f"✅ Datos de estudiante recolectados:")
            for key, value in student_data.items():
                print(f"     {key}: {value}")
        else:
            print("⚠️  No se pudieron recolectar datos del estudiante")
    except Exception as e:
        print(f"❌ ERROR recolectando datos de estudiante: {e}")
        import traceback
        print(traceback.format_exc())
        return False
    
    # 8. Probar preparación de datos de entrenamiento
    print("\n7. PROBANDO PREPARACIÓN DE DATOS DE ENTRENAMIENTO...")
    try:
        training_data = ml_service.prepare_training_data()
        print(f"✅ Datos de entrenamiento preparados: {len(training_data)} muestras")
        print(f"   Columnas: {list(training_data.columns)}")
        if len(training_data) > 0:
            print(f"   Muestra de datos:")
            print(training_data.head().to_string())
    except Exception as e:
        print(f"❌ ERROR preparando datos de entrenamiento: {e}")
        import traceback
        print(traceback.format_exc())
        return False
    
    # 9. Probar entrenamiento del modelo
    print("\n8. PROBANDO ENTRENAMIENTO DEL MODELO...")
    try:
        ml_model = ml_service.train_model()
        if ml_model:
            print(f"✅ Modelo entrenado exitosamente:")
            print(f"     Versión: {ml_model.model_version}")
            print(f"     Score de validación: {ml_model.validation_score:.3f}")
            print(f"     Error absoluto medio: {ml_model.mean_absolute_error:.2f}")
            print(f"     Muestras de entrenamiento: {ml_model.training_samples}")
        else:
            print("⚠️  El modelo no se pudo entrenar (pero no hubo error)")
    except Exception as e:
        print(f"❌ ERROR entrenando modelo: {e}")
        import traceback
        print(traceback.format_exc())
        return False
    
    # 10. Probar predicciones
    print("\n9. PROBANDO PREDICCIONES...")
    try:
        prediction = ml_service.predict_next_period(test_student)
        if prediction:
            print(f"✅ Predicción generada:")
            print(f"     Estudiante: {prediction.student.first_name} {prediction.student.last_name}")
            print(f"     Período predicho: {prediction.predicted_period}")
            print(f"     Nota predicha: {prediction.predicted_grade:.1f}")
            print(f"     Confianza: {prediction.confidence:.1f}%")
        else:
            print("⚠️  No se pudo generar predicción (posiblemente no hay próximo período)")
    except Exception as e:
        print(f"❌ ERROR generando predicción: {e}")
        import traceback
        print(traceback.format_exc())
        return False
    
    print(f"\n{'='*60}")
    print("🎉 DIAGNÓSTICO COMPLETADO - SISTEMA FUNCIONANDO CORRECTAMENTE")
    print("="*60)
    return True

if __name__ == "__main__":
    diagnose_ml_system()