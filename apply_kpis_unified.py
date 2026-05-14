import re

path = r'c:\Users\Admin\Documents\Proyecto-Dashboard-ITM\api.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Buscamos el inicio de get_kpis
start_kpis = content.find('@app.get("/api/kpis")')
# Buscamos el final de la zona a reemplazar, que sería el endpoint de heatmap
end_fantasmas = content.find('@app.get("/api/heatmap")')

new_kpis_block = """@app.get("/api/kpis")
@cache(expire=3600)
def get_kpis(semestre: str = "2025-2"):
    try:
        sb = get_supabase_client()
        
        # 1. Consultar la vista maestra de resumen
        res_resumen = sb.table('view_kpi_resumen').select('*').eq('semester', semestre).execute()
        data_resumen = res_resumen.data

        if not data_resumen:
            return {
                "total_estudiantes": 0, 
                "mortalidad_global": 0.0, 
                "fuera_de_medellin_o_sin_datos": 0, 
                "asignatura_critica": {"nombre": "N/A", "porcentaje": 0.0},
                "total_fantasmas": 0
            }

        # 2. Consultar la vista de materias (ordenando por 'mortalidad')
        res_mat = sb.table('view_kpi_materias').select('*').eq('semester', semestre).order('mortalidad', desc=True).limit(1).execute()
        critica_nombre = "N/A"
        critica_pct = 0.0
        if res_mat.data:
            critica_nombre = str(res_mat.data[0]['asignatura'])
            critica_pct = float(res_mat.data[0]['mortalidad'])

        # 3. Consultar la vista de estudiantes fantasmas
        res_fantasma = sb.table('view_kpi_estudiantes_fantasmas').select('*').eq('semester', semestre).execute()
        total_fantasmas = 0
        if res_fantasma.data:
            total_fantasmas = int(res_fantasma.data[0].get('total_fantasmas', res_fantasma.data[0].get('estudiantes_fantasma', 0)))

        return {
            "total_estudiantes": int(data_resumen[0]['total_estudiantes']),
            "mortalidad_global": float(data_resumen[0]['mortalidad_global']),
            "fuera_de_medellin_o_sin_datos": 0, 
            "asignatura_critica": {
                "nombre": critica_nombre,
                "porcentaje": critica_pct
            },
            "total_fantasmas": total_fantasmas
        }
    except Exception as e:
        print(f"Error KPIs: {e}")
        return JSONResponse(status_code=400, content={"error": str(e)})

@app.on_event("startup")
async def startup():
    FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache")

"""

if start_kpis != -1 and end_fantasmas != -1:
    content = content[:start_kpis] + new_kpis_block + content[end_fantasmas:]
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Éxito: get_kpis unificado y kpi-fantasmas viejo eliminado.")
else:
    print("Aviso: No se encontró el rango de reemplazo para get_kpis.")
