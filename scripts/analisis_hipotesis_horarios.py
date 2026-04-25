import os
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from dotenv import load_dotenv
from supabase import create_client, Client
import statsmodels.formula.api as smf
import warnings

# Silenciar advertencias de formato de Pandas
warnings.filterwarnings('ignore')

# ==========================================
# 1. CONFIGURACIÓN
# ==========================================
load_dotenv()
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def fetch_table(table_name: str, columns: str = "*") -> pd.DataFrame:
    """Extrae TODOS los registros paginando para evadir el límite de 1000 de Supabase."""
    all_data = []
    start = 0
    page_size = 1000
    
    while True:
        response = supabase.table(table_name).select(columns).range(start, start + page_size - 1).execute()
        data = response.data
        if not data: break
        all_data.extend(data)
        if len(data) < page_size: break
        start += page_size
        
    return pd.DataFrame(all_data)

# ==========================================
# 2. EXTRACCIÓN Y CRUCE
# ==========================================
print("📥 Iniciando extracción masiva de datos desde la nube...")
df_perf = fetch_table("academic_performance")
df_groups = fetch_table("class_groups").rename(columns={'id': 'group_id'})
df_sched = fetch_table("group_schedules")
df_teachers = fetch_table("teachers").rename(columns={'id': 'teacher_id', 'full_name': 'teacher_name'})

print("🔄 Cruzando tablas relacionales...")

# Bórramos la columna duplicada 'tenant_id' de las tablas secundarias para evitar choques en Pandas
df_groups = df_groups.drop(columns=['tenant_id', 'created_at', 'updated_at'], errors='ignore')
df_sched = df_sched.drop(columns=['tenant_id', 'created_at', 'updated_at'], errors='ignore')
df_teachers = df_teachers.drop(columns=['tenant_id', 'created_at', 'updated_at'], errors='ignore')

# Unimos Notas -> Grupos -> Horarios -> Profesores
df_master = df_perf.merge(df_groups, on='group_id', how='inner')
df_master = df_master.merge(df_sched, on='group_id', how='inner')
df_master = df_master.merge(df_teachers, on='teacher_id', how='inner')

# ==========================================
# 3. LIMPIEZA Y CORRECCIÓN DE SESGOS
# ==========================================
print("🧹 Aplicando corrección de horas fantasmas y empaquetando en bloques...")

# Convertir la columna de texto de la BD a objeto de tiempo (extraemos la hora)
df_master['hora_cruda'] = pd.to_datetime(df_master['start_time'], format='%H:%M:%S', errors='coerce').dt.hour

# ELIMINAR SESGO: Si la hora es <= 5 (ej. 4 AM), significa que era 4 PM (16:00) en la realidad
df_master['hora_real'] = df_master['hora_cruda'].apply(lambda x: x + 12 if x <= 5 else x)

# ---------------- NUEVO CÓDIGO DE EMPAQUETADO (CORREGIDO) ----------------
# Redujimos el límite hasta las 22 (10:00 PM) para que las clases fantasma desaparezcan
limites = [6, 8, 10, 12, 14, 16, 18, 20, 22]
etiquetas = ['06:00-08:00', '08:00-10:00', '10:00-12:00', '12:00-14:00', 
             '14:00-16:00', '16:00-18:00', '18:00-20:00', '20:00-22:00']

# Empaquetamos. Cualquier hora rara que pase de las 22:00 quedará como "NaN" (Nula)
df_master['franja_horaria'] = pd.cut(df_master['hora_real'], bins=limites, labels=etiquetas, right=False)

# Al eliminar los nulos, eliminamos automáticamente a los "fantasmas" de la madrugada
df_master = df_master.dropna(subset=['franja_horaria'])
# -------------------------------------------------------------

# Definir Mortalidad: Si la definitiva es menor a 3.0 (incluye abandonos y ceros) = 1 (Mortalidad)
df_master['mortalidad'] = df_master['final_grade'].apply(lambda x: 1 if float(x) < 3.0 else 0)

# Mapear días de la semana
dias_semana = {1: 'Lunes', 2: 'Martes', 3: 'Miércoles', 4: 'Jueves', 5: 'Viernes', 6: 'Sábado'}
df_master['dia_nombre'] = df_master['day_of_week'].map(dias_semana)

# ==========================================
# 4. AISLAMIENTO ESTADÍSTICO (REGRESIÓN LOGÍSTICA)
# ==========================================
print("\n🧠 Ejecutando modelo de aislamiento estadístico (Horario vs Profesor)...")

# Usamos IDs en lugar de nombres para que la fórmula matemática no falle con espacios
df_master['profe_codigo'] = df_master['teacher_id'].astype('category').cat.codes

try:
    # Fórmula: ¿La mortalidad se explica por la franja horaria controlando al profesor?
    modelo = smf.logit('mortalidad ~ C(franja_horaria) + C(profe_codigo)', data=df_master).fit(disp=0)
    
    print("\n" + "="*60)
    print("--- RESULTADOS PUROS DEL HORARIO (Sin sesgo de profesor) ---")
    
    # Extraemos solo los resultados que corresponden a las horas
    pvalues_horas = modelo.pvalues[modelo.pvalues.index.str.contains('franja_horaria')]
    horas_criticas = pvalues_horas[pvalues_horas < 0.05]
    
    if not horas_criticas.empty:
        print("🚨 CONCLUSIÓN: La hipótesis es CORRECTA. Incluso aislando a los profesores estrictos,")
        print("la hora de la clase impacta fuertemente en el rendimiento del estudiante.")
        print("Franjas con impacto estadísticamente comprobado (p-value < 0.05):")
        print(horas_criticas.to_string())
    else:
        print("🟢 CONCLUSIÓN: La hipótesis inicial fue un espejismo.")
        print("Al aislar a los profesores, el horario por sí solo NO tiene un impacto matemático real.")
    print("="*60 + "\n")
    
except Exception as e:
    print(f"⚠️ Advertencia estadística: {e}")

# ==========================================
# 5. VISUALIZACIÓN CORREGIDA
# ==========================================
print("🎨 Generando el Heatmap definitivo...")

# Ordenar días y horas lógicamente
orden_dias = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado']
orden_horas = sorted(df_master['franja_horaria'].unique())

pivot_table = df_master.pivot_table(
    values='mortalidad', 
    index='franja_horaria', 
    columns='dia_nombre', 
    aggfunc='mean'
)
pivot_table = pivot_table.reindex(index=orden_horas, columns=orden_dias)

plt.figure(figsize=(12, 8))
sns.heatmap(pivot_table, annot=True, fmt=".1%", cmap="YlOrRd", linewidths=.5, vmin=0, vmax=1)
plt.title('Tasa Real de Mortalidad Académica por Franja Horaria\n(Datos corregidos y sin sesgo de madrugada)', fontsize=16, pad=20)
plt.xlabel('Día de la Semana', fontsize=12)
plt.ylabel('Franja Horaria (Hora Exacta)', fontsize=12)
plt.tight_layout()

plt.savefig('mortalidad_horario_corregida.png', dpi=300, bbox_inches='tight')
print("✅ Análisis finalizado. Nueva gráfica guardada como 'mortalidad_horario_corregida.png'")
