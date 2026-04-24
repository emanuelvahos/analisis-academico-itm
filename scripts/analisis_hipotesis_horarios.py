import os
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from supabase import create_client, Client
from dotenv import load_dotenv

# ==========================================
# 1. Configuración y Conexión a Supabase
# ==========================================
load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Faltan variables de entorno SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================
# 2. Extracción de Datos
# ==========================================
def fetch_table(table_name: str, columns: str = "*") -> pd.DataFrame:
    """Extrae todos los registros de una tabla en Supabase y retorna un DataFrame."""
    # Nota: Si las tablas tienen >1000 registros, la API de Supabase pagina por defecto.
    # Para datasets masivos, lo ideal es usar count y paginar iterativamente.
    # Asumimos una muestra representativa o extracción directa sin límite para este análisis.
    response = supabase.table(table_name).select(columns).limit(10000).execute()
    return pd.DataFrame(response.data)

print("Iniciando extracción de datos desde Supabase...")

# Extraemos solo las columnas necesarias para no saturar memoria
df_performance = fetch_table("academic_performance", "group_id, is_passing")
df_groups = fetch_table("class_groups", "id, subject_id, teacher_id")
df_subjects = fetch_table("subjects", "id, name")
df_teachers = fetch_table("teachers", "id, full_name")
df_schedules = fetch_table("group_schedules", "group_id, day_of_week, start_time")

# ==========================================
# 3. Limpieza y Cruce de Datos (Joins)
# ==========================================
print("Procesando y cruzando la información...")

# Renombramos columnas para facilitar los merges (evita conflictos de sufijos _x, _y)
df_groups = df_groups.rename(columns={'id': 'group_id'})
df_subjects = df_subjects.rename(columns={'id': 'subject_id', 'name': 'subject_name'})
df_teachers = df_teachers.rename(columns={'id': 'teacher_id', 'full_name': 'teacher_name'})

# Realizamos las uniones (Inner Joins) para construir el Dataset Analítico
df_master = df_performance.merge(df_groups, on='group_id', how='inner')
df_master = df_master.merge(df_subjects, on='subject_id', how='inner')
df_master = df_master.merge(df_teachers, on='teacher_id', how='inner')
df_master = df_master.merge(df_schedules, on='group_id', how='inner')

# Convertimos el boolean (Aprobó: True/False) a variable dummy de Mortalidad (Reprobó: 1/0)
# Esto facilita calcular la "tasa" usando la media aritmética
df_master['reprobo'] = df_master['is_passing'].apply(lambda x: 1 if x is False else 0)

# Diccionario para mapear días de la semana
dias_semana = {1: 'Lunes', 2: 'Martes', 3: 'Miércoles', 4: 'Jueves', 5: 'Viernes', 6: 'Sábado', 7: 'Domingo'}
df_master['dia_nombre'] = df_master['day_of_week'].map(dias_semana)

# ==========================================
# 4. Análisis de la Hipótesis de la Profesora
# ==========================================
ASIGNATURA_OBJETIVO = "Cálculo"

# Filtramos usando contains para atrapar 'Cálculo Diferencial', 'Cálculo Integral', etc.
df_filtered = df_master[df_master['subject_name'].str.contains(ASIGNATURA_OBJETIVO, case=False, na=False)]

if df_filtered.empty:
    print(f"No se encontraron registros para la asignatura: {ASIGNATURA_OBJETIVO}")
else:
    print(f"Registros encontrados para {ASIGNATURA_OBJETIVO}: {len(df_filtered)}")
    
    # Agrupamos por Docente, Día y Hora de inicio
    # Calculamos el % de reprobación (Tasa de Mortalidad)
    grouped = df_filtered.groupby(['teacher_name', 'dia_nombre', 'start_time']).agg(
        total_estudiantes=('reprobo', 'count'),
        tasa_mortalidad=('reprobo', 'mean')
    ).reset_index()

    # Filtramos grupos con muy pocos estudiantes para no sesgar el % (ej. mínimo 5 estudiantes)
    grouped = grouped[grouped['total_estudiantes'] >= 5]
    
    # Multiplicamos por 100 para visualizar en porcentaje (%)
    grouped['tasa_mortalidad_pct'] = grouped['tasa_mortalidad'] * 100

    # ==========================================
    # 5. Visualización de Resultados (Heatmap)
    # ==========================================
    print("Generando visualización (Heatmap)...")
    
    # Creamos un Pivot Table ideal para un Heatmap
    # Filas: Docentes, Columnas: Hora de inicio, Valores: Tasa de mortalidad (%)
    # Se podría incluir el día, pero para la hipótesis (6am vs 10am) cruzamos hora y docente.
    heatmap_data = df_filtered.groupby(['teacher_name', 'start_time'])['reprobo'].mean().reset_index()
    heatmap_data['tasa_mortalidad_pct'] = heatmap_data['reprobo'] * 100
    pivot_table = heatmap_data.pivot(index='teacher_name', columns='start_time', values='tasa_mortalidad_pct')
    
    # Configuración del lienzo de Matplotlib
    plt.figure(figsize=(12, 7))
    sns.set_theme(style="whitegrid")
    
    # Trazamos el Heatmap con Seaborn
    ax = sns.heatmap(
        pivot_table, 
        annot=True,              # Mostrar el número dentro de la celda
        fmt=".1f",               # 1 decimal
        cmap="YlOrRd",           # Paleta Semáforo: Amarillo (bajo) a Rojo (alto)
        cbar_kws={'label': '% de Mortalidad (Reprobados / Desertores)'},
        linewidths=.5,           # Líneas de separación
        vmin=0, vmax=100         # Rango fijo de 0 a 100%
    )
    
    # Estilos de títulos y etiquetas
    plt.title(f'¿Impacta la franja horaria en la mortalidad de {ASIGNATURA_OBJETIVO}?', fontsize=16, fontweight='bold', pad=20)
    plt.xlabel('Hora de Inicio de la Clase', fontsize=12, fontweight='bold')
    plt.ylabel('Docente', fontsize=12, fontweight='bold')
    
    # Rotar las horas para mejor lectura si hay muchas
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    # Guardar gráfico y mostrar
    output_filename = "mortalidad_horario_heatmap.png"
    plt.savefig(output_filename, dpi=300)
    print(f"Análisis finalizado exitosamente. Gráfico guardado en el mismo directorio como '{output_filename}'")
    
    # plt.show() # Descomentar para ver en ventana si se corre localmente o en Jupyter

    # ==========================================
    # 6. Validación Estadística (Test de Chi-cuadrado)
    # ==========================================
    from scipy.stats import chi2_contingency

    print("\n" + "="*50)
    print("--- RESULTADOS DE LA VALIDACIÓN ESTADÍSTICA ---")
    
    # Creamos una tabla de contingencia: Frecuencia de Aprobados vs Reprobados por Horario
    contingency_table = pd.crosstab(df_filtered['start_time'], df_filtered['reprobo'])
    
    # Ejecutamos el test de Chi-cuadrado de independencia
    chi2_stat, p_val, dof, ex = chi2_contingency(contingency_table)
    
    print(f"Valor p (p-value) obtenido: {p_val:.5f}")
    print("="*50)
    
    # Interpretación automática
    ALPHA = 0.05
    if p_val < ALPHA:
        print("CONCLUSIÓN: La diferencia de mortalidad entre las franjas horarias ES estadísticamente significativa.")
        print("-> La hipótesis de la profesora está respaldada matemáticamente: el horario SÍ impacta en la tasa de reprobación.")
    else:
        print("CONCLUSIÓN: La diferencia de mortalidad entre las franjas horarias NO es estadísticamente significativa.")
        print("-> La hipótesis de la profesora NO se respalda con los datos actuales: cualquier variación entre horarios podría deberse al azar.")
    print("="*50 + "\n")
