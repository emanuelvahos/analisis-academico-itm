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
import unicodedata
from supabase import create_client, Client
import re

def clean_geo_string(text: str) -> str:
    if not isinstance(text, str): return ""
    # 1. Quitar tildes
    text = ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')
    # 2. Minusculas y quitar caracteres especiales (guiones, comas, puntos)
    text = re.sub(r'[^a-z0-9\s]', '', text.lower())
    # 3. Quitar la palabra "barrio" o "comuna" si viene pegada
    text = re.sub(r'\b(barrio|comuna)\b', '', text)
    # 4. Quitar espacios dobles
    return ' '.join(text.split())

def remove_accents(text: str) -> str:
    if not isinstance(text, str): return ""
    return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')

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
    COORDS_CSV = {clean_geo_string(str(row['Name'])): [row['Longitude'], row['Latitude']] for _, row in df_coords_csv.iterrows()}
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

MUNICIPIOS_EXTERNOS = ['bello', 'itagui', 'envigado', 'sabaneta', 'copacabana', 'girardota', 'caldas', 'la estrella', 'barbosa', 'rionegro', 'apartado', 'marinilla']

# Diccionario maestro unificado (Prioridad a sedes si hay colisión)
COORDS_SAFE = {**COORDS_CSV, **{clean_geo_string(k): v for k, v in COORDS_SEDES.items()}}

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

# --- HELPER: Consulta paginada a Supabase (supera el límite de 1000 filas) ---
def supabase_fetch_all(table: str, select: str, filters: dict = None, page_size: int = 1000) -> list:
    """Trae TODOS los registros de una tabla usando paginación con .range().
    PostgREST ignora .limit() > 1000, así que paginamos manualmente."""
    sb = get_supabase_client()
    all_data = []
    offset = 0
    while True:
        q = sb.table(table).select(select)
        if filters:
            for col, val in filters.items():
                q = q.eq(col, val)
        batch = q.range(offset, offset + page_size - 1).execute().data or []
        all_data.extend(batch)
        if len(batch) < page_size:
            break  # Última página
        offset += page_size
    return all_data

def clean_df_for_json(df: pd.DataFrame) -> list:
    return df.replace({np.nan: None}).to_dict(orient='records')

def flatten_join(row: dict, join_table: str) -> dict:
    """Aplana columnas anidadas de un JOIN de Supabase al nivel raíz del dict."""
    nested = row.get(join_table)
    if isinstance(nested, dict):
        for k, v in nested.items():
            row[k] = v
    return row



# --- ENDPOINTS ---

@app.get("/api/kpis")
def get_kpis(semestre: str = "2025-2"):
    try:
        sb = get_supabase_client()
        # Total absoluto: solo tabla students, sin joins
        r_total = sb.table('students').select('*', count='exact').limit(1).execute()
        total_estudiantes = r_total.count or 0

        # Mortalidad global del semestre
        # Traemos también el nombre de la asignatura para el KPI dinámico
        sel = 'student_id, final_grade, class_groups!inner(semester, subjects(name))'
        data_perf = sb.table('academic_performance').select(sel).eq('class_groups.semester', semestre).limit(100000).execute().data or []
        
        mortalidad_global = 0.0
        asignatura_critica = {"nombre": "N/A", "porcentaje": 0.0}
        fuera_mapa = 0

        if data_perf:
            df = pd.DataFrame(data_perf)
            df['final_grade'] = pd.to_numeric(df['final_grade'], errors='coerce').fillna(0)
            df['mortalidad'] = (df['final_grade'] < 3.0).astype(int)
            mortalidad_global = round(float(df['mortalidad'].mean() * 100), 1)

            # --- Lógica de Asignatura Crítica ---
            # Extraer nombre de la materia (navegación segura)
            df['subject_name'] = df['class_groups'].apply(lambda x: x.get('subjects', {}).get('name', 'N/A') if isinstance(x, dict) else 'N/A')
            
            # Agrupar para encontrar la de mayor mortalidad (Mínimo 10 estudiantes)
            subjects_stats = df.groupby('subject_name').agg(
                total_estudiantes=('mortalidad', 'count'),
                tasa_mortalidad=('mortalidad', 'mean')
            ).reset_index()
            
            # Filtro de muestra estadística
            subjects_stats = subjects_stats[subjects_stats['total_estudiantes'] >= 10]
            
            if not subjects_stats.empty:
                critica = subjects_stats.sort_values('tasa_mortalidad', ascending=False).iloc[0]
                asignatura_critica = {
                    "nombre": critica['subject_name'],
                    "porcentaje": round(float(critica['tasa_mortalidad'] * 100), 1)
                }

        # Estudiantes sin barrio valido
        data_stu = supabase_fetch_all('students', 'id, barrio')
        if data_stu:
            df_s = pd.DataFrame(data_stu)
            invalidos = ['DESCONOCIDA','NAN','NONE','','UNKNOWN','** DESCONOCIDA **']
            fuera_mapa = int(df_s[df_s['barrio'].astype(str).str.upper().str.strip().isin(invalidos)].shape[0])

        return {
            "total_estudiantes": total_estudiantes,
            "mortalidad_global": mortalidad_global,
            "fuera_de_medellin_o_sin_datos": fuera_mapa,
            "asignatura_critica": asignatura_critica
        }
    except Exception as e:
        print(f"Error KPIs: {e}")
        return JSONResponse(status_code=400, content={"error": str(e)})

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
    try:
        data = supabase_fetch_all('academic_performance', 'student_id, final_grade, class_groups!inner(semester, group_schedules(start_time, day_of_week))', {'class_groups.semester': semestre})
        if not data: return []
        df = pd.DataFrame(data)
        # 1. Normalizar notas (por si vienen con coma colombiana) y quitar nulos
        df['final_grade'] = df['final_grade'].astype(str).str.replace(',', '.')
        df['final_grade'] = pd.to_numeric(df['final_grade'], errors='coerce')
        df = df.dropna(subset=['final_grade'])

        df['mortalidad'] = (df['final_grade'] < 3.0).astype(int)
        def extract_sched(row):
            cg = row.get('class_groups', {})
            scheds = cg.get('group_schedules', []) if isinstance(cg, dict) else []
            return scheds[0] if scheds else {}
        df['sched'] = df.apply(extract_sched, axis=1)
        df['start_time'] = df['sched'].apply(lambda x: x.get('start_time') if isinstance(x, dict) else None)
        df['day_of_week'] = df['sched'].apply(lambda x: x.get('day_of_week') if isinstance(x, dict) else None)
        df['hora'] = pd.to_datetime(df['start_time'], format='%H:%M:%S', errors='coerce').dt.hour
        df['hora'] = df['hora'].apply(lambda x: x + 12 if pd.notnull(x) and x <= 5 else x)
        limites = [6,8,10,12,14,16,18,20,22]
        etiquetas = ['06:00-08:00','08:00-10:00','10:00-12:00','12:00-14:00','14:00-16:00','16:00-18:00','18:00-20:00','20:00-22:00']
        df['franja_horaria'] = pd.cut(df['hora'], bins=limites, labels=etiquetas, right=False).astype(str)
        dias = {1:'Lunes',2:'Martes',3:'Miércoles',4:'Jueves',5:'Viernes',6:'Sábado'}
        df['dia_nombre'] = df['day_of_week'].map(dias)
        df = df.dropna(subset=['franja_horaria','dia_nombre'])
        result = df.groupby(['franja_horaria','dia_nombre'])['mortalidad'].mean().reset_index()
        result['mortalidad'] = result['mortalidad'].round(4)
        return clean_df_for_json(result)
    except Exception as e:
        print(f"Error heatmap: {e}")
        return JSONResponse(status_code=400, content={"error": str(e)})

@app.get("/api/teachers")
def get_teachers(semestre: str = "2025-2", materia: str = None):
    try:
        sel = 'student_id, final_grade, class_groups!inner(semester, subjects(name), teachers(full_name))'
        filters = {'class_groups.semester': semestre}
        if materia:
            filters['class_groups.subjects.name'] = materia
        data = supabase_fetch_all('academic_performance', sel, filters)
        if not data: return []
        df = pd.DataFrame(data)
        # Navegación segura con `or {}` para evitar NoneType.get()
        def extract_teacher(x):
            cg = x if isinstance(x, dict) else {}
            teacher = cg.get('teachers') or {}
            return teacher.get('full_name')  # None si no tiene docente asignado
        df['teacher_name'] = df['class_groups'].apply(extract_teacher)
        
        # 1. Normalizar notas (por si vienen con coma colombiana) y quitar nulos
        df['final_grade'] = df['final_grade'].astype(str).str.replace(',', '.')
        df['final_grade'] = pd.to_numeric(df['final_grade'], errors='coerce')
        df = df.dropna(subset=['final_grade', 'teacher_name'])

        # 2. Agrupar manteniendo a todos los estudiantes (aprobados y reprobados)
        stats = df.groupby('teacher_name').agg(
            total_estudiantes=('student_id', 'nunique'),
            reprobados=('final_grade', lambda x: (x < 3.0).sum())
        ).reset_index()

        # 3. Calcular la tasa pura (SIN multiplicar por 100)
        stats['tasa_mortalidad'] = (stats['reprobados'] / stats['total_estudiantes']).round(4).fillna(0)

        min_est = 3 if materia else 5
        stats = stats[stats['total_estudiantes'] >= min_est].sort_values('tasa_mortalidad', ascending=False).head(15)
        
        # 4. Retornar con las llaves originales que consume main.js
        return clean_df_for_json(stats)
    except Exception as e:
        print(f"Error teachers: {e}")
        return JSONResponse(status_code=400, content={"error": str(e)})


@app.get("/api/adaptacion")
def get_adaptacion(semestre: str = "2025-2"):
    try:
        sb = get_supabase_client()
        # Clave primaria es 'id', no 'student_id'
        data = supabase_fetch_all('students', 'id, antiguedad')
        data_perf = sb.table('academic_performance').select('student_id, final_grade, class_groups!inner(semester)').eq('class_groups.semester', semestre).limit(100000).execute().data or []
        if not data_perf: return []
        df_p = pd.DataFrame(data_perf)
        df_p['final_grade'] = pd.to_numeric(df_p['final_grade'], errors='coerce').fillna(0)
        df_p['mortalidad'] = (df_p['final_grade'] < 3.0).astype(int)
        # Renombrar 'id' → 'student_id' para poder hacer el merge
        df_s = pd.DataFrame(data).rename(columns={'id': 'student_id'})[['student_id', 'antiguedad']]
        df = df_p.merge(df_s, on='student_id', how='left')
        if 'antiguedad' not in df.columns: return []
        result = df.groupby('antiguedad')['mortalidad'].mean().reset_index()
        result['mortalidad'] = result['mortalidad'].round(4)
        result = result.rename(columns={'antiguedad': 'semestre'})
        return clean_df_for_json(result)
    except Exception as e:
        print(f"Error adaptacion: {e}")
        return JSONResponse(status_code=400, content={"error": str(e)})


@app.get("/api/brecha-ciencias")
def get_brecha_ciencias(semestre: str = "2025-2"):
    try:
        data = supabase_fetch_all('academic_performance', 'student_id, final_grade, class_groups!inner(semester, subjects(name))', {'class_groups.semester': semestre})
        if not data: return []
        df = pd.DataFrame(data)
        df['subject_name'] = df['class_groups'].apply(lambda x: x.get('subjects', {}).get('name','') if isinstance(x,dict) else '')
        df = df[df['subject_name'].str.contains('CÁLCULO|FISICA|ALGEBRA|PROGRAMACIÓN|CALCULO', case=False, na=False)]
        if df.empty: return []
        
        data_s = supabase_fetch_all('students', 'id, gender')
        df_gen = pd.DataFrame(data_s).rename(columns={'id':'student_id'})
        df = df.merge(df_gen, on='student_id', how='inner')
        
        # 1. Normalizar notas (por si vienen con coma colombiana) y quitar nulos
        df['final_grade'] = df['final_grade'].astype(str).str.replace(',', '.')
        df['final_grade'] = pd.to_numeric(df['final_grade'], errors='coerce')
        df = df.dropna(subset=['final_grade'])

        # 2. Agrupar manteniendo a todos los estudiantes (aprobados y reprobados)
        stats = df.groupby('gender').agg(
            total_estudiantes=('student_id', 'nunique'),
            reprobados=('final_grade', lambda x: (x < 3.0).sum())
        ).reset_index()

        # 3. Calcular la tasa pura (SIN multiplicar por 100)
        stats['tasa_mortalidad'] = (stats['reprobados'] / stats['total_estudiantes']).round(4).fillna(0)

        # 4. Retornar con las llaves originales que consume main.js (sexo, tasa_mortalidad)
        return clean_df_for_json(stats.rename(columns={'gender': 'sexo'}))
    except Exception as e:
        print(f"Error brecha: {e}")
        return JSONResponse(status_code=400, content={"error": str(e)})

@app.get("/api/materias-filtro")
def get_materias_filtro(semestre: str = "2025-2"):
    try:
        data = supabase_fetch_all('academic_performance', 'student_id, final_grade, class_groups!inner(semester, subjects(name))', {'class_groups.semester': semestre})
        if not data: return []
        df = pd.DataFrame(data)
        df['subject_name'] = df['class_groups'].apply(lambda x: x.get('subjects',{}).get('name','') if isinstance(x,dict) else '')
        df = df[~df['subject_name'].str.contains('NIVELATORIO|GRADO|PRACTICA', case=False, na=False)]
        
        # 1. Normalizar notas (por si vienen con coma colombiana) y quitar nulos
        df['final_grade'] = df['final_grade'].astype(str).str.replace(',', '.')
        df['final_grade'] = pd.to_numeric(df['final_grade'], errors='coerce')
        df = df.dropna(subset=['final_grade'])

        # 2. Agrupar manteniendo a todos los estudiantes (aprobados y reprobados)
        stats = df.groupby('subject_name').agg(
            total_estudiantes=('student_id', 'nunique'),
            reprobados=('final_grade', lambda x: (x < 3.0).sum())
        ).reset_index()

        # 3. Calcular la tasa pura (SIN multiplicar por 100)
        stats['tasa_mortalidad'] = (stats['reprobados'] / stats['total_estudiantes']).round(4).fillna(0)

        stats = stats[stats['total_estudiantes']>=30].sort_values('tasa_mortalidad', ascending=False).head(10)
        
        # 4. Retornar con las llaves originales que consume main.js (asignatura, tasa_mortalidad)
        return clean_df_for_json(stats.rename(columns={'subject_name': 'asignatura'}))
    except Exception as e:
        print(f"Error materias-filtro: {e}")
        return JSONResponse(status_code=400, content={"error": str(e)})

@app.get("/api/sedes")
def get_sedes(semestre: str = "2025-2"):
    try:
        data = supabase_fetch_all('academic_performance', 'student_id, final_grade, class_groups!inner(semester)', {'class_groups.semester': semestre})
        if not data: return []
        df = pd.DataFrame(data)
        data_s = supabase_fetch_all('students', 'id, campus_id')
        data_c = sb.table('campuses').select('id, name').limit(100000).execute().data or []
        df_s = pd.DataFrame(data_s).rename(columns={'id':'student_id'})
        df_c = pd.DataFrame(data_c).rename(columns={'id':'campus_id','name':'sede'})
        df_s = df_s.merge(df_c, on='campus_id', how='left')
        df = df.merge(df_s, on='student_id', how='inner')
        
        # 1. Normalizar notas (por si vienen con coma colombiana) y quitar nulos
        df['final_grade'] = df['final_grade'].astype(str).str.replace(',', '.')
        df['final_grade'] = pd.to_numeric(df['final_grade'], errors='coerce')
        df = df.dropna(subset=['final_grade'])

        # 2. Agrupar manteniendo a todos los estudiantes (aprobados y reprobados)
        stats = df.groupby('sede').agg(
            total_estudiantes=('student_id', 'nunique'),
            reprobados=('final_grade', lambda x: (x < 3.0).sum())
        ).reset_index()

        # 3. Calcular la tasa pura (SIN multiplicar por 100)
        stats['tasa_mortalidad'] = (stats['reprobados'] / stats['total_estudiantes']).round(4).fillna(0)

        stats = stats[stats['total_estudiantes']>=10].sort_values('tasa_mortalidad', ascending=False)
        
        # 4. Retornar con las llaves originales que consume main.js (sede, tasa_mortalidad)
        return clean_df_for_json(stats[['sede', 'total_estudiantes', 'reprobados', 'tasa_mortalidad']])
    except Exception as e:
        print(f"Error sedes: {e}")
        return JSONResponse(status_code=400, content={"error": str(e)})

@app.get("/api/jornada")
def get_jornada(semestre: str = "2025-2"):
    try:
        data = supabase_fetch_all('academic_performance', 'student_id, final_grade, class_groups!inner(semester, group_schedules(start_time))', {'class_groups.semester': semestre})
        if not data: return []
        df = pd.DataFrame(data)
        def get_hora(row):
            cg = row.get('class_groups', {})
            scheds = cg.get('group_schedules', []) if isinstance(cg, dict) else []
            if scheds:
                t = pd.to_datetime(scheds[0].get('start_time',''), format='%H:%M:%S', errors='coerce')
                if pd.notnull(t):
                    h = t.hour
                    return h + 12 if h <= 5 else h
            return None
        df['hora'] = df.apply(get_hora, axis=1)
        
        # 1. Normalizar notas (por si vienen con coma colombiana) y quitar nulos
        df['final_grade'] = df['final_grade'].astype(str).str.replace(',', '.')
        df['final_grade'] = pd.to_numeric(df['final_grade'], errors='coerce')
        df = df.dropna(subset=['hora', 'final_grade'])
        
        df['jornada'] = df['hora'].apply(lambda x: 'Nocturna (18:00 - 22:00)' if x >= 18 else 'Diurna (06:00 - 17:59)')
        
        # 2. Agrupar manteniendo a todos los estudiantes (aprobados y reprobados)
        stats = df.groupby('jornada').agg(
            total_estudiantes=('student_id', 'nunique'),
            reprobados=('final_grade', lambda x: (x < 3.0).sum())
        ).reset_index()

        # 3. Calcular la tasa pura (SIN multiplicar por 100)
        stats['tasa_mortalidad'] = (stats['reprobados'] / stats['total_estudiantes']).round(4).fillna(0)
        
        # 4. Retornar con las llaves originales que consume main.js (jornada, tasa_mortalidad)
        return clean_df_for_json(stats)
    except Exception as e:
        print(f"Error jornada: {e}")
        return JSONResponse(status_code=400, content={"error": str(e)})

@app.get("/api/rutas-transporte")
def get_rutas_transporte(semestre: str = "2025-2"):
    try:
        sb = get_supabase_client()
        # Obtener estudiantes activos en el semestre
        data_perf = sb.table('academic_performance').select('student_id, class_groups!inner(semester)').eq('class_groups.semester', semestre).limit(100000).execute().data or []
        if not data_perf: return []
        student_ids = list({r['student_id'] for r in data_perf})
        
        # Traer datos geográficos de todos los estudiantes y filtrar en Python
        data_s = supabase_fetch_all('students', 'id, barrio, comuna, campus_id')
        data_c = sb.table('campuses').select('id, name').limit(100000).execute().data or []
        
        df_s = pd.DataFrame(data_s).rename(columns={'id': 'student_id'})
        df_c = pd.DataFrame(data_c).rename(columns={'id': 'campus_id', 'name': 'sede_name'})
        
        # Filtrar solo estudiantes del semestre
        df_s = df_s[df_s['student_id'].isin(student_ids)].copy()
        df_s = df_s.merge(df_c, on='campus_id', how='left')
        
        # Normalizar sede_name
        df_s['sede_name'] = df_s['sede_name'].fillna('').astype(str).str.strip()
        
        # Limpiar geografía y agrupar externos
        df_s['barrio_limpio'] = df_s['barrio'].fillna('').astype(str).apply(clean_geo_string)
        df_s.loc[df_s['barrio_limpio'].isin(MUNICIPIOS_EXTERNOS), 'barrio_limpio'] = 'Otro Municipio'
        df_s.loc[df_s['comuna'].astype(str).str.lower().str.contains('|'.join(MUNICIPIOS_EXTERNOS), na=False), 'barrio_limpio'] = 'Otro Municipio'
        
        df_s['comuna_limpia'] = df_s['comuna'].fillna('').astype(str).apply(clean_geo_string)
        
        rutas = df_s.groupby(['barrio_limpio','sede_name','comuna_limpia']).size().reset_index(name='cantidad')
        rutas = rutas[rutas['cantidad'] > 0]
        
        rutas['barrio_norm'] = rutas['barrio_limpio']
        rutas['comuna_norm'] = rutas['comuna_limpia']
        rutas['destino_norm'] = rutas['sede_name'].str.lower().str.strip().apply(clean_geo_string)
        
        # Debug: mostrar las claves disponibles y qué barrios hay
        print(f"[DEBUG rutas] Barrios únicos (muestra): {rutas['barrio_norm'].unique()[:5].tolist()}")
        print(f"[DEBUG rutas] Destinos únicos: {rutas['destino_norm'].unique().tolist()}")
        print(f"[DEBUG rutas] Claves COORDS_SAFE (muestra): {list(COORDS_SAFE.keys())[:5]}")
        
        rutas['origen_coords'] = rutas['barrio_norm'].map(COORDS_SAFE)
        mask = rutas['origen_coords'].isna()
        # Plan B: intentar por comuna
        rutas.loc[mask, 'origen_coords'] = rutas.loc[mask, 'comuna_norm'].map(COORDS_SAFE)
        rutas['destino_coords'] = rutas['destino_norm'].map(COORDS_SAFE)
        
        df_limpio = rutas.dropna(subset=['origen_coords','destino_coords'])
        print(f"[DEBUG rutas] Total rutas con coords: {len(df_limpio)} de {len(rutas)} posibles")
        
        result = []
        for _, row in df_limpio.iterrows():
            origen_display = str(row['barrio_limpio']).title() if row['barrio_limpio'] else str(row['comuna_limpia']).title()
            result.append({
                "coords": [row['origen_coords'], row['destino_coords']],
                "value": int(row['cantidad']),
                "origen": origen_display,
                "destino": str(row['sede_name']).title()
            })
        print(f"DEBUG: Rutas mapeadas: {len(result)}")
        return result
    except Exception as e:
        print(f"Error rutas: {e}")
        return JSONResponse(status_code=400, content={"error": str(e)})



@app.get("/api/mapa-poligonos")
def get_mapa_poligonos(semestre: str = "2025-2", metrica: str = 'poblacion', nivel_geo: str = 'barrio'):
    try:
        sb = get_supabase_client()
        col_geo = 'barrio' if nivel_geo == 'barrio' else 'comuna'
        
        # 1. Notas del semestre (grain: registro-nota)
        data_perf = sb.table('academic_performance').select('student_id, final_grade, class_groups!inner(semester)').eq('class_groups.semester', semestre).limit(100000).execute().data or []
        if not data_perf: return []
        
        # 2. Solo los estudiantes activos en ese semestre
        student_ids_activos = list({r['student_id'] for r in data_perf})
        
        # 3. Datos geográficos de todos los estudiantes
        data_s = supabase_fetch_all('students', 'id, barrio, comuna')
        
        df_p = pd.DataFrame(data_perf)
        # 1. Normalizar notas (por si vienen con coma colombiana) y quitar nulos
        df_p['final_grade'] = df_p['final_grade'].astype(str).str.replace(',', '.')
        df_p['final_grade'] = pd.to_numeric(df_p['final_grade'], errors='coerce')
        df_p = df_p.dropna(subset=['final_grade'])
        
        # Filtrar students al universo del semestre
        df_s = pd.DataFrame(data_s).rename(columns={'id': 'student_id'})
        df_s = df_s[df_s['student_id'].isin(student_ids_activos)]
        
        # 4. JOIN: unir notas con barrio/comuna del estudiante
        df = df_p.merge(df_s, on='student_id', how='left')
        
        # Limpiar geografía y agrupar externos
        df['barrio_limpio'] = df['barrio'].fillna('').astype(str).apply(clean_geo_string)
        df.loc[df['barrio_limpio'].isin(MUNICIPIOS_EXTERNOS), 'barrio_limpio'] = 'Otro Municipio'
        # Intentar atrapar externos desde la comuna si el barrio no lo indicó
        if 'comuna' in df.columns:
            df.loc[df['comuna'].astype(str).str.lower().str.contains('|'.join(MUNICIPIOS_EXTERNOS), na=False), 'barrio_limpio'] = 'Otro Municipio'
            df['comuna_limpia'] = df['comuna'].fillna('').astype(str).apply(clean_geo_string)
            df.loc[df['comuna_limpia'].isin(MUNICIPIOS_EXTERNOS), 'comuna_limpia'] = 'Otro Municipio'
            df['comuna'] = df['comuna_limpia']
            
        df['barrio'] = df['barrio_limpio']

        # 5. Normalizar a MAYUSCULAS para cruzar con GeoJSON
        df[col_geo] = df[col_geo].fillna('DESCONOCIDO').astype(str).str.upper().str.strip()
        df.loc[df[col_geo].isin(['NAN','NONE','','** DESCONOCIDA **', 'DESCONOCIDO']), col_geo] = 'DESCONOCIDO'
        
        totales = df.groupby(col_geo)['student_id'].nunique().reset_index(name='total_estudiantes')
        
        if metrica == 'poblacion':
            res = totales.rename(columns={'total_estudiantes': 'value'})
        elif metrica == 'aprobacion':
            df['aprobado'] = (df['final_grade'] >= 3.0).astype(int)
            agg = df.groupby(col_geo).agg(aprobados=('aprobado','sum'), total=('aprobado','count')).reset_index()
            agg['value'] = np.where(agg['total']>0, (agg['aprobados']/agg['total']), 0.0)
            agg['value'] = agg['value'].round(4)
            res = agg[[col_geo,'value']]
        elif metrica == 'riesgo':
            df['perdio'] = (df['final_grade'] < 3.0).astype(int)
            agg = df.groupby(col_geo).agg(reprobados=('perdio','sum'), total=('perdio','count')).reset_index()
            agg['value'] = np.where(agg['total']>0, (agg['reprobados']/agg['total']), 0.0)
            agg['value'] = agg['value'].round(4)
            res = agg[[col_geo,'value']]
        else:
            return []
        
        res = res.merge(totales, on=col_geo, how='left').dropna(subset=['value'])
        res = res.rename(columns={col_geo: 'name'})
        
        print(f"[DEBUG mapa] Registros enviados al frontend: {len(res)}, muestra: {res['name'].head(3).tolist()}")
        return clean_df_for_json(res[['name','value','total_estudiantes']])
    except Exception as e:
        print(f"Error mapa-poligonos: {e}")
        return JSONResponse(status_code=400, content={"error": str(e)})

    except Exception as e:
        print(f"Error mapa-poligonos: {e}")
        return JSONResponse(status_code=400, content={"error": str(e)})

@app.get("/api/materias-list")
def get_materias_list():
    try:
        sb = get_supabase_client()
        data = sb.table('subjects').select('name').limit(100000).execute().data or []
        return sorted({r['name'] for r in data if r.get('name')})
    except Exception as e:
        print(f"Error materias-list: {e}")
        return []

@app.get("/")
def read_index():
    return FileResponse('public/index.html')

app.mount("/", StaticFiles(directory="public"), name="public")

# ARRANQUE PARA RENDER
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("api:app", host="0.0.0.0", port=port)
