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
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from fastapi_cache.decorator import cache
from dotenv import load_dotenv
import unicodedata
from supabase import create_client, Client
import re
import time
import asyncio
from functools import wraps
import json
import difflib

# --- CARGAR DICCIONARIOS OFICIALES DESDE GEOJSON ---
try:
    with open('medellin.geojson', 'r', encoding='utf-8') as f:
        geo_data = json.load(f)
    
    # Extraer nombres únicos respetando la capitalización oficial del GeoJSON
    GEO_COMUNAS = {f.get('properties', {}).get('nombre_comuna', '').upper(): f.get('properties', {}).get('nombre_comuna', '') for f in geo_data.get('features', []) if f.get('properties', {}).get('nombre_comuna')}
    GEO_BARRIOS = {f.get('properties', {}).get('nombre_barrio', '').upper(): f.get('properties', {}).get('nombre_barrio', '') for f in geo_data.get('features', []) if f.get('properties', {}).get('nombre_barrio')}
    print(f"Geo-Matching cargado: {len(GEO_COMUNAS)} comunas y {len(GEO_BARRIOS)} barrios detectados.")
except Exception as e:
    print(f"Advertencia: No se pudo cargar medellin.geojson para el mapeo estricto: {e}")
    GEO_COMUNAS = {}
    GEO_BARRIOS = {}

# Cache initialized at startup

def clean_geo(text):
    if not isinstance(text, str): return ""
    # Quitar tildes
    text = ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')
    text = text.lower()
    # Quitar caracteres especiales y palabras basura
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    text = re.sub(r'\b(barrio|comuna|vereda|corregimiento)\b', '', text)
    return ' '.join(text.split())

def unificar_ubicacion(row):
    barrio = str(row.get('barrio', ''))
    comuna = str(row.get('comuna', ''))
    
    if 'seleccionar' in barrio.lower() or 'desconocida' in comuna.lower():
        return 'Desconocido'
        
    barrio_cln = clean_geo(barrio)
    comuna_cln = clean_geo(comuna)
    texto_unido = f"{barrio_cln} {comuna_cln}"
    
    # 1. Si detecta un municipio externo, unifica bajo ese nombre
    for mun in MUNICIPIOS_EXTERNOS:
        if mun in texto_unido:
            return mun.title() # Ej: 'Bello', 'Itagui'
            
    # 2. Si no es municipio externo, devuelve el barrio limpio para el cruce en Medellín
    if barrio_cln:
        return barrio_cln.title()
    return 'Desconocido'

def clean_geo_string(text: str) -> str:
    return clean_geo(text)

def emparejar_con_geojson(valor, tipo='comuna'):
    """Emparejador inteligente para alinear BD con GeoJSON usando Búsqueda Exacta o Difusa (Fuzzy)"""
    if not valor or pd.isna(valor) or str(valor).lower() in ['seleccionar', 'desconocido', '', 'nan', 'none']: 
        return 'Desconocido'
    
    valor_upper = str(valor).upper().strip()
    mapa_oficial = GEO_COMUNAS if tipo == 'comuna' else GEO_BARRIOS
    
    # 1. Búsqueda Exacta (ignorando mayúsculas)
    if valor_upper in mapa_oficial:
        return mapa_oficial[valor_upper] # Devuelve el nombre con la ortografía perfecta del GeoJSON
        
    # 2. Búsqueda Difusa (Fuzzy Matching) para corregir errores tipográficos (ej. "Moscu No.1")
    matches = difflib.get_close_matches(valor_upper, mapa_oficial.keys(), n=1, cutoff=0.7)
    if matches:
        return mapa_oficial[matches[0]]
        
    return str(valor).title() # Fallback si no hay match razonable

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

MUNICIPIOS_EXTERNOS = ['bello', 'itagui', 'envigado', 'copacabana', 'sabaneta', 'caldas', 'la estrella', 'girardota', 'barbosa', 'guarne', 'rionegro', 'el penol', 'san pedro', 'bogota', 'duitama', 'marinilla', 'gomez plata', 'san jeronimo', 'caucasia', 'la ceja', 'quibdo', 'pasto', 'retiro', 'yarumal', 'cali', 'frontino']

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



def calcular_mortalidad_sql(df, group_col, extra_cols=None):
    """Replica la lógica SQL: COUNT(DISTINCT student) y SUM(final_grade < 3.0)"""
    df = df.copy()
    # Normalizar notas
    df['final_grade'] = df['final_grade'].astype(str).str.replace(',', '.')
    df['final_grade'] = pd.to_numeric(df['final_grade'], errors='coerce')
    df = df.dropna(subset=['final_grade'])
    
    agrupadores = [group_col] if extra_cols is None else [group_col] + extra_cols
    
    # Agrupación estricta
    kpi_df = df.groupby(agrupadores).agg(
        total_evaluaciones=('final_grade', 'count'),
        total_estudiantes_unicos=('student_id', 'nunique'),
        reprobados=('final_grade', lambda x: (x < 3.0).sum())
    ).reset_index()
    
    # Tasa pura (0.0 a 1.0)
    kpi_df['value'] = (kpi_df['reprobados'] / kpi_df['total_evaluaciones']).round(4).fillna(0)
    kpi_df = kpi_df.rename(columns={group_col: 'name'})
    
    return kpi_df

# --- ENDPOINTS ---

@app.get("/api/kpis")
@cache(expire=3600)
def get_kpis(semestre: str = "2025-2"):
    try:
        sb = get_supabase_client()
        
        # 1. Consultar la vista maestra
        res_resumen = sb.table('view_kpi_resumen').select('*').eq('semester', semestre).execute()
        data_resumen = res_resumen.data

        if not data_resumen:
            return {
                "total_estudiantes": 0, 
                "mortalidad_global": 0.0, 
                "fuera_de_medellin_o_sin_datos": 0, 
                "asignatura_critica": {"nombre": "N/A", "porcentaje": 0.0}
            }

        # 2. Consultar la vista de materias (CORREGIDO: ordenando por 'mortalidad', no por 'value')
        res_mat = sb.table('view_kpi_materias').select('*').eq('semester', semestre).order('mortalidad', desc=True).limit(1).execute()
        
        critica_nombre = "N/A"
        critica_pct = 0.0
        if res_mat.data:
            critica_nombre = res_mat.data[0]['asignatura']
            critica_pct = float(res_mat.data[0]['mortalidad'])

        return {
            "total_estudiantes": data_resumen[0]['total_estudiantes'],
            "mortalidad_global": float(data_resumen[0]['mortalidad_global']),
            "fuera_de_medellin_o_sin_datos": 0, 
            "asignatura_critica": {
                "nombre": critica_nombre,
                "porcentaje": critica_pct
            }
        }
    except Exception as e:
        print(f"Error KPIs: {e}")
        return JSONResponse(status_code=400, content={"error": str(e)})

@app.get("/api/kpi-fantasmas")
@cache(expire=3600)
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
        
        # 1. Normalizar notas y eliminar nulos
        df['final_grade'] = df['final_grade'].astype(str).str.replace(',', '.')
        df['final_grade'] = pd.to_numeric(df['final_grade'], errors='coerce')
        df = df.dropna(subset=['final_grade'])
        
        # Aplanar semestre para agrupaciones
        df['semester'] = df['class_groups'].apply(lambda x: x.get('semester') if isinstance(x, dict) else None)

        if semestre:
            # --- LÓGICA CORE (Semestre Específico) ---
            # Agrupar por estudiante y sacar su nota máxima
            max_grades = df.groupby('student_id')['final_grade'].max().reset_index()
            # Filtrar a los que su nota máxima es estrictamente 0.0
            fantasmas_ids = max_grades[max_grades['final_grade'] == 0.0]['student_id']
            
            # Registros de esos estudiantes
            fantasmas_df = df[df['student_id'].isin(fantasmas_ids)]
            
            total_evaluaciones = len(fantasmas_df)
            total_estudiantes_unicos = fantasmas_df['student_id'].nunique()
            total_estudiantes_activos = df['student_id'].nunique()
            
            return {
                "name": "Estudiantes Fantasma",
                "value": 1.0,  # Mortalidad 100%
                "total_evaluaciones": int(total_evaluaciones),
                "total_estudiantes_unicos": int(total_estudiantes_unicos),
                "reprobados": int(total_evaluaciones),
                "porcentaje_del_total": round((total_estudiantes_unicos / total_estudiantes_activos) * 100, 2) if total_estudiantes_activos > 0 else 0,
                "semestre": semestre
            }
        else:
            # --- EVOLUCIÓN HISTÓRICA ---
            evolucion = []
            for sem_val, group in df.groupby('semester'):
                # Nota máxima por estudiante en ESTE semestre
                max_sem = group.groupby('student_id')['final_grade'].max().reset_index()
                f_ids = max_sem[max_sem['final_grade'] == 0.0]['student_id']
                
                f_df = group[group['student_id'].isin(f_ids)]
                
                total_sem = group['student_id'].nunique()
                fantasmas_sem = f_df['student_id'].nunique()
                
                evolucion.append({
                    "semestre": str(sem_val),
                    "estudiantes_fantasma": int(fantasmas_sem),
                    "total_estudiantes": int(total_sem),
                    "porcentaje": round((fantasmas_sem / total_sem) * 100, 1) if total_sem > 0 else 0.0
                })
            return sorted(evolucion, key=lambda x: x['semestre'], reverse=True)

    except Exception as e:
        print(f"Error en KPI Fantasmas: {e}")
        return JSONResponse(
            status_code=400, 
            content={"error": str(e), "estudiantes_fantasma": 0, "total_estudiantes": 0, "porcentaje": 0}
        )

@app.on_event("startup")
async def startup():
    FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache")

@app.get("/api/heatmap")
@cache(expire=3600)
def get_heatmap(semestre: str = "2025-2"):
    try:
        supabase = get_supabase_client()
        data = supabase.table('view_kpi_heatmap').select('*').eq('semester', semestre).execute().data or []
        return [{
            "dia_nombre": row.get('dia', ''),
            "franja_horaria": row.get('hora', ''),
            "mortalidad": float(row.get('total_estudiantes', 0))
        } for row in data]
    except Exception as e:
        print(f"Error heatmap: {e}")
        return JSONResponse(status_code=400, content={"error": str(e)})

@app.get("/api/teachers")
@cache(expire=3600)
def get_teachers(semestre: str = "2025-2"):
    try:
        supabase = get_supabase_client()
        data = supabase.table('view_top_docentes').select('*').eq('semester', semestre).execute().data or []
        return [{
            "name": str(row.get('teacher_name', 'N/A')),
            "value": float(row.get('mortalidad', 0)),
            "total_evaluaciones": int(row.get('total_evaluaciones', 0)),
            "reprobados": int(row.get('reprobados', 0))
        } for row in data]
    except Exception as e:
        print(f"Error teachers: {e}")
        return []

@app.get("/api/adaptacion")
@cache(expire=3600)
def get_adaptacion(semestre: str = "2025-2"):
    try:
        supabase = get_supabase_client()
        data = supabase.table('view_kpi_adaptacion').select('*').eq('semester', semestre).execute().data or []
        return [{
            "name": str(row.get('estado', 'N/A')),
            "value": float(row.get('mortalidad', 0)),
            "total_evaluaciones": int(row.get('total_evaluaciones', 0)),
            "reprobados": int(row.get('reprobados', 0))
        } for row in data]
    except Exception as e:
        print(f"Error adaptacion: {e}")
        return []

@app.get("/api/brecha-ciencias")
@cache(expire=3600)
def get_brecha_ciencias(semestre: str = "2025-2"):
    try:
        supabase = get_supabase_client()
        data = supabase.table('view_kpi_genero').select('*').eq('semester', semestre).execute().data or []
        return [{
            "name": str(row.get('sexo', 'N/A')),
            "value": float(row.get('mortalidad', 0)),
            "total_evaluaciones": int(row.get('total_evaluaciones', 0)),
            "reprobados": int(row.get('reprobados', 0))
        } for row in data]
    except Exception as e:
        print(f"Error brecha: {e}")
        return []

# 1. EL ENDPOINT QUE BUSCA JAVASCRIPT (Soluciona el 404)
@app.get("/api/materias-list") 
@cache(expire=3600)
def get_materias_list(semestre: str = "2025-2"):
    try:
        sb = get_supabase_client()
        res = sb.table('view_kpi_materias').select('*').eq('semester', semestre).order('mortalidad', desc=True).limit(10).execute()
        return [{"name": str(row['asignatura']), "value": float(row['mortalidad'])} for row in res.data]
    except Exception as e:
        print(f"Error materias: {e}")
        return [] # Array vacío salva a ECharts de colapsar

# 2. EL ENDPOINT DE JORNADA CORREGIDO (Soluciona el error 'get')
@app.get("/api/jornada")
@cache(expire=3600)
def get_jornada(semestre: str = "2025-2"):
    try:
        sb = get_supabase_client()
        res = sb.table('view_kpi_jornada').select('*').eq('semester', semestre).execute()
        return [{"name": str(row['jornada']), "value": float(row['mortalidad'])} for row in res.data if row['jornada']]
    except Exception as e:
        print(f"Error jornada: {e}")
        return []

# 3. EL NUEVO ENDPOINT DE FANTASMAS
@app.get("/api/fantasmas")
@cache(expire=3600)
def get_fantasmas(semestre: str = "2025-2"):
    try:
        sb = get_supabase_client()
        res = sb.table('view_kpi_estudiantes_fantasmas').select('*').eq('semester', semestre).execute()
        total = res.data[0]['total_fantasmas'] if res.data and len(res.data) > 0 else 0
        return {"total_fantasmas": total}
    except Exception as e:
        print(f"Error fantasmas: {e}")
        return {"total_fantasmas": 0}
@app.get("/api/fantasmas")
@cache(expire=3600)
def get_fantasmas(semestre: str = "2025-2"):
    try:
        supabase = get_supabase_client()
        data = supabase.table('view_kpi_estudiantes_fantasmas').select('*').eq('semester', semestre).execute().data or []
        
        # Extraer el valor dependiendo de cómo se llame exactamente la columna en la vista
        # Intentamos 'estudiantes_fantasma' o 'total_fantasmas'
        total = 0
        if data:
            total = data[0].get('estudiantes_fantasma', data[0].get('total_fantasmas', 0))
            
        return {"total_fantasmas": int(total)}
    except Exception as e:
        print(f"Error fantasmas: {e}")
        return {"total_fantasmas": 0}

@app.get("/api/sedes")
@cache(expire=3600)
def get_sedes(semestre: str = "2025-2"):
    try:
        supabase = get_supabase_client()
        data = supabase.table('view_kpi_sedes').select('*').eq('semester', semestre).execute().data or []
        result = [{
            "name": str(row.get('sede', 'N/A')),
            "value": float(row.get('mortalidad', 0)),
            "total_evaluaciones": int(row.get('total_evaluaciones', 0)),
            "reprobados": int(row.get('reprobados', 0))
        } for row in data]
        # Ordenar descendente
        return sorted(result, key=lambda x: x['value'], reverse=True)
    except Exception as e:
        print(f"Error sedes: {e}")
        return []

@app.get("/api/jornada")
@cache(expire=3600)
def get_jornada(semestre: str = "2025-2"):
    try:
        supabase = get_supabase_client()
        data = supabase.table('view_kpi_jornada').select('*').eq('semester', semestre).execute().data or []
        return [{
            "name": str(row.get('jornada', 'N/A')),
            "value": float(row.get('mortalidad', 0)),
            "total_evaluaciones": int(row.get('total_evaluaciones', 0)),
            "reprobados": int(row.get('reprobados', 0))
        } for row in data]
    except Exception as e:
        print(f"Error jornada: {e}")
        return []

@app.get("/api/rutas-transporte")
@cache(expire=3600)
def get_rutas_transporte(semestre: str = "2025-2"):
    try:
        sb = get_supabase_client()
        # Obtener estudiantes activos en el semestre
        data_perf = supabase_fetch_all('academic_performance', 'student_id, class_groups!inner(semester)', {'class_groups.semester': semestre})
        if not data_perf: return []
        student_ids = list({r['student_id'] for r in data_perf})
        
        # Traer datos geográficos de todos los estudiantes y filtrar en Python
        data_s = supabase_fetch_all('students', 'id, barrio, comuna, campus_id')
        data_c = supabase_fetch_all('campuses', 'id, name')
        
        df_s = pd.DataFrame(data_s).rename(columns={'id': 'student_id'})
        df_c = pd.DataFrame(data_c).rename(columns={'id': 'campus_id', 'name': 'sede_name'})
        
        # Filtrar solo estudiantes del semestre
        df_s = df_s[df_s['student_id'].isin(student_ids)].copy()
        df_s = df_s.merge(df_c, on='campus_id', how='left')
        
        # Normalizar sede_name
        df_s['sede_name'] = df_s['sede_name'].fillna('').astype(str).str.strip()
        
        # Aplicar unificación geográfica
        df_s['ubicacion_final'] = df_s.apply(unificar_ubicacion, axis=1)
        
        rutas = df_s.groupby(['ubicacion_final','sede_name']).size().reset_index(name='cantidad')
        rutas = rutas[rutas['cantidad'] > 0]
        
        rutas['barrio_norm'] = rutas['ubicacion_final'].apply(clean_geo)
        rutas['destino_norm'] = rutas['sede_name'].str.lower().str.strip().apply(clean_geo)
        
        # Debug: mostrar las claves disponibles y qué barrios hay
        print(f"[DEBUG rutas] Barrios únicos (muestra): {rutas['barrio_norm'].unique()[:5].tolist()}")
        print(f"[DEBUG rutas] Destinos únicos: {rutas['destino_norm'].unique().tolist()}")
        print(f"[DEBUG rutas] Claves COORDS_SAFE (muestra): {list(COORDS_SAFE.keys())[:5]}")
        
        rutas['origen_coords'] = rutas['barrio_norm'].map(COORDS_SAFE)
        rutas['destino_coords'] = rutas['destino_norm'].map(COORDS_SAFE)
        
        df_limpio = rutas.dropna(subset=['origen_coords','destino_coords'])
        print(f"[DEBUG rutas] Total rutas con coords: {len(df_limpio)} de {len(rutas)} posibles")
        
        result = []
        for _, row in df_limpio.iterrows():
            result.append({
                "coords": [row['origen_coords'], row['destino_coords']],
                "value": int(row['cantidad']),
        "origen": str(row['ubicacion_final']),
        "destino": str(row['sede_name']).title()
            })
        print(f"DEBUG: Rutas mapeadas: {len(result)}")
        return result
    except Exception as e:
        print(f"Error rutas: {e}")
        return JSONResponse(status_code=400, content={"error": str(e)})



@app.get("/api/mapa-poligonos")
@cache(expire=3600)
def get_mapa_poligonos(semestre: str = "2025-2", metrica: str = 'poblacion', nivel_geo: str = 'barrio'):
    try:
        sb = get_supabase_client()
        col_geo = 'barrio' if nivel_geo == 'barrio' else 'comuna'
        
        # 1. Consultar vista optimizada
        data = sb.table('view_kpi_mapa').select('*').eq('semester', semestre).execute().data or []
        if not data: return []
        
        df = pd.DataFrame(data)
        
        # 2. Aplicar unificación geográfica (barrio, comuna)
        df['ubicacion_final'] = df.apply(unificar_ubicacion, axis=1)
        
        # --- SMART GEO-MATCHING (Alinear con GeoJSON) ---
        df[col_geo] = df['ubicacion_final'].apply(lambda x: emparejar_con_geojson(x, tipo=nivel_geo))
        
        # Filtrar desconocidos para el reporte final del mapa
        df = df[df[col_geo] != 'Desconocido']
        
        # Convertir a numérico (CORREGIDO: 'total_estudiantes' en lugar de 'total_estudiantes_unicos')
        for c in ['total_evaluaciones', 'total_estudiantes', 'reprobados']:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
        
        # Agrupar por la geografía homologada
        agg_cols = {
            'total_evaluaciones': 'sum',
            'total_estudiantes': 'sum',
            'reprobados': 'sum'
        }
        agg_cols = {k: v for k, v in agg_cols.items() if k in df.columns}
        
        agg = df.groupby(col_geo).agg(agg_cols).reset_index()
        
        if metrica == 'poblacion':
            agg['value'] = agg['total_estudiantes']
        elif metrica == 'aprobacion':
            agg['aprobados'] = agg['total_evaluaciones'] - agg['reprobados']
            agg['value'] = np.where(agg['total_evaluaciones'] > 0, agg['aprobados'] / agg['total_evaluaciones'], 0.0)
            agg['value'] = agg['value'].round(4)
        elif metrica == 'riesgo':
            agg['value'] = np.where(agg['total_evaluaciones'] > 0, agg['reprobados'] / agg['total_evaluaciones'], 0.0)
            agg['value'] = agg['value'].round(4)
        else:
            return []
        
        # Renombrar solo el nivel geográfico, ya que total_estudiantes ya tiene el nombre correcto
        agg = agg.rename(columns={col_geo: 'name'})
        res = agg[['name', 'value', 'total_estudiantes']].dropna(subset=['value'])
        
        print(f"[DEBUG mapa] Registros enviados al frontend: {len(res)}, muestra: {res['name'].head(3).tolist()}")
        return clean_df_for_json(res)
    except Exception as e:
        print(f"Error mapa-poligonos: {e}")
        return JSONResponse(status_code=400, content={"error": str(e)})

# --- CONFIGURACIÓN DE ARCHIVOS ESTÁTICOS PARA PRODUCCIÓN ---
current_dir = os.path.dirname(os.path.realpath(__file__))

# 1. Montar archivos de lógica y estilos en /static
app.mount("/static", StaticFiles(directory=os.path.join(current_dir, "static")), name="static")

# 2. Montar carpeta public para assets y geojson (acceder como /assets/... o /medellin.geojson)
app.mount("/public", StaticFiles(directory=os.path.join(current_dir, "public")), name="public")

@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(current_dir, 'index.html'))

# Fallback para servir archivos desde public en la raíz (ej. /medellin.geojson)
app.mount("/", StaticFiles(directory=os.path.join(current_dir, "public")), name="root_public")

# ARRANQUE PARA RENDER
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("api:app", host="0.0.0.0", port=port)
