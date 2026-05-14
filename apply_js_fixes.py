import re

path = r'c:\Users\Admin\Documents\Proyecto-Dashboard-ITM\static\main.js'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. FIX KPIs
kpis_pattern = re.compile(r'// A\. Fetch KPIs.*?// B\. Fetch Heatmap', re.DOTALL)
kpis_new = """// A. Fetch KPIs
    try {
        console.log("Cargando sección: KPIs...");
        const targetSemestre = isComparing ? '2025-2' : semestre;
        const kpiRes = await fetch(`${API_BASE}/kpis?semestre=${targetSemestre}`);
        const kpiData = await kpiRes.json();
        
        console.log(`[DEBUG] KPIs | Semestre: ${targetSemestre} | Datos:`, kpiData);

        if (document.getElementById('kpi-mortalidad')) document.getElementById('kpi-mortalidad').innerText = kpiData.mortalidad_global;
        if (document.getElementById('kpi-estudiantes')) document.getElementById('kpi-estudiantes').innerText = kpiData.total_estudiantes.toLocaleString('es-CO');
        
        // Carga directa del valor de fantasmas desde el JSON unificado
        if (document.getElementById('kpi-fantasmas-valor')) {
            const fantasmas = kpiData.total_fantasmas || 0;
            document.getElementById('kpi-fantasmas-valor').innerText = fantasmas.toLocaleString('es-CO');
            const subtextoEl = document.getElementById('kpi-fantasmas-subtexto');
            if (subtextoEl) subtextoEl.innerHTML = `Alumnos con notas en cero`;
        }

        try {
            const kpiEstFooter = document.querySelector('#kpi-estudiantes')?.closest('.card')?.querySelector('.foot');
            if (kpiEstFooter) {
                kpiEstFooter.innerHTML = `<strong>${kpiData.total_estudiantes.toLocaleString('es-CO')}</strong> 
                    Estenciales Totales (${(kpiData.fuera_de_medellin_o_sin_datos || 0).toLocaleString('es-CO')} fuera de Medellín o sin barrio)`;
            }
        } catch (e) { console.warn('Fallo en footer KPI estudiantes:', e); }

        if (document.getElementById('kpi-asignatura-nombre')) document.getElementById('kpi-asignatura-nombre').innerText = (kpiData.asignatura_critica && kpiData.asignatura_critica.nombre) ? kpiData.asignatura_critica.nombre : 'N/A';
        if (document.getElementById('kpi-asignatura-pct')) document.getElementById('kpi-asignatura-pct').innerText = (kpiData.asignatura_critica && kpiData.asignatura_critica.porcentaje) ? kpiData.asignatura_critica.porcentaje + '% de reprobación' : '0%';
    } catch (error) {
        console.error("Fallo crítico en sección KPIs:", error);
    }

    // B. Fetch Heatmap"""
content = kpis_pattern.sub(kpis_new, content)

# 2. FIX MATERIAS
materias_pattern = re.compile(r'// F\. Fetch Materias Filtro.*?// G\. Fetch Sedes', re.DOTALL)
materias_new = """// F. Fetch Materias Filtro
    try {
        console.log("Cargando sección: Materias Filtro...");
        // API correcta: /api/materias-list
        const fetchRes = await fetchChartData('materias-list'); 
        
        // Protección contra undefined (El problema de forEach)
        if (!Array.isArray(fetchRes.data1)) fetchRes.data1 = [];
        if (!Array.isArray(fetchRes.data2)) fetchRes.data2 = [];

        console.log(`[DEBUG] Materias | Semestre: ${semestre} | Datos:`, fetchRes);

        if (fetchRes.data1.length === 0 && (!fetchRes.isComparing || fetchRes.data2.length === 0)) {
            console.warn("[DEBUG] Datos inválidos o vacíos para Materias");
        } else {
            const processed = processChartData(fetchRes, true); // Reverse for horizontal

            // Mapeo blindado manual
            materiasChart.setOption({
                yAxis: { type: 'category', data: processed.categories },
                series: getSeriesConfig(processed),
                tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: commonTooltipFormatter }
            }, { replaceMerge: ['series', 'yAxis'] });
        }
    } catch (error) {
        console.error("Fallo en sección Materias:", error);
    }

    // G. Fetch Sedes"""
content = materias_pattern.sub(materias_new, content)

# 3. FIX JORNADA
jornada_pattern = re.compile(r'// H\. Fetch Jornada.*?// I\. Fetch Rutas Transporte \(Mapa\)', re.DOTALL)
jornada_new = """// H. Fetch Jornada
    try {
        console.log("Cargando sección: Jornada...");
        const fetchRes = await fetchChartData('jornada');
        
        // Protección contra undefined
        if (!Array.isArray(fetchRes.data1)) fetchRes.data1 = [];
        if (!Array.isArray(fetchRes.data2)) fetchRes.data2 = [];

        console.log(`[DEBUG] Jornada | Semestre: ${semestre} | Datos:`, fetchRes);

        if (fetchRes.data1.length === 0 && (!fetchRes.isComparing || fetchRes.data2.length === 0)) {
            console.warn("[DEBUG] Datos inválidos o vacíos para Jornada");
        } else {
            const processed = processChartData(fetchRes, false);

            // Mapeo blindado manual para ECharts
            jornadaChart.setOption({
                xAxis: { type: 'category', data: processed.categories },
                series: getSeriesConfig(processed),
                tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: commonTooltipFormatter }
            }, { replaceMerge: ['series', 'xAxis'] });

            // Update Total Evaluaciones KPI
            let totalEvaluaciones = processed.data1.reduce((sum, j) => sum + (j.total_evaluaciones || 0), 0);
            if (fetchRes.isComparing) {
                totalEvaluaciones += processed.data2.reduce((sum, j) => sum + (j.total_evaluaciones || 0), 0);
            }
            const contadorRegistros = document.getElementById('contador-registros');
            if (contadorRegistros) {
                contadorRegistros.innerText = totalEvaluaciones.toLocaleString('es-CO');
            }
        }
    } catch (error) {
        console.error("Fallo en sección Jornada:", error);
    }

    // I. Fetch Rutas Transporte (Mapa)"""
content = jornada_pattern.sub(jornada_new, content)

# 4. FIX processChartData global para evitar "forEach is not a function" en el resto de charts
process_pattern = re.compile(r'function processChartData\(fetchResult, reverse = false\) \{.*?let raw1 = fetchResult\.data1 \|\| \[\];.*?let raw2 = fetchResult\.data2 \|\| \[\];', re.DOTALL)
process_new = """function processChartData(fetchResult, reverse = false) {
    // Protección global contra endpoints que devuelven diccionarios de error o undefined
    let raw1 = Array.isArray(fetchResult.data1) ? fetchResult.data1 : [];
    let raw2 = Array.isArray(fetchResult.data2) ? fetchResult.data2 : [];"""
content = process_pattern.sub(process_new, content)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("JS patches aplicados correctamente.")
