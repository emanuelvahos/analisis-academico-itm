import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import warnings

# Silenciar advertencias visuales
warnings.filterwarnings('ignore')

def limpiar_columnas(df):
    df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')
    return df

print("📥 Leyendo datos directamente del archivo maestro Excel...")
df = pd.read_excel("Desarrollo Curricular SIGA Semestre (1).xlsx")
df = limpiar_columnas(df)

print("⚙️ Procesando variables académicas y docentes...")

# 1. Calcular Mortalidad
if 'definitiva' in df.columns:
    df['definitiva_num'] = pd.to_numeric(df['definitiva'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
    df['mortalidad'] = df['definitiva_num'].apply(lambda x: 1 if x < 3.0 else 0)

# 2. Crear nombre completo del docente para agrupar
if 'nombres_docente' in df.columns and 'apellidos_docente' in df.columns:
    df['docente_full'] = df['nombres_docente'].fillna('') + ' ' + df['apellidos_docente'].fillna('')
    df['docente_full'] = df['docente_full'].str.strip()


# ==========================================
# GRÁFICA A: TOP 15 DOCENTES CON MAYOR MORTALIDAD (Bar Chart)
# ==========================================
print("🎨 Generando Gráfica A: Top Docentes Críticos (Nueva Versión)...")

docentes_stats = df.groupby('docente_full').agg(
    total_estudiantes=('mortalidad', 'count'),
    tasa_mortalidad=('mortalidad', 'mean')
).reset_index()

# Filtramos para que sean casos estadísticamente fuertes (mínimo 40 estudiantes evaluados en el semestre)
docentes_stats = docentes_stats[docentes_stats['total_estudiantes'] >= 40]

# Ordenamos de mayor a menor mortalidad y sacamos el Top 15
top_docentes = docentes_stats.sort_values(by='tasa_mortalidad', ascending=False).head(15)
top_docentes['tasa_mortalidad_pct'] = top_docentes['tasa_mortalidad'] * 100

# LA MAGIA: Creamos una etiqueta combinada -> "Nombre Docente (N est.)"
top_docentes['etiqueta_eje_y'] = top_docentes.apply(
    lambda row: f"{row['docente_full']} ({int(row['total_estudiantes'])} est.)", axis=1
)

plt.figure(figsize=(12, 8))
grafica_docentes = sns.barplot(
    data=top_docentes,
    x='tasa_mortalidad_pct',
    y='etiqueta_eje_y',
    palette='rocket' # Paleta de colores que va de oscuro (más crítico) a claro
)

# Añadimos el porcentaje exacto al final de cada barra
for i in grafica_docentes.containers:
    grafica_docentes.bar_label(i, fmt='%.1f%%', padding=5, fontweight='bold')

plt.title('Top 15 Docentes con Mayor Tasa de Reprobación\n(Se incluyen solo docentes con más de 40 estudiantes)', fontsize=15, pad=15)
plt.xlabel('Tasa de Mortalidad (%)', fontsize=12)
plt.ylabel('Docente (Total Estudiantes Evaluados)', fontsize=12)

# Añadimos una línea punteada que muestre el promedio general del ITM como punto de comparación
promedio_general = df['mortalidad'].mean() * 100
plt.axvline(x=promedio_general, color='grey', linestyle='--', label=f'Promedio General ITM ({promedio_general:.1f}%)')
plt.legend()

# Extendemos un poco el eje X para que los números no se corten
plt.xlim(0, max(top_docentes['tasa_mortalidad_pct']) + 10)
plt.tight_layout()
plt.savefig('docencia_top_severidad.png', dpi=300)


# ==========================================
# GRÁFICA B: TOP 10 MATERIAS "FILTRO"
# ==========================================
print("🎨 Generando Gráfica B: Materias Cuello de Botella (Corregida)...")

# Filtramos materias que no son de carga académica normal
df_materias = df[~df['asignatura'].str.contains('NIVELATORIO|GRADO|PRACTICA', case=False, na=False)]

materias_stats = df_materias.groupby('asignatura').agg(
    total_estudiantes=('mortalidad', 'count'),
    tasa_mortalidad=('mortalidad', 'mean')
).reset_index()

materias_stats = materias_stats[materias_stats['total_estudiantes'] >= 30]
materias_stats['tasa_mortalidad_pct'] = materias_stats['tasa_mortalidad'] * 100 # A porcentaje para la etiqueta
top_filtros = materias_stats.sort_values(by='tasa_mortalidad_pct', ascending=False).head(10)

plt.figure(figsize=(11, 6))
grafica_materias = sns.barplot(data=top_filtros, x='tasa_mortalidad_pct', y='asignatura', palette='Reds_r')

# LA CORRECCIÓN: Agregar los números al final de cada barra
for i in grafica_materias.containers:
    grafica_materias.bar_label(i, fmt='%.1f%%', padding=5, fontweight='bold')

plt.title('Top 10 Materias "Filtro" Tradicionales', fontsize=14, pad=15)
plt.xlabel('Tasa de Mortalidad (%)', fontsize=12)
plt.ylabel('')
# Extender el límite de X para que la etiqueta quepa
plt.xlim(0, max(top_filtros['tasa_mortalidad_pct']) + 10) 
plt.tight_layout()
plt.savefig('docencia_materias_filtro.png', dpi=300)


# ==========================================
# GRÁFICA C: EFECTO SEDE
# ==========================================
if 'sede' in df.columns:
    print("🎨 Generando Gráfica C: Rendimiento por Sede (Corregida)...")
    
    sede_stats = df.groupby('sede').agg(
        total_estudiantes=('mortalidad', 'count'),
        tasa_mortalidad=('mortalidad', 'mean')
    ).reset_index()
    
    sede_stats = sede_stats[sede_stats['total_estudiantes'] >= 50]
    sede_stats['tasa_mortalidad_pct'] = sede_stats['tasa_mortalidad'] * 100

    plt.figure(figsize=(10, 7))
    # LA CORRECCIÓN: Invertimos X y Y para hacer barras horizontales
    grafica_sede = sns.barplot(data=sede_stats.sort_values('tasa_mortalidad_pct', ascending=False), y='sede', x='tasa_mortalidad_pct', palette='viridis')
    
    # Agregamos las etiquetas de datos
    for i in grafica_sede.containers:
        grafica_sede.bar_label(i, fmt='%.1f%%', padding=5)

    plt.title('Mortalidad Académica según la Sede del ITM', fontsize=14, pad=15)
    plt.xlabel('Tasa de Mortalidad General (%)', fontsize=12)
    plt.ylabel('Sede / Campus', fontsize=12)
    plt.xlim(0, max(sede_stats['tasa_mortalidad_pct']) + 10)
    plt.tight_layout()
    plt.savefig('docencia_efecto_sede.png', dpi=300)

print("✅ Análisis Docente completado. Revisa las 3 nuevas imágenes limpias.")