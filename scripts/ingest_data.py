import os
import pandas as pd
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# Configuración de Supabase
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
tenant_id: str = os.environ.get("TENANT_ID")
supabase: Client = create_client(url, key)

def process_excel(file_path: str):
    """
    Procesa un archivo Excel pesado en trozos para evitar desbordamiento de memoria
    y realiza inserciones masivas en Supabase.
    """
    print(f"Procesando {file_path}...")
    
    # Nota: Excel no soporta chunksize nativo como CSV, 
    # pero podemos leer hojas o usar dask si es extremo.
    # Para 50MB, pandas puede cargarlo en memoria, pero para el procesamiento
    # de 1M de registros es mejor segmentar la lógica.
    
    df = pd.read_excel(file_path)
    
    # 1. Normalización y Limpieza
    # Aquí iría la lógica para separar en las tablas diseñadas
    # Ejemplo: Extraer docentes únicos, asignaturas únicas, etc.
    
    print(f"Registros cargados: {len(df)}")
    
    # Ejemplo de inserción por lotes
    # batch_size = 1000
    # for i in range(0, len(df), batch_size):
    #     batch = df.iloc[i:i+batch_size].to_dict('records')
    #     supabase.table("tu_tabla").insert(batch).execute()

if __name__ == "__main__":
    files = [
        "Desarrollo Curricular SIGA Semestre (1).xlsx",
        "Desarrollo Curricular SIGA Semestre (2).xlsx"
    ]
    
    for f in files:
        if os.path.exists(f):
            process_excel(f)
        else:
            print(f"Archivo no encontrado: {f}")
