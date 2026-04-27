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

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- CARGA GLOBAL DE DATOS (EN RAM) ---
print("🚀 [INFO] Iniciando carga de base de datos en RAM para producción...")

def get_supabase_client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def fetch_table(table_name: str, columns: str = "*") -> pd.DataFrame:
    supabase = get_supabase_client()
    all_data = []
    start, page_size = 0, 1000
    while True:
        response = supabase.table(table_name).select(columns).range(start, start + page_size - 1).execute()
        data = response.data
        if not data: break
        all_data.extend(data)
        if len(data) < page_size: break
        start += page_size
    return pd.DataFrame(all_data)

def load_all_data():
    # 1. Cargar Excel
    print("📥 Cargando Excel maestro...")
    df_ex = pd.read_excel("Desarrollo Curricular SIGA Semestre (1).xlsx")
    df_ex.columns = df_ex.columns.str.strip().str.lower().str.replace(' ', '_')
    
    if 'definitiva' in df_ex.columns:
        df_ex['definitiva_num'] = pd.to_numeric(df_ex['definitiva'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
        df_ex['mortalidad'] = df_ex['definitiva_num'].apply(lambda x: 1 if x < 3.0 else 0)
    
    if 'año' in df_ex.columns and 'semestre' in df_ex.columns:
        df_ex['semester'] = df_ex['año'].astype(str).str.replace('.0', '', regex=False) + '-' + df_ex['semestre'].astype(str).str.replace('.0', '', regex=False)
        
    if 'hora_inicial' in df_ex.columns:
        df_ex['hora_inicial_num'] = pd.to_numeric(df_ex['hora_inicial'], errors='coerce')
        df_ex['hora_real'] = df_ex['hora_inicial_num'].apply(lambda x: x + 12 if pd.notnull(x) and x <= 5 else x)
        df_ex['jornada'] = df_ex['hora_real'].apply(lambda x: 'Nocturna (18:00 - 22:00)' if x >= 18 else 'Diurna (06:00 - 17:59)')

    # 2. Cargar Supabase
    print("📥 Cargando datos desde Supabase...")
    df_perf = fetch_table("academic_performance")
    df_groups = fetch_table("class_groups").rename(columns={'id': 'group_id'})
    df_sched = fetch_table("group_schedules")
    df_subjects = fetch_table("subjects").rename(columns={'id': 'subject_id', 'name': 'subject_name'})
    df_teachers = fetch_table("teachers").rename(columns={'id': 'teacher_id', 'full_name': 'teacher_name'})
    
    print("🔄 Cruzando tablas y optimizando...")
    df_groups = df_groups.drop(columns=['tenant_id', 'created_at', 'updated_at'], errors='ignore')
    df_sched = df_sched.drop(columns=['tenant_id', 'created_at', 'updated_at'], errors='ignore')
    df_subjects = df_subjects.drop(columns=['tenant_id', 'created_at', 'updated_at'], errors='ignore')
    df_teachers = df_teachers.drop(columns=['tenant_id', 'created_at', 'updated_at'], errors='ignore')
    
    df_ma = df_perf.merge(df_groups, on='group_id', how='inner')
    df_ma = df_ma.merge(df_sched, on='group_id', how='left')
    df_ma = df_ma.merge(df_subjects, on='subject_id', how='left')
    df_ma = df_ma.merge(df_teachers, on='teacher_id', how='left')
    
    df_ma['mortalidad'] = df_ma['final_grade'].apply(lambda x: 1 if float(x) < 3.0 else 0)
    df_ma['hora_cruda'] = pd.to_datetime(df_ma['start_time'], format='%H:%M:%S', errors='coerce').dt.hour
    df_ma['hora_real'] = df_ma['hora_cruda'].apply(lambda x: x + 12 if pd.notnull(x) and x <= 5 else x)
    
    limites = [6, 8, 10, 12, 14, 16, 18, 20, 22]
    etiquetas = ['06:00-08:00', '08:00-10:00', '10:00-12:00', '12:00-14:00', '14:00-16:00', '16:00-18:00', '18:00-20:00', '20:00-22:00']
    df_ma['franja_horaria'] = pd.cut(df_ma['hora_real'], bins=limites, labels=etiquetas, right=False)
    
    dias_semana = {1: 'Lunes', 2: 'Martes', 3: 'Miércoles', 4: 'Jueves', 5: 'Viernes', 6: 'Sábado'}
    df_ma['dia_nombre'] = df_ma['day_of_week'].map(dias_semana)
    
    print("✅ [INFO] Carga completada. Servidor listo.")
    return df_ex, df_ma

# Variables globales que residen en RAM
GLOBAL_DF_EXCEL, GLOBAL_DF_MASTER = load_all_data()

def clean_df_for_json(df):
    df_clean = df.copy()
    for col in df_clean.select_dtypes(include=[np.number]).columns:
        df_clean[col] = df_clean[col].astype(float)
    return df_clean.replace({float('nan'): None}).to_dict(orient='records')

# --- ENDPOINTS ---

@app.get("/api/kpis")
def get_kpis(semestre: str = None):
    df = GLOBAL_DF_MASTER
    if semestre: df = df[df['semester'] == semestre]
    
    mortalidad_global = round(df['mortalidad'].mean() * 100, 1) if not df.empty else 0.0
    total_estudiantes = len(df)
    
    df_materias = df[~df['subject_name'].str.contains('NIVELATORIO|GRADO|PRACTICA', case=False, na=False)]
    materias_stats = df_materias.groupby('subject_name').agg(
        total_estudiantes=('mortalidad', 'count'),
        tasa_mortalidad=('mortalidad', 'mean')
    ).reset_index()
    
    materias_stats = materias_stats[materias_stats['total_estudiantes'] >= 30]
    
    if not materias_stats.empty:
        top_materia = materias_stats.sort_values(by='tasa_mortalidad', ascending=False).iloc[0]
        asignatura_critica = {"nombre": top_materia['subject_name'], "porcentaje": round(top_materia['tasa_mortalidad'] * 100, 1)}
    else:
        asignatura_critica = {"nombre": "N/A", "porcentaje": 0.0}

    return {"mortalidad_global": mortalidad_global, "total_estudiantes": total_estudiantes, "asignatura_critica": asignatura_critica}

@app.get("/api/heatmap")
def get_heatmap(semestre: str = None):
    df = GLOBAL_DF_MASTER
    if semestre: df = df[df['semester'] == semestre]
    
    df_heatmap = df.dropna(subset=['franja_horaria', 'dia_nombre'])
    heatmap_data = df_heatmap.groupby(['franja_horaria', 'dia_nombre'])['mortalidad'].mean().reset_index()
    heatmap_data['mortalidad'] = heatmap_data['mortalidad'].fillna(0).round(4)
    
    # Solo columnas necesarias
    return clean_df_for_json(heatmap_data[['franja_horaria', 'dia_nombre', 'mortalidad']])

@app.get("/api/teachers")
def get_teachers(semestre: str = None, materia: str = None):
    df = GLOBAL_DF_MASTER
    if semestre: df = df[df['semester'] == semestre]
    if materia: df = df[df['subject_name'] == materia]
        
    df_teachers = df.dropna(subset=['teacher_name'])
    docentes_stats = df_teachers.groupby('teacher_name').agg(
        total_estudiantes=('mortalidad', 'count'),
        tasa_mortalidad=('mortalidad', 'mean')
    ).reset_index()
    
    min_est = 20 if materia else 40
    docentes_stats = docentes_stats[docentes_stats['total_estudiantes'] >= min_est]
    top_docentes = docentes_stats.sort_values(by='tasa_mortalidad', ascending=False).head(15)
    top_docentes['tasa_mortalidad'] = top_docentes['tasa_mortalidad'].round(4)
    
    return clean_df_for_json(top_docentes[['teacher_name', 'total_estudiantes', 'tasa_mortalidad']])

@app.get("/api/adaptacion")
def get_adaptacion(semestre: str = None):
    df = GLOBAL_DF_EXCEL
    if semestre: df = df[df['semester'] == semestre]
        
    if 'antigüedad' in df.columns:
        df_clean = df.copy()
        df_clean['semestre'] = pd.to_numeric(df_clean['antigüedad'], errors='coerce')
        df_clean = df_clean.dropna(subset=['semestre'])
        df_curva = df_clean[(df_clean['semestre'] >= 1) & (df_clean['semestre'] <= 10)]
        
        curva_stats = df_curva.groupby('semestre').agg(mortalidad=('mortalidad', 'mean')).reset_index()
        curva_stats['mortalidad'] = curva_stats['mortalidad'].fillna(0).astype(float).round(4)
        curva_stats['semestre'] = curva_stats['semestre'].astype(int)
        
        return clean_df_for_json(curva_stats[['semestre', 'mortalidad']])
    return []

@app.get("/api/brecha-ciencias")
def get_brecha_ciencias(semestre: str = None):
    df = GLOBAL_DF_EXCEL
    if semestre: df = df[df['semester'] == semestre]
        
    if 'asignatura' in df.columns and 'sexo' in df.columns:
        materias_duras = df[df['asignatura'].str.contains('CALCULO|FISICA|ALGEBRA|PROGRAMACION', case=False, na=False)]
        if not materias_duras.empty:
            brecha_stats = materias_duras.groupby('sexo').agg(
                total_estudiantes=('mortalidad', 'count'),
                tasa_mortalidad=('mortalidad', 'mean')
            ).reset_index()
            brecha_stats['tasa_mortalidad'] = brecha_stats['tasa_mortalidad'].fillna(0).astype(float).round(4)
            return clean_df_for_json(brecha_stats[['sexo', 'total_estudiantes', 'tasa_mortalidad']])
    return []

@app.get("/api/materias-filtro")
def get_materias_filtro(semestre: str = None):
    df = GLOBAL_DF_EXCEL
    if semestre: df = df[df['semester'] == semestre]
    
    df_materias = df[~df['asignatura'].str.contains('NIVELATORIO|GRADO|PRACTICA', case=False, na=False)]
    materias_stats = df_materias.groupby('asignatura').agg(
        total_estudiantes=('mortalidad', 'count'),
        tasa_mortalidad=('mortalidad', 'mean')
    ).reset_index()
    
    materias_stats = materias_stats[materias_stats['total_estudiantes'] >= 30]
    top_filtros = materias_stats.sort_values(by='tasa_mortalidad', ascending=False).head(10)
    top_filtros['tasa_mortalidad'] = top_filtros['tasa_mortalidad'].astype(float).round(4)
    
    return clean_df_for_json(top_filtros[['asignatura', 'total_estudiantes', 'tasa_mortalidad']])

@app.get("/api/sedes")
def get_sedes(semestre: str = None):
    df = GLOBAL_DF_EXCEL
    if semestre: df = df[df['semester'] == semestre]
        
    if 'sede' in df.columns:
        sede_stats = df.groupby('sede').agg(
            total_estudiantes=('mortalidad', 'count'),
            tasa_mortalidad=('mortalidad', 'mean')
        ).reset_index()
        sede_stats = sede_stats[sede_stats['total_estudiantes'] >= 50]
        sede_stats = sede_stats.sort_values(by='tasa_mortalidad', ascending=False)
        sede_stats['tasa_mortalidad'] = sede_stats['tasa_mortalidad'].astype(float).round(4)
        return clean_df_for_json(sede_stats[['sede', 'total_estudiantes', 'tasa_mortalidad']])
    return []

@app.get("/api/jornada")
def get_jornada(semestre: str = None):
    df = GLOBAL_DF_EXCEL
    if semestre: df = df[df['semester'] == semestre]
        
    if 'jornada' in df.columns:
        jornada_stats = df.groupby('jornada').agg(
            total_estudiantes=('mortalidad', 'count'),
            tasa_mortalidad=('mortalidad', 'mean')
        ).reset_index()
        jornada_stats['tasa_mortalidad'] = jornada_stats['tasa_mortalidad'].astype(float).round(4)
        return clean_df_for_json(jornada_stats[['jornada', 'total_estudiantes', 'tasa_mortalidad']])
    return []

@app.get("/api/materias-list")
def get_materias_list():
    materias = sorted(GLOBAL_DF_MASTER['subject_name'].dropna().unique().tolist())
    return materias

@app.get("/")
def read_index():
    return FileResponse('public/index.html')

app.mount("/", StaticFiles(directory="public"), name="public")
