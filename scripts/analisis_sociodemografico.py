import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import warnings

warnings.filterwarnings('ignore')

def limpiar_columnas(df):
    df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')
    return df

print("📥 Leyendo datos directamente del archivo maestro Excel...")
# Lee el Excel (ajusta el nombre si es diferente)
df = pd.read_excel("Desarrollo Curricular SIGA Semestre (1).xlsx")
df = limpiar_columnas(df)

print("⚙️ Procesando variables sociodemográficas...")
# 1. Calcular Mortalidad
if 'definitiva' in df.columns:
    df['definitiva_num'] = pd.to_numeric(df['definitiva'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
    df['mortalidad'] = df['definitiva_num'].apply(lambda x: 1 if x < 3.0 else 0)

# 2. Arreglar la hora para aislar la madrugada (6:00 AM)
df['hora_inicial'] = pd.to_numeric(df['hora_inicial'], errors='coerce')
df['es_madrugada'] = df['hora_inicial'].apply(lambda x: '6:00 AM' if x == 6 else 'Resto del Día')

# Limpiar Estrato y Sexo
if 'estrato' in df.columns:
    df['estrato'] = pd.to_numeric(df['estrato'], errors='coerce')
    df = df.dropna(subset=['estrato'])
    df['estrato'] = df['estrato'].astype(int).astype(str)

# ==========================================
# GRÁFICA A: FACTOR TRANSPORTE (Estrato vs Madrugada)
# ==========================================
print("🎨 Generando Gráfica A: Estrato y Madrugadas...")
plt.figure(figsize=(10, 6))
grafica_estrato = sns.barplot(
    data=df, 
    x='estrato', 
    y='mortalidad', 
    hue='es_madrugada',
    order=['1', '2', '3', '4', '5', '6'],
    palette={'6:00 AM': '#e74c3c', 'Resto del Día': '#3498db'} # Colores para el Dashboard
)
plt.title('Impacto de Madrugar (6 AM) en la Mortalidad Académica según el Estrato', fontsize=14, pad=15)
plt.ylabel('Tasa de Mortalidad / Reprobación', fontsize=12)
plt.xlabel('Estrato Socioeconómico', fontsize=12)
# Convertir eje Y a porcentaje
vals = grafica_estrato.get_yticks()
grafica_estrato.set_yticklabels(['{:,.0%}'.format(x) for x in vals])
plt.tight_layout()
plt.savefig('sociodemografico_estrato_transporte.png', dpi=300)

# ==========================================
# GRÁFICA B: BRECHA EN CIENCIAS EXACTAS (Sexo vs Mortalidad)
# ==========================================
print("🎨 Generando Gráfica B: Brecha de Género en Matemáticas...")
# Filtramos solo materias que suenen a ciencias exactas
materias_duras = df[df['asignatura'].str.contains('CALCULO|FISICA|ALGEBRA|PROGRAMACION', case=False, na=False)]

if not materias_duras.empty and 'sexo' in materias_duras.columns:
    plt.figure(figsize=(8, 6))
    grafica_sexo = sns.barplot(
        data=materias_duras, 
        x='sexo', 
        y='mortalidad', 
        palette='Set2',
        ci=None
    )
    plt.title('Tasa de Mortalidad en Ciencias Exactas por Sexo\n(Cálculo, Física, Álgebra)', fontsize=14, pad=15)
    plt.ylabel('Tasa de Reprobación', fontsize=12)
    plt.xlabel('Sexo', fontsize=12)
    vals = grafica_sexo.get_yticks()
    grafica_sexo.set_yticklabels(['{:,.0%}'.format(x) for x in vals])
    plt.tight_layout()
    plt.savefig('sociodemografico_brecha_ciencias.png', dpi=300)

print("✅ Análisis Sociodemográfico completado. Revisa las dos nuevas imágenes generadas.")