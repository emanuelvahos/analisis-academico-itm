import os
import logging
import pandas as pd
from openpyxl import load_workbook
from supabase import create_client, Client
from dotenv import load_dotenv

# 1. Configuración
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
TENANT_ID = os.environ.get("TENANT_ID")

if not SUPABASE_URL or not SUPABASE_KEY:
    logger.error("Faltan variables de entorno.")
    exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def clean_column_names(columns: list) -> list:
    return pd.Series(columns).astype(str).str.strip().str.lower().str.replace(' ', '_').str.replace(r'[^\w\s]', '', regex=True).tolist()

def upsert_batch(table_name: str, records: list, conflict_columns: str):
    if not records: return
    try:
        supabase.table(table_name).upsert(records, on_conflict=conflict_columns).execute()
    except Exception as e:
        logger.error(f"Error en tabla {table_name}: {e}")
        raise e

def process_and_upload(df_chunk: pd.DataFrame):
    df = df_chunk.copy()
    if TENANT_ID: df['tenant_id'] = TENANT_ID
    
    # Normalización de textos y códigos
    for col in ['documento', 'grupo', 'codigo_asignatura']:
        if col in df.columns:
            df[col] = df[col].astype(str).str.replace('.0', '', regex=False).str.strip()

    if 'nombres_docente' in df.columns:
        df['docente_full_name'] = (df['nombres_docente'].fillna('') + ' ' + df['apellidos_docente'].fillna('')).str.strip()

    # A. Catálogos
    if 'documento' in df.columns:
        students_df = df[['documento', 'nombres', 'apellidos', 'correo_electronico', 'tenant_id']].copy()
        students_df['full_name'] = (students_df['nombres'].fillna('') + ' ' + students_df['apellidos'].fillna('')).str.strip()
        students_df = students_df.rename(columns={'documento': 'external_id', 'correo_electronico': 'email'})
        students_df = students_df[['external_id', 'full_name', 'email', 'tenant_id']].drop_duplicates('external_id').dropna(subset=['external_id'])
        upsert_batch('students', students_df.to_dict('records'), 'tenant_id, external_id')

    if 'docente_full_name' in df.columns:
        teachers_df = df[['docente_full_name', 'tenant_id']].copy().rename(columns={'docente_full_name': 'full_name'})
        teachers_df = teachers_df.drop_duplicates('full_name').dropna(subset=['full_name'])
        teachers_df = teachers_df[teachers_df['full_name'] != '']
        upsert_batch('teachers', teachers_df.to_dict('records'), 'tenant_id, full_name')

    if 'codigo_asignatura' in df.columns:
        subjects_df = df[['codigo_asignatura', 'asignatura', 'creditos', 'tenant_id']].copy()
        subjects_df = subjects_df.rename(columns={'codigo_asignatura': 'code', 'asignatura': 'name', 'creditos': 'credits'})
        subjects_df['credits'] = pd.to_numeric(subjects_df['credits'], errors='coerce').fillna(0).astype(int)
        subjects_df = subjects_df.drop_duplicates('code').dropna(subset=['code'])
        upsert_batch('subjects', subjects_df.to_dict('records'), 'tenant_id, code')

    # B. Mapeo de UUIDs
    res_stud = supabase.table('students').select('id, external_id').eq('tenant_id', TENANT_ID).in_('external_id', df['documento'].unique().tolist()).execute()
    map_students = {r['external_id']: r['id'] for r in res_stud.data}

    res_teach = supabase.table('teachers').select('id, full_name').eq('tenant_id', TENANT_ID).in_('full_name', df['docente_full_name'].unique().tolist()).execute()
    map_teachers = {r['full_name']: r['id'] for r in res_teach.data}

    res_subj = supabase.table('subjects').select('id, code').eq('tenant_id', TENANT_ID).in_('code', df['codigo_asignatura'].unique().tolist()).execute()
    map_subjects = {r['code']: r['id'] for r in res_subj.data}

    # C. Grupos
    if 'grupo' in df.columns:
        groups_df = df[['grupo', 'año', 'semestre', 'codigo_asignatura', 'docente_full_name', 'tenant_id']].copy()
        groups_df['semester'] = groups_df['año'].astype(str).str.replace('.0','') + '-' + groups_df['semestre'].astype(str).str.replace('.0','')
        groups_df = groups_df.rename(columns={'grupo': 'group_code'})
        groups_df['subject_id'] = groups_df['codigo_asignatura'].map(map_subjects)
        groups_df['teacher_id'] = groups_df['docente_full_name'].map(map_teachers)
        groups_df = groups_df[['group_code', 'semester', 'subject_id', 'teacher_id', 'tenant_id']].dropna().drop_duplicates(['group_code', 'subject_id', 'semester'])
        upsert_batch('class_groups', groups_df.to_dict('records'), 'tenant_id, subject_id, semester, group_code')

    res_groups = supabase.table('class_groups').select('id, group_code, subject_id, semester').eq('tenant_id', TENANT_ID).in_('group_code', df['grupo'].unique().tolist()).execute()
    map_groups = {(r['group_code'], r['subject_id'], r['semester']): r['id'] for r in res_groups.data}

    # D. Horarios
    if 'dia' in df.columns:
        sched_df = df.copy()
        sched_df['semester'] = sched_df['año'].astype(str).str.replace('.0','') + '-' + sched_df['semestre'].astype(str).str.replace('.0','')
        sched_df['subject_id'] = sched_df['codigo_asignatura'].map(map_subjects)
        sched_df['group_id'] = list(zip(sched_df['grupo'], sched_df['subject_id'], sched_df['semester']))
        sched_df['group_id'] = sched_df['group_id'].map(map_groups)
        
        dia_map = {'LUNES': 1, 'MARTES': 2, 'MIÉRCOLES': 3, 'JUEVES': 4, 'VIERNES': 5, 'SÁBADO': 6, 'DOMINGO': 7}
        sched_df['day_of_week'] = sched_df['dia'].astype(str).str.upper().str.strip().map(dia_map)
        sched_df['start_time'] = sched_df['hora_inicial'].astype(str).str.replace('.0','').str.zfill(2) + ':' + sched_df['minutos_hora_inicial'].astype(str).str.replace('.0','').str.zfill(2) + ':00'
        
        # Filtramos los nulos
        sched_df = sched_df[['tenant_id', 'group_id', 'day_of_week', 'start_time', 'aula']].rename(columns={'aula': 'classroom'}).dropna(subset=['group_id', 'day_of_week'])
        
        # LA MAGIA: Forzamos la columna a entero para quitar el ".0"
        sched_df['day_of_week'] = sched_df['day_of_week'].astype(int)
        
        sched_df['end_time'] = df['hora_final'].astype(str).str.replace('.0','').str.zfill(2) + ':' + df['minutos_hora_final'].astype(str).str.replace('.0','').str.zfill(2) + ':00'
        
        sched_final = sched_df[['tenant_id', 'group_id', 'day_of_week', 'start_time', 'end_time', 'classroom']].copy()
        sched_final = sched_final.drop_duplicates(subset=['tenant_id', 'group_id', 'day_of_week', 'start_time'])
        
        upsert_batch('group_schedules', sched_final.to_dict('records'), 'tenant_id, group_id, day_of_week, start_time')
    # E. Notas
    if 'definitiva' in df.columns:
        perf_df = df.copy()
        perf_df['semester'] = perf_df['año'].astype(str).str.replace('.0','') + '-' + perf_df['semestre'].astype(str).str.replace('.0','')
        perf_df['subject_id'] = perf_df['codigo_asignatura'].map(map_subjects)
        perf_df['group_id'] = list(zip(perf_df['grupo'], perf_df['subject_id'], perf_df['semester']))
        perf_df['group_id'] = perf_df['group_id'].map(map_groups)
        perf_df['student_id'] = perf_df['documento'].map(map_students)
        perf_df['final_grade'] = pd.to_numeric(perf_df['definitiva'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0.0)
        perf_df = perf_df[['tenant_id', 'student_id', 'group_id', 'final_grade']].dropna().drop_duplicates(['tenant_id', 'student_id', 'group_id'])
        upsert_batch('academic_performance', perf_df.to_dict('records'), 'tenant_id, student_id, group_id')

def run_etl_pipeline(file_path: str, chunk_size: int = 500):
    wb = load_workbook(filename=file_path, read_only=True, data_only=True)
    ws = wb.active
    row_iterator = ws.iter_rows(values_only=True)
    headers = clean_column_names(next(row_iterator))
    chunk = []
    for row in row_iterator:
        chunk.append(row)
        if len(chunk) == chunk_size:
            process_and_upload(pd.DataFrame(chunk, columns=headers))
            chunk = []
    if chunk: process_and_upload(pd.DataFrame(chunk, columns=headers))
    logger.info("✅ Pipeline completado.")

if __name__ == "__main__":
    run_etl_pipeline("Desarrollo Curricular SIGA Semestre (1).xlsx")