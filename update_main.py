import re

with open('static/main.js', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add `isComparing` state and helpers at the top
helpers_code = """
let currentSemestre = '2025-2';
let isComparing = false;
let currentMetrica = 'poblacion';

// --- HELPERS PARA COMPARACIÓN ---
async function fetchChartData(endpoint, materiaFilter = '') {
    let url2025_1 = `${API_BASE}/${endpoint}?semestre=2025-1`;
    let url2025_2 = `${API_BASE}/${endpoint}?semestre=2025-2`;
    let urlSingle = `${API_BASE}/${endpoint}?semestre=${currentSemestre}`;
    
    if (materiaFilter) {
        const query = `&materia=${encodeURIComponent(materiaFilter)}`;
        url2025_1 += query;
        url2025_2 += query;
        urlSingle += query;
    }
    
    if (isComparing) {
        const [res1, res2] = await Promise.all([fetch(url2025_1), fetch(url2025_2)]);
        return { isComparing: true, data1: await res1.json(), data2: await res2.json() };
    } else {
        const res = await fetch(urlSingle);
        return { isComparing: false, data1: await res.json(), data2: [] };
    }
}

function processChartData(fetchResult, reverse = false) {
    let raw1 = fetchResult.data1 || [];
    let raw2 = fetchResult.data2 || [];
    
    // Sort logic handles Adaptación specific case if needed, but we rely on backend sorting mostly.
    const allKeys = new Set();
    raw1.forEach(item => allKeys.add(item.name));
    if (fetchResult.isComparing) {
        raw2.forEach(item => allKeys.add(item.name));
    }
    
    let categories = Array.from(allKeys);
    if (reverse) categories.reverse();
    
    const map1 = new Map(raw1.map(item => [item.name, item]));
    const map2 = new Map(raw2.map(item => [item.name, item]));
    
    const data1 = categories.map(cat => map1.get(cat) || { name: cat, value: 0, total_evaluaciones: 0, total_estudiantes_unicos: 0, reprobados: 0 });
    const data2 = categories.map(cat => map2.get(cat) || { name: cat, value: 0, total_evaluaciones: 0, total_estudiantes_unicos: 0, reprobados: 0 });
    
    return { categories, data1, data2 };
}

function getSeriesConfig(processedData) {
    if (isComparing) {
        return [
            { name: '2025-1', type: 'bar', data: processedData.data1, itemStyle: {color: '#3b82f6'} },
            { name: '2025-2', type: 'bar', data: processedData.data2, itemStyle: {color: '#f97316'} }
        ];
    } else {
        return [
            { name: currentSemestre, type: 'bar', data: processedData.data1, itemStyle: {color: '#3b82f6'} }
        ];
    }
}
"""

content = re.sub(
    r"let currentSemestre = '2025-2';\nlet currentMetrica = 'poblacion';",
    helpers_code,
    content
)

# 2. Refactor loadData to use helpers
load_data_original = re.search(r"// 3\. Función de Carga de Datos \(Core\).*?// Función dedicada para el Mapa de Calor \(GeoJSON\)", content, re.DOTALL).group(0)

load_data_new = """// 3. Función de Carga de Datos (Core)
let isFetching = false;
async function loadData(semestre) {
    if (isFetching) {
        console.warn("Se ignoró una petición porque ya hay una carga masiva en progreso.");
        return;
    }
    
    isFetching = true;
    console.log("--- Iniciando carga de datos defensiva ---");
    [heatmapChart, teachersChart, adaptacionChart, brechaChart, materiasChart, sedesChart, jornadaChart, mapaChart].forEach(c => c && c.showLoading());

    // A. Fetch KPIs
    try {
        console.log("Cargando sección: KPIs...");
        const kpiRes = await fetch(`${API_BASE}/kpis?semestre=${isComparing ? '2025-2' : semestre}`);
        const kpiData = await kpiRes.json();

        if (document.getElementById('kpi-mortalidad')) document.getElementById('kpi-mortalidad').innerText = kpiData.mortalidad_global;
        if (document.getElementById('kpi-estudiantes')) document.getElementById('kpi-estudiantes').innerText = kpiData.total_estudiantes.toLocaleString('es-CO');

        try {
            const kpiEstFooter = document.querySelector('#kpi-estudiantes')?.closest('.card')?.querySelector('.foot');
            if (kpiEstFooter) {
                kpiEstFooter.innerHTML = `<strong>${kpiData.total_estudiantes.toLocaleString('es-CO')}</strong> 
                    Estenciales Totales (${(kpiData.fuera_de_medellin_o_sin_datos || 0).toLocaleString('es-CO')} fuera de Medellín o sin barrio)`;
            }
        } catch (e) { console.warn('Fallo en footer KPI estudiantes:', e); }

        if (document.getElementById('kpi-asignatura-nombre')) document.getElementById('kpi-asignatura-nombre').innerText = kpiData.asignatura_critica.nombre;
        if (document.getElementById('kpi-asignatura-pct')) document.getElementById('kpi-asignatura-pct').innerText = kpiData.asignatura_critica.porcentaje + '% de reprobación';
    } catch (error) {
        console.error("Fallo crítico en sección KPIs:", error);
    }

    // B. Fetch Heatmap
    try {
        console.log("Cargando sección: Heatmap...");
        const heatmapRes = await fetch(`${API_BASE}/heatmap?semestre=${isComparing ? '2025-2' : semestre}`);
        const heatmapRaw = await heatmapRes.json();
        const heatmapFormatted = heatmapRaw.map(item => {
            const x = days.indexOf(item.dia_nombre);
            const y = hours.indexOf(item.franja_horaria);
            return [x, y, item.mortalidad];
        }).filter(item => item[0] !== -1 && item[1] !== -1);
        heatmapChart.setOption({ series: [{ data: heatmapFormatted }] });
    } catch (error) {
        console.error("Fallo en sección Heatmap:", error);
    }

    // Custom formatter for tooltip
    const commonTooltipFormatter = function (params) {
        // Handle array of params for grouped bars (axis trigger) or single param (item trigger)
        const paramList = Array.isArray(params) ? params : [params];
        let tooltipHtml = `<b>${paramList[0].name}</b><br/>`;
        
        paramList.forEach(p => {
            const d = p.data || {};
            tooltipHtml += `<div style="margin-top: 5px;">
                <span style="display:inline-block;margin-right:4px;border-radius:10px;width:10px;height:10px;background-color:${p.color};"></span>
                <b>${p.seriesName}</b><br/>
                Evaluaciones: ${d.total_evaluaciones || 0}<br/>
                Estudiantes: ${d.total_estudiantes_unicos || 0}<br/>
                Mortalidad: ${((d.value || 0) * 100).toFixed(1)}%
            </div>`;
        });
        return tooltipHtml;
    };

    // C. Fetch Docentes
    try {
        console.log("Cargando sección: Docentes...");
        const materiaFilter = document.getElementById('materia-docente-filter')?.value || '';
        const fetchRes = await fetchChartData('teachers', materiaFilter);
        const processed = processChartData(fetchRes, true); // Reverse for horizontal

        teachersChart.setOption({
            yAxis: { data: processed.categories },
            series: getSeriesConfig(processed),
            tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: commonTooltipFormatter }
        }, { replaceMerge: ['series', 'yAxis'] });
    } catch (error) {
        console.error("Fallo en sección Docentes:", error);
    }

    // D. Fetch Adaptacion
    try {
        console.log("Cargando sección: Adaptación...");
        const fetchRes = await fetchChartData('adaptacion');
        
        // Ensure 1 to 10 fallback if empty
        if (!fetchRes.data1 || fetchRes.data1.length === 0) {
            fetchRes.data1 = Array.from({ length: 10 }, (_, i) => ({ name: `Semestre ${i + 1}`, value: 0.45 - (i * 0.03), total_evaluaciones: 0, total_estudiantes_unicos: 0, reprobados: 0 }));
        }
        if (fetchRes.isComparing && (!fetchRes.data2 || fetchRes.data2.length === 0)) {
            fetchRes.data2 = Array.from({ length: 10 }, (_, i) => ({ name: `Semestre ${i + 1}`, value: 0.40 - (i * 0.02), total_evaluaciones: 0, total_estudiantes_unicos: 0, reprobados: 0 }));
        }

        const processed = processChartData(fetchRes, false);
        // Sort by semestre number
        const sortOrder = Array.from({length: 15}, (_, i) => String(i+1));
        const sortIndices = processed.categories.map((c, i) => i).sort((a, b) => sortOrder.indexOf(processed.categories[a]) - sortOrder.indexOf(processed.categories[b]));
        
        processed.categories = sortIndices.map(i => processed.categories[i]);
        processed.data1 = sortIndices.map(i => processed.data1[i]);
        processed.data2 = sortIndices.map(i => processed.data2[i]);

        adaptacionChart.setOption({
            xAxis: { type: 'category', data: processed.categories },
            series: getSeriesConfig(processed),
            tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: commonTooltipFormatter }
        }, { replaceMerge: ['series', 'xAxis'] });
    } catch (error) {
        console.error("Fallo en sección Adaptación:", error);
    }

    // E. Fetch Brecha de Género
    try {
        console.log("Cargando sección: Brecha de Género...");
        const fetchRes = await fetchChartData('brecha-ciencias');
        const processed = processChartData(fetchRes, false);

        brechaChart.setOption({
            xAxis: { data: processed.categories },
            series: getSeriesConfig(processed),
            tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: commonTooltipFormatter }
        }, { replaceMerge: ['series', 'xAxis'] });
    } catch (error) {
        console.error("Fallo en sección Brecha:", error);
    }

    // F. Fetch Materias Filtro
    try {
        console.log("Cargando sección: Materias Filtro...");
        const fetchRes = await fetchChartData('materias-filtro');
        const processed = processChartData(fetchRes, true); // Reverse for horizontal

        materiasChart.setOption({
            yAxis: { data: processed.categories },
            series: getSeriesConfig(processed),
            tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: commonTooltipFormatter }
        }, { replaceMerge: ['series', 'yAxis'] });
    } catch (error) {
        console.error("Fallo en sección Materias:", error);
    }

    // G. Fetch Sedes
    try {
        console.log("Cargando sección: Sedes...");
        const fetchRes = await fetchChartData('sedes');
        const processed = processChartData(fetchRes, false);

        sedesChart.setOption({
            xAxis: { data: processed.categories },
            series: getSeriesConfig(processed),
            tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: commonTooltipFormatter }
        }, { replaceMerge: ['series', 'xAxis'] });
    } catch (error) {
        console.error("Fallo en sección Sedes:", error);
    }

    // H. Fetch Jornada
    try {
        console.log("Cargando sección: Jornada...");
        const fetchRes = await fetchChartData('jornada');
        const processed = processChartData(fetchRes, false);

        // Update Total Evaluaciones KPI
        let totalEvaluaciones = processed.data1.reduce((sum, j) => sum + (j.total_evaluaciones || 0), 0);
        if (fetchRes.isComparing) {
            totalEvaluaciones += processed.data2.reduce((sum, j) => sum + (j.total_evaluaciones || 0), 0);
        }
        const contadorRegistros = document.getElementById('contador-registros');
        if (contadorRegistros) {
            contadorRegistros.innerText = totalEvaluaciones.toLocaleString('es-CO');
        }

        jornadaChart.setOption({
            xAxis: { data: processed.categories },
            series: getSeriesConfig(processed),
            tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: commonTooltipFormatter }
        }, { replaceMerge: ['series', 'xAxis'] });
    } catch (error) {
        console.error("Fallo en sección Jornada:", error);
    }

    // I. Fetch Rutas Transporte (Mapa)
    try {
        console.log("Cargando sección: Mapa de Rutas...");
        const mapaRes = await fetch(`${API_BASE}/rutas-transporte?semestre=${isComparing ? '2025-2' : semestre}`);
        const mapaRaw = await mapaRes.json();

        const nodosMap = new Map();
        mapaRaw.forEach(ruta => {
            if (ruta.origen && ruta.coords?.[0]) {
                if (!nodosMap.has(ruta.origen)) {
                    nodosMap.set(ruta.origen, { name: ruta.origen, value: ruta.coords[0], isCampus: false });
                }
            }
            if (ruta.destino && ruta.coords?.[1]) {
                if (!nodosMap.has(ruta.destino)) {
                    nodosMap.set(ruta.destino, { name: ruta.destino, value: ruta.coords[1], isCampus: true });
                }
            }
        });

        const scatterData = Array.from(nodosMap.values()).map(nodo => ({
            name: nodo.name,
            value: nodo.value,
            symbolSize: nodo.isCampus ? 15 : 8,
            itemStyle: {
                color: nodo.isCampus ? '#FF5722' : '#00B5E2',
                shadowBlur: 10,
                shadowColor: nodo.isCampus ? '#FF5722' : '#00B5E2'
            },
            label: { show: true, position: 'right', formatter: '{b}', color: '#E2E8F0', fontSize: 11, fontWeight: nodo.isCampus ? 'bold' : 'normal' }
        }));

        mapaChart.setOption({
            series: [{ data: mapaRaw }, { data: scatterData }]
        });
    } catch (error) {
        console.error("Fallo en sección Mapa de Rutas:", error);
    }

    // J. Fetch KPI Fantasmas
    try {
        console.log("Cargando sección: KPI Fantasmas...");
        cargarKPIFantasmas(isComparing ? '2025-2' : semestre);
    } catch (error) {
        console.error("Fallo en sección KPI Fantasmas:", error);
    }

    // Quitar estado de carga
    [heatmapChart, teachersChart, adaptacionChart, brechaChart, materiasChart, sedesChart, jornadaChart, mapaChart].forEach(c => c && c.hideLoading());
    console.log("--- Carga de datos finalizada ---");
    isFetching = false;
}

// Función dedicada para el Mapa de Calor (GeoJSON)
"""

content = content.replace(load_data_original, load_data_new)

# 3. Modify Event Listener for Semestre Buttons
btn_listener_orig = r'''    const botonesSemestre = document.querySelectorAll\('\.filter-bar button'\);\n    botonesSemestre\.forEach\(btn => \{\n        btn\.addEventListener\('click', \(e\) => \{\n            botonesSemestre\.forEach\(b => b\.classList\.remove\('active'\)\);\n            const botonClickeado = e\.currentTarget;\n            botonClickeado\.classList\.add\('active'\);\n            currentSemestre = botonClickeado\.getAttribute\('data-semester'\) \|\| botonClickeado\.innerText\.trim\(\);\n            \n            const titulo = document\.getElementById\('titulo-periodo'\);\n            if \(titulo\) \{\n                titulo\.innerText = `Resumen General · Periodo \$\{currentSemestre\}`;\n            \}\n            \n            if \(currentSemestre !== "Comparar"\) \{\n                actualizarDashboard\(\);\n            \}\n        \}\);\n    \}\);'''

btn_listener_new = """    const botonesSemestre = document.querySelectorAll('.filter-bar button');
    botonesSemestre.forEach(btn => {
        btn.addEventListener('click', (e) => {
            botonesSemestre.forEach(b => b.classList.remove('active'));
            const botonClickeado = e.currentTarget;
            botonClickeado.classList.add('active');
            
            const btnValue = botonClickeado.getAttribute('data-semester') || botonClickeado.innerText.trim();
            const titulo = document.getElementById('titulo-periodo');
            
            if (btnValue === "Comparar") {
                isComparing = true;
                if (titulo) titulo.innerText = `Resumen General · Comparativa 2025-1 vs 2025-2`;
            } else {
                isComparing = false;
                currentSemestre = btnValue;
                if (titulo) titulo.innerText = `Resumen General · Periodo ${currentSemestre}`;
            }
            actualizarDashboard();
        });
    });"""

content = re.sub(btn_listener_orig, btn_listener_new, content)

with open('static/main.js', 'w', encoding='utf-8') as f:
    f.write(content)

print("Update complete")
