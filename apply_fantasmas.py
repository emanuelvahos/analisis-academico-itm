import re

path = r'c:\Users\Admin\Documents\Proyecto-Dashboard-ITM\api.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Renombrar materias-filtro a materias-list y crear /api/fantasmas
# Buscamos el bloque de materias-filtro:
old_materias_block = """@app.get("/api/materias-filtro")
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
        return []"""

new_materias_block = """@app.get("/api/materias-list")
@cache(expire=3600)
def get_materias_list(semestre: str = "2025-2"):
    try:
        supabase = get_supabase_client()
        # Top 10 ordenado por mortalidad descendente desde SQL
        data = supabase.table('view_kpi_materias').select('*').eq('semester', semestre).order('mortalidad', desc=True).limit(10).execute().data or []
        return [{
            "name": str(row.get('asignatura', 'N/A')),
            "value": float(row.get('mortalidad', 0)),
            "total_evaluaciones": int(row.get('total_evaluaciones', 0)),
            "reprobados": int(row.get('reprobados', 0))
        } for row in data]
    except Exception as e:
        print(f"Error materias-list: {e}")
        return []

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
        return {"total_fantasmas": 0}"""

if old_materias_block in content:
    content = content.replace(old_materias_block, new_materias_block)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Éxito: api.py actualizado con /api/materias-list y /api/fantasmas.")
else:
    print("Aviso: No se encontró el bloque exacto. Asegúrate de que no haya cambios sutiles.")
