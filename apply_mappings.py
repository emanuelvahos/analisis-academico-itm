import re
import os

path = r'c:\Users\Admin\Documents\Proyecto-Dashboard-ITM\api.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

new_endpoints_code = """@app.get("/api/teachers")
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

@app.get("/api/materias-filtro")
@cache(expire=3600)
def get_materias_filtro(semestre: str = "2025-2"):
    try:
        supabase = get_supabase_client()
        # Ordenar por mortalidad descendente y limitar a 10 desde SQL
        data = supabase.table('view_kpi_materias').select('*').eq('semester', semestre).order('mortalidad', desc=True).limit(10).execute().data or []
        return [{
            "name": str(row.get('asignatura', 'N/A')),
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
        return []"""

start_marker = '@app.get("/api/teachers")'
end_marker = '@app.get("/api/rutas-transporte")'

start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx != -1 and end_idx != -1:
    new_content = content[:start_idx] + new_endpoints_code + "\n\n" + content[end_idx:]
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("Endpoints refactorizados con formateo y ordenamiento estricto aplicados.")
else:
    print(f"No se pudo encontrar el rango de reemplazo. start_idx: {start_idx}, end_idx: {end_idx}")
