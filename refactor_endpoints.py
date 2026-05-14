import re

with open('api.py', 'r', encoding='utf-8') as f:
    content = f.read()

# REEMPLAZAR GET_KPIS
old_kpis = re.search(r"@app\.get\(\"/api/kpis\"\)\n@cache\(expire=3600\)\ndef get_kpis.*?except Exception as e:\n        print\(f\"Error KPIs: \{e\}\"\)\n        return JSONResponse\(status_code=400, content={\"error\": str\(e\)\}\)", content, re.DOTALL)

new_kpis = """@app.get("/api/kpis")
@cache(expire=3600)
def get_kpis(semestre: str = "2025-2"):
    try:
        sb = get_supabase_client()
        # 1. Consultar Resumen General
        resumen_data = sb.table('view_kpi_resumen').select('*').eq('semester', semestre).execute().data
        
        total_estudiantes = 0
        mortalidad_global = 0.0
        fuera_mapa = 0
        
        if resumen_data and len(resumen_data) > 0:
            total_estudiantes = resumen_data[0].get('total_estudiantes_unicos', resumen_data[0].get('total_estudiantes', 0))
            mortalidad_global = float(resumen_data[0].get('mortalidad_global', resumen_data[0].get('value', 0.0)))
            fuera_mapa = resumen_data[0].get('fuera_de_medellin_o_sin_datos', 0)

        # 2. Consultar Materia Crítica
        materias_data = sb.table('view_kpi_materias').select('*').eq('semester', semestre).order('value', desc=True).limit(1).execute().data
        
        asignatura_critica = {"nombre": "N/A", "porcentaje": 0.0}
        if materias_data and len(materias_data) > 0:
            asignatura_critica = {
                "nombre": materias_data[0].get('name', 'N/A'),
                "porcentaje": round(float(materias_data[0].get('value', 0.0) * 100), 1)
            }

        return {
            "total_estudiantes": total_estudiantes,
            "mortalidad_global": round(mortalidad_global * 100, 1) if mortalidad_global <= 1.0 else round(mortalidad_global, 1),
            "fuera_de_medellin_o_sin_datos": fuera_mapa,
            "asignatura_critica": asignatura_critica
        }
    except Exception as e:
        print(f"Error KPIs: {e}")
        return JSONResponse(status_code=400, content={"error": str(e)})"""

if old_kpis:
    content = content.replace(old_kpis.group(0), new_kpis)
else:
    print("No se encontró old_kpis")


# REEMPLAZAR MAPA POLIGONOS
old_mapa = re.search(r"@app\.get\(\"/api/mapa-poligonos\"\)\n@cache\(expire=3600\)\ndef get_mapa_poligonos.*?except Exception as e:\n        print\(f\"Error mapa-poligonos: \{e\}\"\)\n        return JSONResponse\(status_code=400, content={\"error\": str\(e\)\}\)", content, re.DOTALL)

new_mapa = """@app.get("/api/mapa-poligonos")
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
        # La vista ya debe traer 'barrio' y 'comuna'
        df['ubicacion_final'] = df.apply(unificar_ubicacion, axis=1)
        
        # --- SMART GEO-MATCHING (Alinear con GeoJSON) ---
        df[col_geo] = df['ubicacion_final'].apply(lambda x: emparejar_con_geojson(x, tipo=nivel_geo))
        
        # Filtrar desconocidos para el reporte final del mapa
        df = df[df[col_geo] != 'Desconocido']
        
        # Convertir a numérico por si acaso
        for c in ['total_evaluaciones', 'total_estudiantes_unicos', 'reprobados']:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
        
        # Agrupar por la geografía homologada (ya que varios barrios BD pueden mapear al mismo GeoJSON)
        agg_cols = {
            'total_evaluaciones': 'sum',
            'total_estudiantes_unicos': 'sum',
            'reprobados': 'sum'
        }
        agg_cols = {k: v for k, v in agg_cols.items() if k in df.columns}
        
        agg = df.groupby(col_geo).agg(agg_cols).reset_index()
        
        if metrica == 'poblacion':
            agg['value'] = agg['total_estudiantes_unicos']
        elif metrica == 'aprobacion':
            agg['aprobados'] = agg['total_evaluaciones'] - agg['reprobados']
            agg['value'] = np.where(agg['total_evaluaciones'] > 0, agg['aprobados'] / agg['total_evaluaciones'], 0.0)
            agg['value'] = agg['value'].round(4)
        elif metrica == 'riesgo':
            agg['value'] = np.where(agg['total_evaluaciones'] > 0, agg['reprobados'] / agg['total_evaluaciones'], 0.0)
            agg['value'] = agg['value'].round(4)
        else:
            return []
        
        agg = agg.rename(columns={col_geo: 'name', 'total_estudiantes_unicos': 'total_estudiantes'})
        res = agg[['name', 'value', 'total_estudiantes']].dropna(subset=['value'])
        
        print(f"[DEBUG mapa] Registros enviados al frontend: {len(res)}, muestra: {res['name'].head(3).tolist()}")
        return clean_df_for_json(res)
    except Exception as e:
        print(f"Error mapa-poligonos: {e}")
        return JSONResponse(status_code=400, content={"error": str(e)})"""

if old_mapa:
    content = content.replace(old_mapa.group(0), new_mapa)
    # Limpiar un posible bloque extra repetido
    content = content.replace('    except Exception as e:\n        print(f"Error mapa-poligonos: {e}")\n        return JSONResponse(status_code=400, content={"error": str(e)})\n\n    except Exception as e:\n        print(f"Error mapa-poligonos: {e}")\n        return JSONResponse(status_code=400, content={"error": str(e)})', 
                             '    except Exception as e:\n        print(f"Error mapa-poligonos: {e}")\n        return JSONResponse(status_code=400, content={"error": str(e)})')

else:
    print("No se encontró old_mapa")

with open('api.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("api.py endpoints updated")
