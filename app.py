import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import plotly.graph_objects as go

# Configuración principal
st.set_page_config(page_title="ITM Dashboard", layout="wide", page_icon="📊")

# Constantes
API_BASE = "http://127.0.0.1:8000/api"

# --- FUNCIONES DE ACCESO A DATOS (CACHÉ HABILITADO) ---
@st.cache_data(ttl=3600)
def fetch_api_data(endpoint: str, params: dict = None):
    """Consulta la API interna del dashboard. Usamos caché de 1 hora."""
    try:
        if params is None:
            params = {}
        r = requests.get(f"{API_BASE}/{endpoint}", params=params, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Error fetching data from /{endpoint}: {e}")
        return []

# --- INTERFAZ ---
st.title("📊 ITM · Dashboard Analítico Académico")
st.markdown("Monitor de rendimiento estudiantil y mortalidad académica.")

# Barra lateral para filtros
st.sidebar.header("Filtros Globales")
semestres_disponibles = ["2025-2", "2025-1", "2024-2", "2024-1"]
semestre_seleccionado = st.sidebar.selectbox("Semestre", semestres_disponibles, index=0)

# Cargar KPIs Globales
kpis = fetch_api_data("kpis", {"semestre": semestre_seleccionado})

if isinstance(kpis, dict) and "total_estudiantes" in kpis:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Estudiantes Activos", f"{kpis['total_estudiantes']:,}")
    col2.metric("Mortalidad Global", f"{kpis['mortalidad_global']}%")
    
    critica = kpis.get("asignatura_critica", {})
    col3.metric(f"Materia Crítica", critica.get('nombre', 'N/A'), f"{critica.get('porcentaje', 0)}% mortalidad", delta_color="inverse")
    
    # Estudiantes fantasma
    fantasmas = fetch_api_data("kpi-fantasmas", {"semestre": semestre_seleccionado})
    f_total = fantasmas.get("total_estudiantes_unicos", 0) if isinstance(fantasmas, dict) else 0
    f_pct = fantasmas.get("porcentaje_del_total", 0) if isinstance(fantasmas, dict) else 0
    col4.metric("Estudiantes Fantasma", f"{f_total}", f"{f_pct}% del total", delta_color="inverse")

st.markdown("---")

# Layout de gráficas
col_charts_1, col_charts_2 = st.columns(2)

with col_charts_1:
    st.subheader("Mortalidad por Jornada")
    jornada_data = fetch_api_data("jornada", {"semestre": semestre_seleccionado})
    if jornada_data:
        df_j = pd.DataFrame(jornada_data)
        if not df_j.empty and 'name' in df_j.columns and 'value' in df_j.columns:
            df_j['Mortalidad (%)'] = (df_j['value'] * 100).round(1)
            fig = px.bar(df_j, x='name', y='Mortalidad (%)', color='name', 
                         title="Impacto por Jornada", 
                         labels={'name': 'Jornada'})
            st.plotly_chart(fig, use_container_width=True)

with col_charts_2:
    st.subheader("Brecha de Género")
    genero_data = fetch_api_data("brecha-ciencias", {"semestre": semestre_seleccionado})
    if genero_data:
        df_g = pd.DataFrame(genero_data)
        if not df_g.empty and 'name' in df_g.columns and 'value' in df_g.columns:
            df_g['Mortalidad (%)'] = (df_g['value'] * 100).round(1)
            fig = px.pie(df_g, names='name', values='Mortalidad (%)', 
                         title="Mortalidad según Sexo",
                         hole=0.4)
            st.plotly_chart(fig, use_container_width=True)

st.markdown("---")
col_charts_3, col_charts_4 = st.columns(2)

with col_charts_3:
    st.subheader("Mortalidad por Nivel de Adaptación")
    adapt_data = fetch_api_data("adaptacion", {"semestre": semestre_seleccionado})
    if adapt_data:
        df_a = pd.DataFrame(adapt_data)
        if not df_a.empty and 'name' in df_a.columns and 'value' in df_a.columns:
            df_a['Mortalidad (%)'] = (df_a['value'] * 100).round(1)
            fig = px.bar(df_a, x='name', y='Mortalidad (%)', 
                         title="Antigüedad del Estudiante",
                         color='name')
            st.plotly_chart(fig, use_container_width=True)

with col_charts_4:
    st.subheader("Top 10 Docentes con Mayor Mortalidad")
    docentes_data = fetch_api_data("teachers", {"semestre": semestre_seleccionado})
    if docentes_data:
        df_d = pd.DataFrame(docentes_data).head(10)
        if not df_d.empty and 'name' in df_d.columns and 'value' in df_d.columns:
            df_d['Mortalidad (%)'] = (df_d['value'] * 100).round(1)
            # Ordenar para Plotly (las barras horizontales se grafican de abajo hacia arriba)
            df_d = df_d.sort_values('Mortalidad (%)', ascending=True)
            fig = px.bar(df_d, x='Mortalidad (%)', y='name', orientation='h',
                         title="Docentes Críticos (>30 evaluaciones)")
            st.plotly_chart(fig, use_container_width=True)

st.markdown("---")
st.subheader("Top Materias con Mayor Mortalidad")
materias_data = fetch_api_data("materias-filtro", {"semestre": semestre_seleccionado})
if materias_data:
    df_m = pd.DataFrame(materias_data)
    if not df_m.empty and 'name' in df_m.columns and 'value' in df_m.columns:
        df_m['Mortalidad (%)'] = (df_m['value'] * 100).round(1)
        fig = px.bar(df_m, x='name', y='Mortalidad (%)', text='Mortalidad (%)',
                     title="Materias Críticas")
        fig.update_traces(textposition='outside')
        st.plotly_chart(fig, use_container_width=True)

