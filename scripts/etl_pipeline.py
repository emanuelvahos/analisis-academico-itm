import os
import logging
import pandas as pd
from openpyxl import load_workbook
from supabase import create_client, Client
from dotenv import load_dotenv

# 1. Configuración de Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Cargar variables de entorno
load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
TENANT_ID = os.environ.get("TENANT_ID")

if not SUPABASE_URL or not SUPABASE_KEY:
    logger.error("Faltan variables de entorno SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY.")
    exit(1)

# Inicializar cliente de Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def clean_column_names(columns: list) -> list:
    """Convierte los nombres de las columnas a snake_case."""
    return (
        pd.Series(columns)
        .astype(str)
        .str.strip()
        .str.lower()
        .str.replace(' ', '_')
        .str.replace(r'[^\w\s]', '', regex=True)
        .tolist()
    )


def format_time(row) -> str:
    """Formatea la hora inicial y minutos a HH:MM."""
    try:
        # Ajusta los nombres 'hora_inicial' y 'minutos' según queden tras el snake_case
        h = row.get('hora_inicial')
        m = row.get('minutos')
        
        if pd.isna(h) or pd.isna(m):
            return None
            
        return f"{int(h):02d}:{int(m):02d}"
    except (ValueError, TypeError):
        return None


def clean_chunk(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica las reglas de limpieza y transformación al chunk."""
    
    # 2. Rellenar valores nulos en notas parciales con 0
    # Buscamos columnas que puedan contener notas parciales
    partial_grade_cols = [col for col in df.columns if 'nota' in col or 'parcial' in col]
    for col in partial_grade_cols:
        # Convertimos a numérico por si vienen como texto, rellenamos con 0
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
    # 3. Formatear la hora
    if 'hora_inicial' in df.columns and 'minutos' in df.columns:
        df['formatted_time'] = df.apply(format_time, axis=1)
        
    # Inyectar el tenant_id a todos los registros
    if TENANT_ID:
        df['tenant_id'] = TENANT_ID
        
    return df


def upsert_batch(table_name: str, records: list, conflict_columns: str):
    """Ejecuta un batch upsert a Supabase."""
    if not records:
        return
    try:
        # El método .upsert maneja inserción o actualización basada en on_conflict
        response = supabase.table(table_name).upsert(
            records, 
            on_conflict=conflict_columns
        ).execute()
        
    except Exception as e:
        logger.error(f"Error realizando upsert en tabla '{table_name}': {e}")


def process_and_upload(df_chunk: pd.DataFrame):
    """
    Separa el chunk en las distintas entidades (Estudiantes, Asignaturas, etc.)
    y las sube a Supabase de forma relacional.
    """
    df = clean_chunk(df_chunk)
    
    # NOTA: Los nombres de columnas exactos dependerán de tu Excel original.
    # A continuación se ilustra la lógica utilizando nombres inferidos.
    
    # -- 1. SUBIR ESTUDIANTES --
    # Supongamos que la columna del documento se llama 'documento_estudiante'
    if 'documento_estudiante' in df.columns:
        students_df = df[['documento_estudiante', 'nombre_estudiante', 'email', 'tenant_id']].copy()
        students_df = students_df.rename(columns={
            'documento_estudiante': 'external_id',
            'nombre_estudiante': 'full_name'
        })
        # Limpiar duplicados dentro de este mismo chunk
        students_df = students_df.drop_duplicates(subset=['external_id'])
        
        # Eliminar filas donde no haya external_id válido
        students_df = students_df.dropna(subset=['external_id'])
        
        # Upsert a Supabase (asumiendo constraint unique_tenant_external_id)
        upsert_batch('students', students_df.to_dict(orient='records'), 'tenant_id, external_id')

    # -- 2. SUBIR CLASES/GRUPOS --
    if 'id_clase' in df.columns:
        classes_df = df[['id_clase', 'nombre_asignatura', 'formatted_time', 'tenant_id']].copy()
        classes_df = classes_df.rename(columns={'id_clase': 'group_code'})
        classes_df = classes_df.drop_duplicates(subset=['group_code'])
        classes_df = classes_df.dropna(subset=['group_code'])
        
        # Nota: aquí habría que asociar el subject_id (asignatura) buscándolo o insertándolo antes
        # upsert_batch('class_groups', classes_df.to_dict('records'), 'tenant_id, group_code')

    # -- 3. SUBIR NOTAS (Tabla de relación) --
    # Requiere cruzar el ID generado del estudiante y el ID del grupo de clase, 
    # o usar los external_id si tu tabla lo permite
    pass


def run_etl_pipeline(file_path: str, chunk_size: int = 5000):
    """
    Lee un archivo XLSX masivo fila por fila para simular un chunksize 
    extremadamente eficiente en memoria (Pandas read_excel no soporta chunksize).
    """
    logger.info(f"Iniciando pipeline ETL para: {file_path}")
    
    if not os.path.exists(file_path):
        logger.error(f"El archivo {file_path} no existe.")
        return

    try:
        # Se utiliza openpyxl en read_only=True para streamear el archivo sin cargarlo en RAM
        wb = load_workbook(filename=file_path, read_only=True, data_only=True)
        ws = wb.active
        
        # Crear un iterador sobre las filas
        row_iterator = ws.iter_rows(values_only=True)
        
        # Obtener y estandarizar la cabecera
        raw_headers = next(row_iterator)
        headers = clean_column_names(raw_headers)
        
        chunk = []
        chunk_number = 1
        total_rows = 0
        
        logger.info(f"Cabeceras extraídas: {headers[:5]}... (total: {len(headers)})")
        
        for row in row_iterator:
            chunk.append(row)
            
            # Cuando llegamos al tamaño del chunk, lo procesamos
            if len(chunk) == chunk_size:
                df_chunk = pd.DataFrame(chunk, columns=headers)
                
                logger.info(f"Procesando Chunk #{chunk_number} ({chunk_size} filas)...")
                process_and_upload(df_chunk)
                
                total_rows += chunk_size
                chunk = []
                chunk_number += 1
                
        # Procesar el bloque remanente
        if chunk:
            df_chunk = pd.DataFrame(chunk, columns=headers)
            logger.info(f"Procesando Chunk #{chunk_number} FINAL ({len(chunk)} filas)...")
            process_and_upload(df_chunk)
            total_rows += len(chunk)
            
        logger.info(f"Pipeline ETL completado exitosamente. Total registros procesados: {total_rows}")
        
    except Exception as e:
        logger.error(f"Error crítico durante la ejecución del pipeline: {e}", exc_info=True)


if __name__ == "__main__":
    # Archivo objetivo
    EXCEL_FILE = "Desarrollo Curricular SIGA Semestre (1).xlsx"
    
    # Se ajusta el tamaño del chunk. 5000 es un buen equilibrio entre uso de RAM y 
    # velocidad de peticiones a la API de Supabase.
    run_etl_pipeline(EXCEL_FILE, chunk_size=5000)
