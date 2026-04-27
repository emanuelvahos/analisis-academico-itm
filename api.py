import os
import pandas as pd
import numpy as np
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv
from supabase import create_client, Client

# Cargar variables de entorno
load_dotenv()
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

app = FastAPI(title="API Dashboard ITM")

# Configurar CORS para permitir que el frontend consuma la API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_supabase_client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def fetch_table(table_name: str, columns: str = "*") -> pd.DataFrame:
    """Extrae TODOS los registros paginando para evadir el límite de Supabase."""
    supabase = get_supabase_client()
    all_data = []
    start = 0
    page_size = 1000
    while True:
        response = supabase.table(table_name).select(columns).range(start, start + page_size - 1).execute()
        data = response.data
        if not data: break
        all_data.extend(data)
        if len(data) < page_size: break
        start += page_size
    return pd.DataFrame(all_data)

# Caché en memoria para evitar consultar la base de datos en cada petición
data_cache = {}

def get_excel_data() -> pd.DataFrame:
    """Extrae datos del archivo Excel para los análisis temporales y sociodemográficos."""
    if "excel" in data_cache:
        return data_cache["excel"]
    
    print("📥 Leyendo datos desde el Excel maestro...")
    df = pd.read_excel("Desarrollo Curricular SIGA Semestre (1).xlsx")
    df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')
    
    # Calcular Mortalidad
    if 'definitiva' in df.columns:
        df['definitiva_num'] = pd.to_numeric(df['definitiva'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
        df['mortalidad'] = df['definitiva_num'].apply(lambda x: 1 if x < 3.0 else 0)
        
    # Crear columna 'semester' para filtrar
    if 'año' in df.columns and 'semestre' in df.columns:
        df['semester'] = df['año'].astype(str).str.replace('.0', '', regex=False) + '-' + df['semestre'].astype(str).str.replace('.0', '', regex=False)
        
    # Calcular Hora Real y Jornada para el Excel
    if 'hora_inicial' in df.columns:
        df['hora_inicial_num'] = pd.to_numeric(df['hora_inicial'], errors='coerce')
        df['hora_real'] = df['hora_inicial_num'].apply(lambda x: x + 12 if pd.notnull(x) and x <= 5 else x)
        df['jornada'] = df['hora_real'].apply(lambda x: 'Nocturna (18:00 - 22:00)' if x >= 18 else 'Diurna (06:00 - 17:59)')

    data_cache["excel"] = df
    return df

def clean_df_for_json(df):
    """Limpia un DataFrame para evitar errores de serialización JSON con NaNs y tipos Numpy."""
    df_clean = df.copy()
    # Asegurar que las columnas numéricas críticas sean tipos nativos
    for col in df_clean.select_dtypes(include=[np.number]).columns:
        df_clean[col] = df_clean[col].astype(float)
    # Reemplazar NaNs por None (nulos en JSON)
    df_clean = df_clean.replace({float('nan'): None})
    return df_clean.to_dict(orient='records')

def get_master_data() -> pd.DataFrame:
    """Extrae y cruza los datos, guardando el resultado en caché."""
    if "master" in data_cache:
        return data_cache["master"]
    
    print("📥 Descargando datos desde Supabase...")
    df_perf = fetch_table("academic_performance")
    df_groups = fetch_table("class_groups").rename(columns={'id': 'group_id'})
    df_sched = fetch_table("group_schedules")
    df_subjects = fetch_table("subjects").rename(columns={'id': 'subject_id', 'name': 'subject_name'})
    df_teachers = fetch_table("teachers").rename(columns={'id': 'teacher_id', 'full_name': 'teacher_name'})
    
    print("🔄 Cruzando tablas y limpiando datos...")
    # Bórramos la columna duplicada 'tenant_id' y otras para evitar choques en Pandas
    df_groups = df_groups.drop(columns=['tenant_id', 'created_at', 'updated_at'], errors='ignore')
    df_sched = df_sched.drop(columns=['tenant_id', 'created_at', 'updated_at'], errors='ignore')
    df_subjects = df_subjects.drop(columns=['tenant_id', 'created_at', 'updated_at'], errors='ignore')
    df_teachers = df_teachers.drop(columns=['tenant_id', 'created_at', 'updated_at'], errors='ignore')
    
    # Unimos Notas -> Grupos -> Horarios -> Asignaturas -> Docentes
    df_master = df_perf.merge(df_groups, on='group_id', how='inner')
    df_master = df_master.merge(df_sched, on='group_id', how='left')
    df_master = df_master.merge(df_subjects, on='subject_id', how='left')
    df_master = df_master.merge(df_teachers, on='teacher_id', how='left')
    
    # 1. Calcular Mortalidad
    df_master['mortalidad'] = df_master['final_grade'].apply(lambda x: 1 if float(x) < 3.0 else 0)
    
    # 2. Calcular Franja Horaria (corrigiendo sesgo AM/PM)
    df_master['hora_cruda'] = pd.to_datetime(df_master['start_time'], format='%H:%M:%S', errors='coerce').dt.hour
    df_master['hora_real'] = df_master['hora_cruda'].apply(lambda x: x + 12 if pd.notnull(x) and x <= 5 else x)
    
    limites = [6, 8, 10, 12, 14, 16, 18, 20, 22]
    etiquetas = ['06:00-08:00', '08:00-10:00', '10:00-12:00', '12:00-14:00', 
                 '14:00-16:00', '16:00-18:00', '18:00-20:00', '20:00-22:00']
    
    df_master['franja_horaria'] = pd.cut(df_master['hora_real'], bins=limites, labels=etiquetas, right=False)
    
    # 3. Mapear días de la semana
    dias_semana = {1: 'Lunes', 2: 'Martes', 3: 'Miércoles', 4: 'Jueves', 5: 'Viernes', 6: 'Sábado'}
    df_master['dia_nombre'] = df_master['day_of_week'].map(dias_semana)
    
    data_cache["master"] = df_master
    return df_master

@app.get("/api/kpis")
def get_kpis(semestre: str = None):
    df = get_master_data()
    
    if semestre:
        df = df[df['semester'] == semestre]
        
    # 1. Mortalidad Global
    mortalidad_global = round(df['mortalidad'].mean() * 100, 1) if not df.empty else 0.0
    
    # 2. Total Estudiantes (Registros académicos)
    total_estudiantes = len(df)
    
    # 3. Asignatura más crítica
    # Filtramos materias de nivelatorio o práctica
    df_materias = df[~df['subject_name'].str.contains('NIVELATORIO|GRADO|PRACTICA', case=False, na=False)]
    
    materias_stats = df_materias.groupby('subject_name').agg(
        total_estudiantes=('mortalidad', 'count'),
        tasa_mortalidad=('mortalidad', 'mean')
    ).reset_index()
    
    # Mínimo 30 estudiantes evaluados
    materias_stats = materias_stats[materias_stats['total_estudiantes'] >= 30]
    
    if not materias_stats.empty:
        top_materia = materias_stats.sort_values(by='tasa_mortalidad', ascending=False).iloc[0]
        asignatura_critica_nombre = top_materia['subject_name']
        asignatura_critica_porcentaje = round(top_materia['tasa_mortalidad'] * 100, 1)
    else:
        asignatura_critica_nombre = "N/A"
        asignatura_critica_porcentaje = 0.0

    return {
        "mortalidad_global": mortalidad_global,
        "total_estudiantes": total_estudiantes,
        "asignatura_critica": {
            "nombre": asignatura_critica_nombre,
            "porcentaje": asignatura_critica_porcentaje
        }
    }

@app.get("/api/heatmap")
def get_heatmap(semestre: str = None):
    df = get_master_data()
    
    if semestre:
        df = df[df['semester'] == semestre]
        
    # Filtrar solo registros con franja horaria y día válidos
    df_heatmap = df.dropna(subset=['franja_horaria', 'dia_nombre'])
    
    # Agrupar para obtener la tasa de mortalidad promedio por franja y día
    heatmap_data = df_heatmap.groupby(['franja_horaria', 'dia_nombre'])['mortalidad'].mean().reset_index()
    
    # Formatear el porcentaje a un decimal para que la respuesta JSON sea limpia (ej: 0.345 -> 0.345)
    heatmap_data['mortalidad'] = heatmap_data['mortalidad'].fillna(0).round(4)
    
    # Convertir a una lista de diccionarios
    return clean_df_for_json(heatmap_data)

@app.get("/api/teachers")
def get_teachers(semestre: str = None, materia: str = None):
    df = get_master_data()
    
    if semestre:
        df = df[df['semester'] == semestre]
        
    if materia:
        df = df[df['subject_name'] == materia]
        
    df_teachers_stats = df.dropna(subset=['teacher_name'])
    docentes_stats = df_teachers_stats.groupby('teacher_name').agg(
        total_estudiantes=('mortalidad', 'count'),
        tasa_mortalidad=('mortalidad', 'mean')
    ).reset_index()
    
    # Mínimo 20 estudiantes evaluados por docente si hay filtro de materia, sino 40
    min_est = 20 if materia else 40
    docentes_stats = docentes_stats[docentes_stats['total_estudiantes'] >= min_est]
    
    top_docentes = docentes_stats.sort_values(by='tasa_mortalidad', ascending=False).head(15)
    top_docentes['tasa_mortalidad'] = top_docentes['tasa_mortalidad'].round(4)
    
    return clean_df_for_json(top_docentes)

@app.get("/api/adaptacion")
def get_adaptacion(semestre: str = None):
    df = get_excel_data()
    
    if semestre and 'semester' in df.columns:
        df = df[df['semester'] == semestre]
        
    if 'antigüedad' in df.columns:
        # Limpieza estricta de la columna antigüedad
        df_clean = df.copy()
        df_clean['semestre'] = pd.to_numeric(df_clean['antigüedad'], errors='coerce')
        df_clean = df_clean.dropna(subset=['semestre'])
        
        df_curva = df_clean[(df_clean['semestre'] >= 1) & (df_clean['semestre'] <= 10)]
        
        curva_stats = df_curva.groupby('semestre').agg(
            mortalidad=('mortalidad', 'mean')
        ).reset_index()
        
        curva_stats['mortalidad'] = curva_stats['mortalidad'].fillna(0).astype(float).round(4)
        curva_stats['semestre'] = curva_stats['semestre'].astype(int)
        
        datos_json = clean_df_for_json(curva_stats)
        print("📊 Datos Curva:", datos_json)
        return datos_json
    return []

@app.get("/api/brecha-ciencias")
def get_brecha_ciencias(semestre: str = None):
    df = get_excel_data()
    
    if semestre and 'semester' in df.columns:
        df = df[df['semester'] == semestre]
        
    if 'asignatura' in df.columns and 'sexo' in df.columns:
        materias_duras = df[df['asignatura'].str.contains('CALCULO|FISICA|ALGEBRA|PROGRAMACION', case=False, na=False)]
        
        if not materias_duras.empty:
            brecha_stats = materias_duras.groupby('sexo').agg(
                total_estudiantes=('mortalidad', 'count'),
                tasa_mortalidad=('mortalidad', 'mean')
            ).reset_index()
            
            brecha_stats['tasa_mortalidad'] = brecha_stats['tasa_mortalidad'].fillna(0).astype(float).round(4)
            return clean_df_for_json(brecha_stats)
    return []

@app.get("/api/materias-filtro")
def get_materias_filtro(semestre: str = None):
    df = get_excel_data()
    if semestre:
        df = df[df['semester'] == semestre]
    
    # Filtramos materias que no son de carga académica normal
    df_materias = df[~df['asignatura'].str.contains('NIVELATORIO|GRADO|PRACTICA', case=False, na=False)]
    
    materias_stats = df_materias.groupby('asignatura').agg(
        total_estudiantes=('mortalidad', 'count'),
        tasa_mortalidad=('mortalidad', 'mean')
    ).reset_index()
    
    materias_stats = materias_stats[materias_stats['total_estudiantes'] >= 30]
    top_filtros = materias_stats.sort_values(by='tasa_mortalidad', ascending=False).head(10)
    top_filtros['tasa_mortalidad'] = top_filtros['tasa_mortalidad'].astype(float).round(4)
    
    return clean_df_for_json(top_filtros)

@app.get("/api/sedes")
def get_sedes(semestre: str = None):
    df = get_excel_data()
    if semestre:
        df = df[df['semester'] == semestre]
        
    if 'sede' in df.columns:
        sede_stats = df.groupby('sede').agg(
            total_estudiantes=('mortalidad', 'count'),
            tasa_mortalidad=('mortalidad', 'mean')
        ).reset_index()
        
        sede_stats = sede_stats[sede_stats['total_estudiantes'] >= 50]
        sede_stats = sede_stats.sort_values(by='tasa_mortalidad', ascending=False)
        sede_stats['tasa_mortalidad'] = sede_stats['tasa_mortalidad'].astype(float).round(4)
        
        return clean_df_for_json(sede_stats)
    return []

@app.get("/api/jornada")
def get_jornada(semestre: str = None):
    df = get_excel_data()
    if semestre:
        df = df[df['semester'] == semestre]
        
    if 'jornada' in df.columns:
        jornada_stats = df.groupby('jornada').agg(
            total_estudiantes=('mortalidad', 'count'),
            tasa_mortalidad=('mortalidad', 'mean')
        ).reset_index()
        
        jornada_stats['tasa_mortalidad'] = jornada_stats['tasa_mortalidad'].astype(float).round(4)
        
        return clean_df_for_json(jornada_stats)
    return []

@app.get("/api/materias-list")
def get_materias_list():
    df = get_master_data()
    materias = sorted(df['subject_name'].dropna().unique().tolist())
    return materias

# Servir el Frontend (index.html) en la ruta raíz
@app.get("/")
def read_index():
    return FileResponse('public/index.html')

# Montar la carpeta public para servir main.js y assets
# Se monta al final para no interferir con las rutas /api
app.mount("/", StaticFiles(directory="public"), name="public")
