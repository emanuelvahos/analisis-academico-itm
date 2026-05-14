import re
import os

path = r'c:\Users\Admin\Documents\Proyecto-Dashboard-ITM\api.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Definir los nuevos endpoints
new_endpoints_code = """@app.get("/api/heatmap")
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
            "name": row.get('teacher_name', 'N/A'),
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
            "name": row.get('estado', 'N/A'),
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
            "name": row.get('sexo', 'N/A'),
            "value": float(row.get('mortalidad', 0)),
            "total_evaluaciones": int(row.get('total_evaluaciones', 0)),
            "reprobados": int(row.get('reprobados', 0))
        } for row in data]
    except Exception as e:
        print(f"Error brecha: {e}")
        return []

@app.get("/api/materias-filtro")
@cache(expire=3600)
def get_materias_filtro(semestre: str = "2025-2"):
    try:
        supabase = get_supabase_client()
        data = supabase.table('view_kpi_materias').select('*').eq('semester', semestre).execute().data or []
        return [{
            "name": row.get('asignatura', 'N/A'),
            "value": float(row.get('mortalidad', 0)),
            "total_evaluaciones": int(row.get('total_evaluaciones', 0)),
            "reprobados": int(row.get('reprobados', 0))
        } for row in data]
    except Exception as e:
        print(f"Error materias: {e}")
        return []

@app.get("/api/sedes")
@cache(expire=3600)
def get_sedes(semestre: str = "2025-2"):
    try:
        supabase = get_supabase_client()
        data = supabase.table('view_kpi_sedes').select('*').eq('semester', semestre).execute().data or []
        return [{
            "name": row.get('sede', 'N/A'),
            "value": float(row.get('mortalidad', 0)),
            "total_evaluaciones": int(row.get('total_evaluaciones', 0)),
            "reprobados": int(row.get('reprobados', 0))
        } for row in data]
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
            "name": row.get('jornada', 'N/A'),
            "value": float(row.get('mortalidad', 0)),
            "total_evaluaciones": int(row.get('total_evaluaciones', 0)),
            "reprobados": int(row.get('reprobados', 0))
        } for row in data]
    except Exception as e:
        print(f"Error jornada: {e}")
        return []"""

# Buscar el bloque que empieza en @app.get("/api/heatmap") y termina antes de @app.get("/api/rutas-transporte")
# Usaremos un regex multilínea
pattern = r'@app\.get\("/api/heatmap"\).*?def get_jornada\(semestre: str = "2025-2"\):.*?return \[\]'
# Pero la implementación actual puede variar ligeramente. 
# Buscaremos el inicio y el final conocidos.

start_marker = '@app.get("/api/heatmap")'
end_marker = '@app.get("/api/rutas-transporte")'

start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx != -1 and end_idx != -1:
    new_content = content[:start_idx] + new_endpoints_code + "\n\n" + content[end_idx:]
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("Endpoints refactorizados aplicados exitosamente.")
else:
    print(f"No se pudo encontrar el rango de reemplazo. start_idx: {start_idx}, end_idx: {end_idx}")
