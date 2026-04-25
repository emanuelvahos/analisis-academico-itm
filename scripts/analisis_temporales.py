import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import warnings

warnings.filterwarnings('ignore')

def limpiar_columnas(df):
    df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')
    return df

print("📥 Leyendo datos directamente del archivo maestro Excel...")
df = pd.read_excel("Desarrollo Curricular SIGA Semestre (1).xlsx")
df = limpiar_columnas(df)

print("⚙️ Procesando variables temporales y de adaptación...")

# 1. Calcular Mortalidad
if 'definitiva' in df.columns:
    df['definitiva_num'] = pd.to_numeric(df['definitiva'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
    df['mortalidad'] = df['definitiva_num'].apply(lambda x: 1 if x < 3.0 else 0)

# Limpiar variables clave
df['dia'] = df['dia'].astype(str).str.upper().str.strip()
df['hora_inicial'] = pd.to_numeric(df['hora_inicial'], errors='coerce')


# ==========================================
# GRÁFICA A: JORNADA DIURNA VS NOCTURNA
# ==========================================
print("🎨 Generando Gráfica A: Diurna vs Nocturna...")

# Clasificamos la jornada (Asumimos que la noche empieza a las 18:00 / 6 PM)
# Si la hora inicial es <= 5, recordamos que es la tarde (ej. 4 = 16:00)
df['hora_real'] = df['hora_inicial'].apply(lambda x: x + 12 if pd.notnull(x) and x <= 5 else x)

def clasificar_jornada(hora):
    if pd.isnull(hora): return None
    if hora >= 18: return 'Nocturna (18:00 - 22:00)'
    return 'Diurna (06:00 - 17:59)'

df['jornada'] = df['hora_real'].apply(clasificar_jornada)

jornada_stats = df.dropna(subset=['jornada']).groupby('jornada').agg(
    tasa_mortalidad=('mortalidad', 'mean')
).reset_index()

plt.figure(figsize=(8, 5))
grafica_jornada = sns.barplot(data=jornada_stats, x='jornada', y='tasa_mortalidad', palette='Set2')

for i in grafica_jornada.containers:
    grafica_jornada.bar_label(i, fmt='%.1f%%', padding=5, labels=[f"{x*100:.1f}%" for x in i.datavalues])

plt.title('Tasa de Mortalidad: Jornada Diurna vs Nocturna', fontsize=14, pad=15)
plt.ylabel('Tasa de Mortalidad', fontsize=12)
plt.xlabel('Tipo de Jornada', fontsize=12)
vals = grafica_jornada.get_yticks()
grafica_jornada.set_yticklabels(['{:,.0%}'.format(x) for x in vals])
plt.tight_layout()
plt.savefig('temporal_jornada.png', dpi=300)


# ==========================================
# GRÁFICA B: EL RIESGO DEL FIN DE SEMANA
# ==========================================
print("🎨 Generando Gráfica B: Sábado vs Entre Semana...")

def clasificar_dia(dia):
    if dia == 'NAN' or pd.isnull(dia): return None
    if dia == 'SÁBADO' or dia == 'DOMINGO': return 'Fin de Semana'
    return 'Lunes a Viernes'

df['tipo_dia'] = df['dia'].apply(clasificar_dia)

dia_stats = df.dropna(subset=['tipo_dia']).groupby('tipo_dia').agg(
    tasa_mortalidad=('mortalidad', 'mean')
).reset_index()

plt.figure(figsize=(8, 5))
grafica_dia = sns.barplot(data=dia_stats, x='tipo_dia', y='tasa_mortalidad', palette='coolwarm')

for i in grafica_dia.containers:
    grafica_dia.bar_label(i, fmt='%.1f%%', padding=5, labels=[f"{x*100:.1f}%" for x in i.datavalues])

plt.title('Rendimiento Académico: Clases de Fin de Semana vs Regular', fontsize=14, pad=15)
plt.ylabel('Tasa de Mortalidad', fontsize=12)
plt.xlabel('', fontsize=12)
vals = grafica_dia.get_yticks()
grafica_dia.set_yticklabels(['{:,.0%}'.format(x) for x in vals])
plt.tight_layout()
plt.savefig('temporal_fin_semana.png', dpi=300)


# ==========================================
# GRÁFICA C: CURVA DE ADAPTACIÓN (Antigüedad)
# ==========================================
if 'antigüedad' in df.columns:
    print("🎨 Generando Gráfica C: Curva de Adaptación (Antigüedad)...")
    
    # Limpiamos la antigüedad (Semestre en el que va el estudiante)
    df['semestre_estudiante'] = pd.to_numeric(df['antigüedad'], errors='coerce')
    
    # Filtramos para ver solo desde el semestre 1 hasta el 10 (carrera normal)
    df_curva = df[(df['semestre_estudiante'] >= 1) & (df['semestre_estudiante'] <= 10)]
    
    curva_stats = df_curva.groupby('semestre_estudiante').agg(
        tasa_mortalidad=('mortalidad', 'mean')
    ).reset_index()
    
    curva_stats['tasa_mortalidad_pct'] = curva_stats['tasa_mortalidad'] * 100

    plt.figure(figsize=(10, 6))
    grafica_curva = sns.lineplot(
        data=curva_stats, 
        x='semestre_estudiante', 
        y='tasa_mortalidad_pct', 
        marker='o', 
        linewidth=2, 
        color='#2ecc71',
        markersize=8
    )

    plt.title('Curva de Adaptación: Mortalidad Académica según el Semestre Cursado', fontsize=14, pad=15)
    plt.ylabel('Tasa de Mortalidad (%)', fontsize=12)
    plt.xlabel('Semestre Cursado por el Estudiante (Antigüedad)', fontsize=12)
    
    # Forzar que el eje X muestre números enteros (1 al 10)
    plt.xticks(range(1, 11))
    
    # Añadir los porcentajes encima de cada punto para mejor lectura
    for x, y in zip(curva_stats['semestre_estudiante'], curva_stats['tasa_mortalidad_pct']):
        plt.text(x, y + 1.5, f'{y:.1f}%', ha='center', fontsize=9, fontweight='bold')
        
    # Extender un poco el eje Y para que los textos no se corten
    plt.ylim(0, max(curva_stats['tasa_mortalidad_pct']) + 5)
    
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.tight_layout()
    plt.savefig('temporal_curva_adaptacion.png', dpi=300)

print("✅ Análisis Temporal completado. Revisa las 3 nuevas imágenes.")