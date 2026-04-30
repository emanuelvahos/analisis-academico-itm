print("--- INICIANDO API.PY ---")
import os
import pandas as pd
import numpy as np
import gc
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from dotenv import load_dotenv
from supabase import create_client, Client

# Cargar variables de entorno
print("Cargando .env...")
load_dotenv()
print(".env cargado.")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

# --- COORDENADAS MEDELLÍN (Commute Map Dinámico) ---
try:
    # Carga del CSV oficial de barrios y veredas
    df_coords_csv = pd.read_csv('Barrios y veredas de Medellín.csv')
    COORDS_CSV = {str(row['Name']).lower().strip(): [row['Longitude'], row['Latitude']] for _, row in df_coords_csv.iterrows()}
except Exception as e:
    print(f"Error cargando CSV de coordenadas: {e}")
    COORDS_CSV = {}
print("Coordenadas base cargadas.")

# Inyección de Sedes ITM y alias comunes
COORDS_SEDES = {
    'robledo': [-75.594, 6.273],
    'fraternidad': [-75.556, 6.246],
    'fraternidad medellín': [-75.556, 6.246],
    'frat. medellín': [-75.556, 6.246],
    'castilla': [-75.570, 6.295],
    'floresta': [-75.590, 6.258]
}

# Diccionario maestro unificado (Prioridad a sedes si hay colisión)
COORDS_SAFE = {**COORDS_CSV, **COORDS_SEDES}

app = FastAPI(title="API Dashboard ITM")

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- CLIENTE SUPABASE ---
def get_supabase_client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

# --- CARGA DE DATOS DESDE SUPABASE ---

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
    # Optimización inmediata: Categorías
    for col in df.select_dtypes(include=['object']).columns:
        df[col] = df[col].astype('category')
    return df

def load_data_from_supabase():
    print("[SUPABASE] Iniciando reconstruccion relacional en RAM...")
    
    # 1. Descargar tablas
    df_perf = fetch_table("academic_performance").rename(columns={'id': 'performance_id'})
    df_groups = fetch_table("class_groups").rename(columns={'id': 'group_id'})
    df_subjects = fetch_table("subjects").rename(columns={'id': 'subject_id', 'name': 'subject_name'})
    df_teachers = fetch_table("teachers").rename(columns={'id': 'teacher_id', 'full_name': 'teacher_name'})
    df_programs = fetch_table("academic_programs").rename(columns={'id': 'program_id', 'name': 'program_name'})
    df_sched = fetch_table("group_schedules").rename(columns={'id': 'schedule_id'})

    # Modificaciones solicitadas por el usuario:
    df_students = fetch_table("students").rename(columns={'id': 'student_id'})
    df_campuses = fetch_table("campuses").rename(columns={'id': 'campus_id', 'name': 'sede_name'})

    # --- LIMPIEZA DE METADATOS PARA EVITAR COLISIONES EN MERGES ---
    # Eliminamos tenant_id y created_at de todas las tablas excepto la principal si fuera necesario
    # Pero para el dashboard no los necesitamos en RAM.
    metadata_cols = ['tenant_id', 'created_at']
    dfs_to_clean = [df_perf, df_groups, df_subjects, df_teachers, df_programs, df_sched, df_students, df_campuses]
    
    for _df in dfs_to_clean:
        cols_to_drop = [c for c in metadata_cols if c in _df.columns]
        if cols_to_drop:
            _df.drop(columns=cols_to_drop, inplace=True)

    print("[DATA] Mezclando datos relacionales...")
    
    # Grain: Estudiante-Grupo (Performance)
    df = df_perf.merge(df_groups, on='group_id', how='inner')
    df = df.merge(df_subjects, on='subject_id', how='left')
    df = df.merge(df_teachers, on='teacher_id', how='left')
    
    # Añadir cruces solicitados (y mantener los necesarios de students para kpis como gender, antiguedad, etc.)
    df = df.merge(df_students[['student_id', 'comuna', 'barrio', 'stratum', 'gender', 'antiguedad', 'campus_id', 'program_id']], on='student_id', how='left')
    df = df.merge(df_programs, on='program_id', how='left')
    df = df.merge(df_campuses[['campus_id', 'sede_name']], on='campus_id', how='left')

    # Capturar el total absoluto ANTES de borrar el DataFrame de memoria
    total_db = int(df_students['student_id'].nunique())

    # Renombramos temporalmente sede_name a campus_name para no quebrar otras gráficas que usen campus_name
    df['campus_name'] = df['sede_name']

    # Limpieza de memoria intermedia
    del df_perf, df_groups, df_subjects, df_teachers, df_students, df_programs, df_campuses
    gc.collect()

    # Procesamiento Master (Grain: Estudiante-Grupo)
    df['final_grade'] = pd.to_numeric(df['final_grade'], errors='coerce').astype(np.float32)
    df['mortalidad'] = (df['final_grade'] < 3.0).astype(np.uint8)
    
    # REGLA B: Categorías para texto
    for col in df.select_dtypes(include=['object']).columns:
        df[col] = df[col].astype('category')

    # Reconstrucción para Heatmap (Grain: Estudiante-Grupo-Horario)
    df_h = df.merge(df_sched, on='group_id', how='left')
    del df_sched
    gc.collect()

    df_h['hora_cruda'] = pd.to_datetime(df_h['start_time'], format='%H:%M:%S', errors='coerce').dt.hour
    df_h['hora_real'] = df_h['hora_cruda'].apply(lambda x: x + 12 if pd.notnull(x) and x <= 5 else x).astype(np.float32)
    
    limites = [6, 8, 10, 12, 14, 16, 18, 20, 22]
    etiquetas = ['06:00-08:00', '08:00-10:00', '10:00-12:00', '12:00-14:00', '14:00-16:00', '16:00-18:00', '18:00-20:00', '20:00-22:00']
    df_h['franja_horaria'] = pd.cut(df_h['hora_real'], bins=limites, labels=etiquetas, right=False).astype('category')
    
    dias_semana = {1: 'Lunes', 2: 'Martes', 3: 'Miércoles', 4: 'Jueves', 5: 'Viernes', 6: 'Sábado'}
    df_h['dia_nombre'] = df_h['day_of_week'].map(dias_semana).astype('category')

    print(f"[RAM] Datos cargados: {len(df)} registros de rendimiento, {df['student_id'].nunique()} estudiantes activos.")
    
    return df, df_h, total_db

# Carga global al inicio
GLOBAL_DF_MASTER, GLOBAL_DF_HEATMAP, TOTAL_ESTUDIANTES_INSTITUCION = load_data_from_supabase()

# --- OPTIMIZACIÓN DE KPIs ---
print("[KPI] Pre-calculando KPIs estaticos por semestre...")
STATIC_KPI_CACHE = {}
all_semesters = GLOBAL_DF_MASTER['semester'].unique()

for sem in all_semesters:
    df_s = GLOBAL_DF_MASTER[GLOBAL_DF_MASTER['semester'] == sem]
    m_global = round(float(df_s['mortalidad'].mean() * 100), 1) if not df_s.empty else 0.0
    
    # KPI TOTAL: Ahora muestra el 100% de la población institucional (ej. 28,076)
    t_est = TOTAL_ESTUDIANTES_INSTITUCION
    
    # Calcular cuántos están fuera de Medellín o sin datos
    invalid_neighborhoods = ['DESCONOCIDA', 'NAN', 'NONE', '', 'UNKNOWN', '** DESCONOCIDA **']
    df_s_mapped = df_s[~df_s['barrio'].astype(str).str.upper().str.strip().isin(invalid_neighborhoods)]
    est_con_mapa = int(df_s_mapped['student_id'].nunique())
    fuera_medellin = t_est - est_con_mapa
    
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
        "fuera_de_medellin_o_sin_datos": fuera_medellin,
        "asignatura_critica": a_critica
    }
    print(f"  - Semestre {sem} listo. (Total: {t_est})")

print("[KPI] Cache completado.")

def clean_df_for_json(df):
    return df.replace({np.nan: None}).to_dict(orient='records')

# --- ENDPOINTS ---

@app.get("/api/kpis")
def get_kpis(semestre: str = "2025-2"):
    # 1. Obtener el total absoluto de estudiantes usando el cliente Supabase
    supabase = get_supabase_client()
    response_total = supabase.table('students').select('*', count='exact').limit(1).execute()
    total_estudiantes = response_total.count if response_total.count else 0
    
    # 2. Recuperar el resto de métricas desde el cache
    kpis = STATIC_KPI_CACHE.get(semestre, {
        "mortalidad_global": 0.0, 
        "fuera_de_medellin_o_sin_datos": 0,
        "asignatura_critica": {"nombre": "N/A", "porcentaje": 0.0}
    })
    
    return {
        "total_estudiantes": total_estudiantes,
        "mortalidad_global": kpis["mortalidad_global"],
        "fuera_de_medellin_o_sin_datos": kpis["fuera_de_medellin_o_sin_datos"],
        "asignatura_critica": kpis["asignatura_critica"]
    }

@app.get("/api/kpi-fantasmas")
def get_kpi_fantasmas(semestre: str = None):
    try:
        # 1. Consulta con JOIN (Inner Join) para acceder al semestre en class_groups
        supabase = get_supabase_client()
        # class_groups!inner asegura que solo traiga registros con un grupo válido y permite filtrar por sus columnas
        query = supabase.table('academic_performance').select('student_id, final_grade, class_groups!inner(semester)')
        
        if semestre:
            query = query.eq('class_groups.semester', semestre)
        
        response = query.limit(100000).execute()
        data = response.data
        
        if not data:
            return {"estudiantes_fantasma": 0, "total_estudiantes": 0, "porcentaje": 0.0, "semestre": semestre} if semestre else []
            
        df = pd.DataFrame(data)
        
        # Aplanar la estructura del JOIN: class_groups es un dict con {'semester': '...'}
        df['semester'] = df['class_groups'].apply(lambda x: x['semester'] if isinstance(x, dict) else None)
        # Limpieza de notas a numérico
        df['final_grade'] = pd.to_numeric(df['final_grade'], errors='coerce').fillna(0)
        
        if semestre:
            # Caso: Un solo semestre solicitado
            total_estudiantes = df['student_id'].nunique()
            max_grades = df.groupby('student_id')['final_grade'].max()
            fantasmas = int((max_grades == 0).sum())
            porcentaje = round((fantasmas / total_estudiantes) * 100, 1) if total_estudiantes > 0 else 0.0
            
            return {
                "estudiantes_fantasma": fantasmas,
                "total_estudiantes": int(total_estudiantes),
                "porcentaje": porcentaje,
                "semestre": semestre
            }
        else:
            # Caso: Evolución histórica (todos los semestres disponibles)
            evolucion = []
            for sem_val, group in df.groupby('semester'):
                total_sem = group['student_id'].nunique()
                max_sem = group.groupby('student_id')['final_grade'].max()
                fantasmas_sem = int((max_sem == 0).sum())
                porcentaje_sem = round((fantasmas_sem / total_sem) * 100, 1) if total_sem > 0 else 0.0
                
                evolucion.append({
                    "semestre": str(sem_val),
                    "estudiantes_fantasma": fantasmas_sem,
                    "total_estudiantes": int(total_sem),
                    "porcentaje": porcentaje_sem
                })
            return sorted(evolucion, key=lambda x: x['semestre'], reverse=True)

    except Exception as e:
        print(f"Error en KPI Fantasmas: {e}")
        return JSONResponse(
            status_code=400, 
            content={"error": str(e), "estudiantes_fantasma": 0, "total_estudiantes": 0, "porcentaje": 0}
        )

@app.get("/api/heatmap")
def get_heatmap(semestre: str = "2025-2"):
    df = GLOBAL_DF_HEATMAP
    df = df[df['semester'] == semestre]
    
    heatmap_data = df.groupby(['franja_horaria', 'dia_nombre'], observed=True)['mortalidad'].mean().reset_index()
    heatmap_data['mortalidad'] = heatmap_data['mortalidad'].fillna(0).round(4).astype(float)
    return clean_df_for_json(heatmap_data[['franja_horaria', 'dia_nombre', 'mortalidad']])

@app.get("/api/teachers")
def get_teachers(semestre: str = "2025-2", materia: str = None):
    df = GLOBAL_DF_MASTER
    df = df[df['semester'] == semestre]
    if materia: df = df[df['subject_name'] == materia]
        
    docentes_stats = df.groupby('teacher_name', observed=True).agg(
        total_estudiantes=('mortalidad', 'count'),
        tasa_mortalidad=('mortalidad', 'mean')
    ).reset_index()
    
    min_est = 5 if materia else 40
    docentes_stats = docentes_stats[docentes_stats['total_estudiantes'] >= min_est]
    top_docentes = docentes_stats.sort_values(by='tasa_mortalidad', ascending=False).head(15)
    top_docentes['tasa_mortalidad'] = top_docentes['tasa_mortalidad'].round(4).astype(float)
    return clean_df_for_json(top_docentes[['teacher_name', 'total_estudiantes', 'tasa_mortalidad']])

@app.get("/api/adaptacion")
def get_adaptacion(semestre: str = "2025-2"):
    df = GLOBAL_DF_MASTER
    df = df[df['semester'] == semestre]
    
    # En el modelo relacional, antiguedad es texto (Nuevo, Antiguo, etc.)
    # Si queremos una curva por semestres, necesitaríamos que los estudiantes tuvieran ese dato numérico.
    # Por ahora, mostramos la mortalidad por categoría de antigüedad disponible.
    if 'antiguedad' in df.columns:
        curva_stats = df.groupby('antiguedad', observed=True).agg(mortalidad=('mortalidad', 'mean')).reset_index()
        curva_stats['mortalidad'] = curva_stats['mortalidad'].round(4).astype(float)
        curva_stats = curva_stats.rename(columns={'antiguedad': 'semestre'})
        return clean_df_for_json(curva_stats)
    return []

@app.get("/api/brecha-ciencias")
def get_brecha_ciencias(semestre: str = "2025-2"):
    df = GLOBAL_DF_MASTER
    df = df[df['semester'] == semestre]
    
    materias_duras = df[df['subject_name'].str.contains('CÁLCULO|FISICA|ALGEBRA|PROGRAMACIÓN|CALCULO', case=False, na=False)]
    if not materias_duras.empty:
        brecha_stats = materias_duras.groupby('gender', observed=True).agg(
            total_estudiantes=('mortalidad', 'count'),
            tasa_mortalidad=('mortalidad', 'mean')
        ).reset_index()
        brecha_stats['tasa_mortalidad'] = brecha_stats['tasa_mortalidad'].round(4).astype(float)
        return clean_df_for_json(brecha_stats.rename(columns={'gender': 'sexo'}))
    return []

@app.get("/api/materias-filtro")
def get_materias_filtro(semestre: str = "2025-2"):
    df = GLOBAL_DF_MASTER
    df = df[df['semester'] == semestre]
    
    df_mat = df[~df['subject_name'].str.contains('NIVELATORIO|GRADO|PRACTICA', case=False, na=False)]
    stats = df_mat.groupby('subject_name', observed=True).agg(
        total_estudiantes=('mortalidad', 'count'),
        tasa_mortalidad=('mortalidad', 'mean')
    ).reset_index()
    
    stats = stats[stats['total_estudiantes'] >= 30]
    top = stats.sort_values(by='tasa_mortalidad', ascending=False).head(10)
    top['tasa_mortalidad'] = top['tasa_mortalidad'].round(4).astype(float)
    return clean_df_for_json(top.rename(columns={'subject_name': 'asignatura'}))

@app.get("/api/sedes")
def get_sedes(semestre: str = "2025-2"):
    df = GLOBAL_DF_MASTER
    df = df[df['semester'] == semestre]
    
    stats = df.groupby('campus_name', observed=True).agg(
        total_estudiantes=('mortalidad', 'count'),
        tasa_mortalidad=('mortalidad', 'mean')
    ).reset_index()
    stats = stats[stats['total_estudiantes'] >= 50]
    stats = stats.sort_values(by='tasa_mortalidad', ascending=False)
    stats['tasa_mortalidad'] = stats['tasa_mortalidad'].round(4).astype(float)
    return clean_df_for_json(stats.rename(columns={'campus_name': 'sede'}))

@app.get("/api/jornada")
def get_jornada(semestre: str = "2025-2"):
    # La jornada depende del horario, usamos el grain de heatmap
    df = GLOBAL_DF_HEATMAP
    df = df[df['semester'] == semestre]
    
    # Recalcular jornada si no existe
    df['jornada'] = df['hora_real'].apply(lambda x: 'Nocturna (18:00 - 22:00)' if x >= 18 else 'Diurna (06:00 - 17:59)')
    
    stats = df.groupby('jornada', observed=True).agg(
        total_estudiantes=('mortalidad', 'count'),
        tasa_mortalidad=('mortalidad', 'mean')
    ).reset_index()
    stats['tasa_mortalidad'] = stats['tasa_mortalidad'].round(4).astype(float)
    return clean_df_for_json(stats)

@app.get("/api/rutas-transporte")
def get_rutas_transporte(semestre: str = "2025-2"):
    df = GLOBAL_DF_MASTER
    df = df[df['semester'] == semestre]
    
    # Agrupar por BARRIO de residencia y sede de estudio para mayor precisión
    # Incluimos la comuna para tener un plan B de mapeo
    rutas = df.groupby(['barrio', 'sede_name', 'comuna'], observed=True).size().reset_index(name='cantidad')
    
    # Filtrar cantidad > 2 (al ser barrios, el grano es más fino)
    rutas = rutas[rutas['cantidad'] > 2]

    # Normalización para el match
    rutas['barrio_norm'] = rutas['barrio'].astype(str).str.lower().str.strip()
    rutas['comuna_norm'] = rutas['comuna'].astype(str).str.lower().str.strip()
    rutas['destino_norm'] = rutas['sede_name'].astype(str).str.lower().str.strip()
    
    # 1. Intentar cruzar por BARRIO
    rutas['origen_coords'] = rutas['barrio_norm'].map(COORDS_SAFE)
    
    # 2. Plan B: Si falló el barrio, intentar por COMUNA
    mask_retry = rutas['origen_coords'].isna()
    rutas.loc[mask_retry, 'origen_coords'] = rutas.loc[mask_retry, 'comuna_norm'].map(COORDS_SAFE)
    
    # 3. Plan C: Si sigue fallando, intentar con el sufijo _comuna (compatibilidad con dict anterior)
    mask_retry_2 = rutas['origen_coords'].isna()
    rutas.loc[mask_retry_2, 'origen_coords'] = (rutas.loc[mask_retry_2, 'comuna_norm'] + "_comuna").map(COORDS_SAFE)
    
    # Mapear Destino (Sede)
    rutas['destino_coords'] = rutas['destino_norm'].map(COORDS_SAFE)
    
    # Eliminar los que no cruzaron (NaN en coordenadas)
    df_limpio = rutas.dropna(subset=['origen_coords', 'destino_coords'])
    
    result = []
    for _, row in df_limpio.iterrows():
        # Usamos el nombre del barrio como origen principal
        origen_display = str(row['barrio']).title() if pd.notnull(row['barrio']) else str(row['comuna']).title()
        
        result.append({
            "coords": [row['origen_coords'], row['destino_coords']],
            "value": int(row['cantidad']),
            "origen": origen_display,
            "destino": str(row['sede_name']).title()
        })
    
    print(f"DEBUG: Rutas (BARRIOS) mapeadas: {len(result)} con éxito")
    return result

@app.get("/api/mapa-poligonos")
def get_mapa_poligonos(semestre: str = "2025-2", metrica: str = 'poblacion', nivel_geo: str = 'barrio'):
    df = GLOBAL_DF_MASTER
    df = df[df['semester'] == semestre].copy()
    
    # Columna objetivo según el nivel (barrio o comuna)
    col_geo = 'barrio' if nivel_geo == 'barrio' else 'comuna'
    
    # Limpiar columna (UPPER CASE para cruzar con GeoJSON oficial)
    df[col_geo] = df[col_geo].astype(str).str.upper().str.strip()
    
    # Cálculo de totales por la unidad geográfica elegida (estudiantes únicos)
    totales = df.groupby(col_geo, observed=True)['student_id'].nunique().reset_index(name='total_estudiantes')

    # Lógica de cálculo según la métrica
    if metrica == 'poblacion':
        res = totales.rename(columns={'total_estudiantes': 'value'})
    elif metrica == 'aprobacion':
        df['aprobado'] = (df['final_grade'] >= 3.0).astype(int)
        res = df.groupby(col_geo, observed=True)['aprobado'].mean().reset_index(name='value')
        res['value'] = (res['value'] * 100).round(1)
    elif metrica == 'riesgo':
        res = df.groupby(col_geo, observed=True)['mortalidad'].mean().reset_index(name='value')
        res['value'] = (res['value'] * 100).round(1)
    else:
        return []
    
    # Unir con totales
    res = res.merge(totales, on=col_geo, how='left')
    
    # Formato final para ECharts [{"name": "Barrio/Comuna", "value": X, "total_estudiantes": Y}]
    res = res.dropna(subset=['value'])
    # NO FILTRAMOS AQUÍ: Enviamos todo para que el frontend separe Medellín de otros municipios
    res = res.rename(columns={col_geo: 'name'})
    
    return clean_df_for_json(res[['name', 'value', 'total_estudiantes']])

@app.get("/api/materias-list")
def get_materias_list():
    return sorted(GLOBAL_DF_MASTER['subject_name'].dropna().unique().tolist())

@app.get("/")
def read_index():
    return FileResponse('public/index.html')

app.mount("/", StaticFiles(directory="public"), name="public")

# ARRANQUE PARA RENDER
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("api:app", host="0.0.0.0", port=port)
