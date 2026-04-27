import os
import pandas as pd
import numpy as np
import gc
import uvicorn
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

# --- CONFIGURACIÓN DE MEMORIA (DIETA PANDAS) ---

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
    
    df = pd.DataFrame(all_data)
    # Optimización inmediata: Categorías y tipos reducidos
    for col in df.select_dtypes(include=['object']).columns:
        df[col] = df[col].astype('category')
    return df

def load_all_data():
    print("🚀 [MEM] Iniciando carga optimizada de datos...")
    
    # REGLA A: Columnas estrictas (Selective Columns)
    excel_cols = ['Año', 'Semestre', 'Sexo', 'Sede', 'Asignatura', 'Hora Inicial', 'Definitiva', 'Antiguedad']
    
    print("📥 Cargando Excel maestro (RAM Diet)...")
    df_ex = pd.read_excel("Desarrollo Curricular SIGA Semestre (1).xlsx", usecols=excel_cols)
    
    # Normalizar nombres
    df_ex.columns = df_ex.columns.str.strip().str.lower().str.replace(' ', '_').str.replace('antiguedad', 'antigüedad').str.replace('año', 'año')
    # Nota: pandas lower() no quita tildes, pero el user lo pedía así. 
    # El archivo dice 'Ao', pandas suele leerlo como 'Año' si el encoding es correcto.
    if 'año' not in df_ex.columns and 'ao' in df_ex.columns:
        df_ex = df_ex.rename(columns={'ao': 'año'})

    # REGLA C: Tipos numéricos reducidos (float32)
    if 'definitiva' in df_ex.columns:
        df_ex['definitiva_num'] = pd.to_numeric(df_ex['definitiva'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0).astype(np.float32)
        df_ex['mortalidad'] = (df_ex['definitiva_num'] < 3.0).astype(np.uint8)
    
    df_ex['semester'] = df_ex['año'].astype(str).str.replace('.0', '', regex=False) + '-' + df_ex['semestre'].astype(str).str.replace('.0', '', regex=False)
    
    if 'hora_inicial' in df_ex.columns:
        df_ex['hora_inicial_num'] = pd.to_numeric(df_ex['hora_inicial'], errors='coerce').astype(np.float32)
        df_ex['hora_real'] = df_ex['hora_inicial_num'].apply(lambda x: x + 12 if pd.notnull(x) and x <= 5 else x).astype(np.float32)
        df_ex['jornada'] = df_ex['hora_real'].apply(lambda x: 'Nocturna (18:00 - 22:00)' if x >= 18 else 'Diurna (06:00 - 17:59)')

    # REGLA B: Categorías para texto
    for col in df_ex.select_dtypes(include=['object']).columns:
        df_ex[col] = df_ex[col].astype('category')

    # 2. Cargar Supabase con columnas seleccionadas
    print("📥 Cargando datos desde Supabase (Selective Fetch)...")
    df_perf = fetch_table("academic_performance", "final_grade, group_id")
    df_groups = fetch_table("class_groups", "id, subject_id, teacher_id, semester").rename(columns={'id': 'group_id'})
    df_sched = fetch_table("group_schedules", "group_id, start_time, day_of_week")
    df_subjects = fetch_table("subjects", "id, name").rename(columns={'id': 'subject_id', 'name': 'subject_name'})
    df_teachers = fetch_table("teachers", "id, full_name").rename(columns={'id': 'teacher_id', 'full_name': 'teacher_name'})
    
    print("🔄 Cruzando tablas (Merge & Clean)...")
    df_ma = df_perf.merge(df_groups, on='group_id', how='inner')
    del df_perf, df_groups # Liberar RAM
    
    df_ma = df_ma.merge(df_sched, on='group_id', how='left')
    del df_sched
    
    df_ma = df_ma.merge(df_subjects, on='subject_id', how='left')
    del df_subjects
    
    df_ma = df_ma.merge(df_teachers, on='teacher_id', how='left')
    del df_teachers
    
    gc.collect()

    # Procesamiento Master
    df_ma['final_grade'] = pd.to_numeric(df_ma['final_grade'], errors='coerce').astype(np.float32)
    df_ma['mortalidad'] = (df_ma['final_grade'] < 3.0).astype(np.uint8)
    
    df_ma['hora_cruda'] = pd.to_datetime(df_ma['start_time'], format='%H:%M:%S', errors='coerce').dt.hour
    df_ma['hora_real'] = df_ma['hora_cruda'].apply(lambda x: x + 12 if pd.notnull(x) and x <= 5 else x).astype(np.float32)
    
    limites = [6, 8, 10, 12, 14, 16, 18, 20, 22]
    etiquetas = ['06:00-08:00', '08:00-10:00', '10:00-12:00', '12:00-14:00', '14:00-16:00', '16:00-18:00', '18:00-20:00', '20:00-22:00']
    df_ma['franja_horaria'] = pd.cut(df_ma['hora_real'], bins=limites, labels=etiquetas, right=False).astype('category')
    
    dias_semana = {1: 'Lunes', 2: 'Martes', 3: 'Miércoles', 4: 'Jueves', 5: 'Viernes', 6: 'Sábado'}
    df_ma['dia_nombre'] = df_ma['day_of_week'].map(dias_semana).astype('category')
    
    # REGLA B para el Master también
    for col in df_ma.select_dtypes(include=['object']).columns:
        df_ma[col] = df_ma[col].astype('category')

    print("✅ [MEM] Carga completada. RAM optimizada.")
    return df_ex, df_ma

# Carga inicial
GLOBAL_DF_EXCEL, GLOBAL_DF_MASTER = load_all_data()

# --- OPTIMIZACIÓN DE KPIs FIJOS ---
print("📊 Pre-calculando KPIs estáticos por semestre...")
STATIC_KPI_CACHE = {}
all_semesters = GLOBAL_DF_MASTER['semester'].unique()

for sem in all_semesters:
    df_s = GLOBAL_DF_MASTER[GLOBAL_DF_MASTER['semester'] == sem]
    m_global = round(float(df_s['mortalidad'].mean() * 100), 1) if not df_s.empty else 0.0
    t_est = int(len(df_s))
    
    # Asignatura crítica
    df_mat = df_s[~df_s['subject_name'].str.contains('NIVELATORIO|GRADO|PRACTICA', case=False, na=False)]
    m_stats = df_mat.groupby('subject_name', observed=True).agg(
        total_est=('mortalidad', 'count'),
        tasa_m=('mortalidad', 'mean')
    ).reset_index()
    m_stats = m_stats[m_stats['total_est'] >= 30]
    
    if not m_stats.empty:
        top = m_stats.sort_values(by='tasa_m', ascending=False).iloc[0]
        a_critica = {"nombre": str(top['subject_name']), "porcentaje": round(float(top['tasa_m'] * 100), 1)}
    else:
        a_critica = {"nombre": "N/A", "porcentaje": 0.0}
    
    STATIC_KPI_CACHE[sem] = {
        "mortalidad_global": m_global,
        "total_estudiantes": t_est,
        "asignatura_critica": a_critica
    }

def clean_df_for_json(df):
    # Ya están optimizados, solo convertir a nativos para JSON
    return df.replace({np.nan: None}).to_dict(orient='records')

# --- ENDPOINTS ---

@app.get("/api/kpis")
def get_kpis(semestre: str = None):
    if semestre in STATIC_KPI_CACHE:
        return STATIC_KPI_CACHE[semestre]
    # Fallback si no está pre-calculado
    return {"mortalidad_global": 0.0, "total_estudiantes": 0, "asignatura_critica": {"nombre": "N/A", "porcentaje": 0.0}}

@app.get("/api/heatmap")
def get_heatmap(semestre: str = None):
    df = GLOBAL_DF_MASTER
    if semestre: df = df[df['semester'] == semestre]
    
    heatmap_data = df.groupby(['franja_horaria', 'dia_nombre'], observed=True)['mortalidad'].mean().reset_index()
    heatmap_data['mortalidad'] = heatmap_data['mortalidad'].fillna(0).round(4).astype(float)
    return clean_df_for_json(heatmap_data[['franja_horaria', 'dia_nombre', 'mortalidad']])

@app.get("/api/teachers")
def get_teachers(semestre: str = None, materia: str = None):
    df = GLOBAL_DF_MASTER
    if semestre: df = df[df['semester'] == semestre]
    if materia: df = df[df['subject_name'] == materia]
        
    docentes_stats = df.groupby('teacher_name', observed=True).agg(
        total_estudiantes=('mortalidad', 'count'),
        tasa_mortalidad=('mortalidad', 'mean')
    ).reset_index()
    
    min_est = 20 if materia else 40
    docentes_stats = docentes_stats[docentes_stats['total_estudiantes'] >= min_est]
    top_docentes = docentes_stats.sort_values(by='tasa_mortalidad', ascending=False).head(15)
    top_docentes['tasa_mortalidad'] = top_docentes['tasa_mortalidad'].round(4).astype(float)
    return clean_df_for_json(top_docentes[['teacher_name', 'total_estudiantes', 'tasa_mortalidad']])

@app.get("/api/adaptacion")
def get_adaptacion(semestre: str = None):
    df = GLOBAL_DF_EXCEL
    if semestre: df = df[df['semester'] == semestre]
    
    if 'antigüedad' in df.columns:
        df_curva = df.copy()
        df_curva['semestre_val'] = pd.to_numeric(df_curva['antigüedad'], errors='coerce')
        df_curva = df_curva[(df_curva['semestre_val'] >= 1) & (df_curva['semestre_val'] <= 10)]
        
        curva_stats = df_curva.groupby('semestre_val', observed=True).agg(mortalidad=('mortalidad', 'mean')).reset_index()
        curva_stats['mortalidad'] = curva_stats['mortalidad'].round(4).astype(float)
        curva_stats = curva_stats.rename(columns={'semestre_val': 'semestre'})
        return clean_df_for_json(curva_stats)
    return []

@app.get("/api/brecha-ciencias")
def get_brecha_ciencias(semestre: str = None):
    df = GLOBAL_DF_EXCEL
    if semestre: df = df[df['semester'] == semestre]
    
    materias_duras = df[df['asignatura'].str.contains('CALCULO|FISICA|ALGEBRA|PROGRAMACION', case=False, na=False)]
    if not materias_duras.empty:
        brecha_stats = materias_duras.groupby('sexo', observed=True).agg(
            total_estudiantes=('mortalidad', 'count'),
            tasa_mortalidad=('mortalidad', 'mean')
        ).reset_index()
        brecha_stats['tasa_mortalidad'] = brecha_stats['tasa_mortalidad'].round(4).astype(float)
        return clean_df_for_json(brecha_stats)
    return []

@app.get("/api/materias-filtro")
def get_materias_filtro(semestre: str = None):
    df = GLOBAL_DF_EXCEL
    if semestre: df = df[df['semester'] == semestre]
    
    df_mat = df[~df['asignatura'].str.contains('NIVELATORIO|GRADO|PRACTICA', case=False, na=False)]
    stats = df_mat.groupby('asignatura', observed=True).agg(
        total_estudiantes=('mortalidad', 'count'),
        tasa_mortalidad=('mortalidad', 'mean')
    ).reset_index()
    
    stats = stats[stats['total_estudiantes'] >= 30]
    top = stats.sort_values(by='tasa_mortalidad', ascending=False).head(10)
    top['tasa_mortalidad'] = top['tasa_mortalidad'].round(4).astype(float)
    return clean_df_for_json(top)

@app.get("/api/sedes")
def get_sedes(semestre: str = None):
    df = GLOBAL_DF_EXCEL
    if semestre: df = df[df['semester'] == semestre]
    
    stats = df.groupby('sede', observed=True).agg(
        total_estudiantes=('mortalidad', 'count'),
        tasa_mortalidad=('mortalidad', 'mean')
    ).reset_index()
    stats = stats[stats['total_estudiantes'] >= 50]
    stats = stats.sort_values(by='tasa_mortalidad', ascending=False)
    stats['tasa_mortalidad'] = stats['tasa_mortalidad'].round(4).astype(float)
    return clean_df_for_json(stats)

@app.get("/api/jornada")
def get_jornada(semestre: str = None):
    df = GLOBAL_DF_EXCEL
    if semestre: df = df[df['semester'] == semestre]
    
    stats = df.groupby('jornada', observed=True).agg(
        total_estudiantes=('mortalidad', 'count'),
        tasa_mortalidad=('mortalidad', 'mean')
    ).reset_index()
    stats['tasa_mortalidad'] = stats['tasa_mortalidad'].round(4).astype(float)
    return clean_df_for_json(stats)

@app.get("/api/materias-list")
def get_materias_list():
    return sorted(GLOBAL_DF_MASTER['subject_name'].dropna().unique().tolist())

@app.get("/")
def read_index():
    return FileResponse('public/index.html')

app.mount("/", StaticFiles(directory="public"), name="public")

# FIX DEL PUERTO PARA RENDER
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("api:app", host="0.0.0.0", port=port)
