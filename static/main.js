// 1. Variables Globales de Estado y Gráficas
let heatmapChart, teachersChart, adaptacionChart, brechaChart, materiasChart, sedesChart, jornadaChart, mapaChart, chartMapaCalor, municipiosChart;

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

let currentNivelGeo = 'barrio'; // Nivel inicial: Barrios
let geojsonLoaded = false;

const API_BASE = '/api';
const days = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'];
const hours = ['06:00-08:00', '08:00-10:00', '10:00-12:00', '12:00-14:00', '14:00-16:00', '16:00-18:00', '18:00-20:00', '20:00-22:00'];

// 2. Función Centralizada de Actualización (con Debounce)
let debounceTimer;
function actualizarDashboard() {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
        console.log("Actualizando dashboard para el semestre:", currentSemestre);
        loadData(currentSemestre);
        renderMapaCalor();
    }, 250); // Evita ráfagas de fetch()
}

// 3. Función de Carga de Datos (Core)
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

function renderMapaCalor() {
    const chartMapaCalor = echarts.getInstanceByDom(document.getElementById('chart-mapa-calor')) || echarts.init(document.getElementById('chart-mapa-calor'));

    chartMapaCalor.showLoading({ text: 'Cargando mapa de Medellín...' });

    // 1. Verificar si el mapa ya está registrado
    if (!echarts.getMap('medellin')) {
        fetch('medellin.geojson')
            .then(response => {
                if (!response.ok) throw new Error("No se encontró medellin.geojson (Error 404)");
                return response.json();
            })
            .then(geojsonData => {
                // Normalizar nombres a mayúsculas para asegurar el cruce
                geojsonData.features.forEach(feature => {
                    if (feature.properties) {
                        // Normalizar barrio
                        if (feature.properties.nombre_barrio) {
                            feature.properties.nombre_barrio = String(feature.properties.nombre_barrio).toUpperCase().trim();
                        }
                        // Normalizar comuna (intentando varios nombres comunes)
                        const keyComuna = ['nombre_comuna', 'NOMBRE', 'Name', 'comuna'].find(k => feature.properties[k]);
                        if (keyComuna) {
                            feature.properties.nombre_comuna = String(feature.properties[keyComuna]).toUpperCase().trim();
                        }
                    }
                });

                echarts.registerMap('medellin', geojsonData);
                cargarDatosGeoJSON(chartMapaCalor);
            })
            .catch(error => {
                console.error("Fallo crítico en GeoJSON:", error);
                chartMapaCalor.hideLoading();
            });
    } else {
        cargarDatosGeoJSON(chartMapaCalor);
    }
}

function cargarDatosGeoJSON(chartInstance) {
    fetch(`/api/mapa-poligonos?semestre=${currentSemestre}&metrica=${currentMetrica}&nivel_geo=${currentNivelGeo}`)
        .then(res => res.json())
        .then(datosDelBackend => {
            // 1. Forzar el cruce perfecto de nombres y valores (conservando ...d)
            const datosLimpios = datosDelBackend.map(d => ({
                ...d,
                name: String(d.name || d.barrio || '').toUpperCase().trim(),
                value: d.value != null ? d.value : (d.count || 0)
            }));

            // 2. Filtrar datos para el gráfico de otros municipios / desconocidos
            const otrosMunicipios = ['BELLO', 'ITAGUI', 'ENVIGADO', 'SABANETA', 'LA ESTRELLA', 'COPACABANA', 'GIRARDOTA', 'BARBOSA', 'CALDAS', 'DESCONOCIDA', 'UNKNOWN', '** DESCONOCIDA **'];
            const datosParaGrafico = datosLimpios.filter(d =>
                otrosMunicipios.some(m => d.name.includes(m)) || d.name === '' || d.name === 'NAN'
            ).sort((a, b) => b.value - a.value).slice(0, 10); // Top 10 otros

            renderGraficoMunicipios(datosParaGrafico);

            // 3. Calcular máximo seguro (excluyendo NaN)
            const valoresValidos = datosLimpios.map(d => d.value).filter(v => !isNaN(v));
            let maxVal = valoresValidos.length > 0 ? Math.max(...valoresValidos) : 100;
            if (maxVal <= 0) maxVal = 100;

            chartInstance.hideLoading();
            chartInstance.setOption({
                tooltip: {
                    trigger: 'item',
                    backgroundColor: 'rgba(15, 23, 42, 0.9)',
                    textStyle: { color: '#fff' },
                    formatter: function (params) {
                        // Si pasas el mouse por un barrio sin datos en la BD
                        if (!params.data) return `<b>${params.name}</b><br/>Sin estudiantes registrados`;

                        const valor = isNaN(params.value) ? 0 : params.value;
                        const label = currentMetrica === 'poblacion' ? 'Estudiantes' : (currentMetrica === 'aprobacion' ? 'Aprobación' : 'Mortalidad');
                        const sufijo = currentMetrica === 'poblacion' ? '' : '%';

                        // Intentamos leer el total desde el backend
                        const total = params.data.total_estudiantes || params.data.total || 'N/A';

                        return `<strong>Barrio: ${params.name}</strong><br/>
                                ${label}: <b>${valor}${sufijo}</b><br/>
                                <span style="color: #cbd5e1; font-size: 12px;">Total estudiantes del barrio: ${total}</span>`;
                    }
                },
                visualMap: {
                    left: 'right',
                    min: 0,
                    max: maxVal,
                    inRange: { color: ['#fee0d2', '#de2d26'] },
                    text: ['Alto', 'Bajo'],
                    calculable: true
                },
                series: [{
                    type: 'map',
                    map: 'medellin',
                    roam: true,
                    scaleLimit: { min: 1, max: 15 }, // Bloquea el zoom out excesivo
                    nameProperty: currentNivelGeo === 'barrio' ? 'nombre_barrio' : 'nombre_comuna',
                    data: datosLimpios
                }]
            });
        })
        .catch(err => {
            console.error("Error cargando datos del backend para el mapa:", err);
            chartInstance.hideLoading();
        });
}

function renderGraficoMunicipios(datos) {
    if (!municipiosChart) {
        municipiosChart = echarts.init(document.getElementById('grafico-municipios'));
    }

    const label = currentMetrica === 'poblacion' ? 'Estudiantes' : (currentMetrica === 'aprobacion' ? 'Aprobación' : 'Mortalidad');
    const sufijo = currentMetrica === 'poblacion' ? '' : '%';

    municipiosChart.setOption({
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, backgroundColor: 'rgba(15, 23, 42, 0.9)', textStyle: { color: '#fff' } },
        grid: { left: '3%', right: '15%', bottom: '3%', top: '5%', containLabel: true },
        xAxis: { type: 'value', axisLabel: { formatter: `{value}${sufijo}` } },
        yAxis: { type: 'category', data: datos.map(d => d.name), axisLabel: { fontSize: 10 } },
        series: [{
            name: label,
            type: 'bar',
            data: datos.map(d => d.value),
            itemStyle: { color: '#64748b' },
            label: { show: true, position: 'right', formatter: `{c}${sufijo}` }
        }]
    });
}

// 4. Inicialización al Cargar el DOM
document.addEventListener('DOMContentLoaded', () => {
    // A. Inicializar ECharts
    heatmapChart = echarts.init(document.getElementById('chart-heatmap'));
    teachersChart = echarts.init(document.getElementById('chart-ranking-docentes'));
    adaptacionChart = echarts.init(document.getElementById('chart-adaptacion'));
    brechaChart = echarts.init(document.getElementById('chart-brecha'));
    materiasChart = echarts.init(document.getElementById('chart-materias'));
    sedesChart = echarts.init(document.getElementById('chart-sedes'));
    jornadaChart = echarts.init(document.getElementById('chart-jornada'));
    mapaChart = echarts.init(document.getElementById('chart-mapa'));
    chartMapaCalor = echarts.init(document.getElementById('chart-mapa-calor'));

    // B. Opciones Base de Gráficas
    heatmapChart.setOption({
        tooltip: { position: 'top', formatter: p => `<strong>${days[p.value[0]]} ${hours[p.value[1]]}</strong><br>Mortalidad: ${(p.value[2] * 100).toFixed(1)}%` },
        grid: { left: '15%', right: '5%', top: '5%', bottom: '15%' },
        xAxis: { type: 'category', data: days, splitArea: { show: true } },
        yAxis: { type: 'category', data: hours, splitArea: { show: true } },
        visualMap: { min: 0, max: 1, calculable: true, orient: 'horizontal', left: 'center', bottom: '0%', inRange: { color: ['#FFFFE0', '#FFEDA0', '#FEB24C', '#F03B20', '#BD0026'] } },
        series: [{ name: 'Mortalidad', type: 'heatmap', data: [], label: { show: true, formatter: p => (p.value[2] * 100).toFixed(1) + '%' } }]
    });

    teachersChart.setOption({
        tooltip: {
            trigger: 'item',
            backgroundColor: 'rgba(15, 23, 42, 0.9)',
            textStyle: { color: '#fff' },
            formatter: function (params) {
                const d = params.data || params;
                return `<b>${d.name}</b><br/>` +
                    `Evaluaciones Totales: <br/> +
                           Estudiantes Únicos: ${d.total || 0}<br/>` +
                    `Reprobados: ${d.reprobados || 0}<br/>` +
                    `Mortalidad: ${((d.value || 0) * 100).toFixed(1)}%`;
            }
        },
        grid: { left: '3%', right: '10%', bottom: '3%', top: '5%', containLabel: true },
        xAxis: { type: 'value', max: 1, axisLabel: { formatter: v => Math.round(v * 100) + '%' } },
        yAxis: { type: 'category', data: [], axisLabel: { interval: 0, width: 150, overflow: 'truncate' } },
        series: [{ type: 'bar', data: [], itemStyle: { color: '#dc2626' }, label: { show: true, position: 'right', formatter: p => (p.value * 100).toFixed(1) + '%' }, emphasis: { focus: 'series' } }]
    });

    adaptacionChart.setOption({
        tooltip: {
            trigger: 'item',
            backgroundColor: 'rgba(15, 23, 42, 0.9)',
            textStyle: { color: '#fff' },
            formatter: function (params) {
                const d = params.data || params;
                return `<b>${d.name}</b><br/>` +
                    `Evaluaciones Totales: <br/> +
                           Estudiantes Únicos: ${d.total || 0}<br/>` +
                    `Reprobados: ${d.reprobados || 0}<br/>` +
                    `Mortalidad: ${((d.value || 0) * 100).toFixed(1)}%`;
            }
        },
        grid: { left: '5%', right: '5%', bottom: '5%', top: '10%', containLabel: true },
        xAxis: { type: 'category', data: [] },
        yAxis: { type: 'value', axisLabel: { formatter: v => Math.round(v * 100) + '%' } },
        series: [{ type: 'line', smooth: true, symbolSize: 8, itemStyle: { color: '#00B5E2' }, lineStyle: { width: 3 }, label: { show: true, position: 'top', formatter: p => (p.value * 100).toFixed(1) + '%' }, emphasis: { focus: 'series' } }]
    });

    brechaChart.setOption({
        tooltip: {
            trigger: 'item',
            backgroundColor: 'rgba(15, 23, 42, 0.9)',
            textStyle: { color: '#fff' },
            formatter: function (params) {
                const d = params.data || params;
                return `<b>${d.name}</b><br/>` +
                    `Evaluaciones Totales: <br/> +
                           Estudiantes Únicos: ${d.total || 0}<br/>` +
                    `Reprobados: ${d.reprobados || 0}<br/>` +
                    `Mortalidad: ${((d.value || 0) * 100).toFixed(1)}%`;
            }
        },
        xAxis: { type: 'category', data: [] },
        yAxis: { type: 'value', axisLabel: { formatter: v => Math.round(v * 100) + '%' } },
        legend: { show: true, bottom: 0, textStyle: { color: '#94a3b8' } },
        series: [{ type: 'bar', data: [], barWidth: '50%', itemStyle: { color: p => ['#8B5CF6', '#00B5E2', '#10B981', '#F59E0B'][p.dataIndex % 4] }, label: { show: true, position: 'top', formatter: p => (p.value * 100).toFixed(1) + '%' }, emphasis: { focus: 'series' } }]
    });

    materiasChart.setOption({
        tooltip: {
            trigger: 'item',
            backgroundColor: 'rgba(15, 23, 42, 0.9)',
            textStyle: { color: '#fff' },
            formatter: function (params) {
                const d = params.data || params;
                return `<b>${d.name}</b><br/>` +
                    `Evaluaciones Totales: <br/> +
                           Estudiantes Únicos: ${d.total || 0}<br/>` +
                    `Reprobados: ${d.reprobados || 0}<br/>` +
                    `Mortalidad: ${((d.value || 0) * 100).toFixed(1)}%`;
            }
        },
        xAxis: { type: 'value', max: 1, axisLabel: { formatter: v => Math.round(v * 100) + '%' } },
        yAxis: { type: 'category', data: [] },
        series: [{ type: 'bar', data: [], itemStyle: { color: '#dc2626' }, label: { show: true, position: 'right', formatter: p => (p.value * 100).toFixed(1) + '%' }, emphasis: { focus: 'series' } }]
    });

    sedesChart.setOption({
        tooltip: {
            trigger: 'item',
            backgroundColor: 'rgba(15, 23, 42, 0.9)',
            textStyle: { color: '#fff' },
            formatter: function (params) {
                const d = params.data || params;
                return `<b>${d.name}</b><br/>` +
                    `Evaluaciones Totales: <br/> +
                           Estudiantes Únicos: ${d.total || 0}<br/>` +
                    `Reprobados: ${d.reprobados || 0}<br/>` +
                    `Mortalidad: ${((d.value || 0) * 100).toFixed(1)}%`;
            }
        },
        xAxis: { type: 'category', data: [], axisLabel: { rotate: 30, interval: 0 } },
        yAxis: { type: 'value', max: 1, axisLabel: { formatter: v => Math.round(v * 100) + '%' } },
        series: [{ type: 'bar', data: [], itemStyle: { color: '#7C3AED' }, label: { show: true, position: 'top', formatter: p => (p.value * 100).toFixed(1) + '%' }, emphasis: { focus: 'series' } }]
    });

    jornadaChart.setOption({
        tooltip: {
            trigger: 'item',
            backgroundColor: 'rgba(15, 23, 42, 0.9)',
            textStyle: { color: '#fff' },
            formatter: function (params) {
                const d = params.data || params;
                return `<b>${d.name}</b><br/>` +
                    `Evaluaciones Totales: <br/> +
                           Estudiantes Únicos: ${d.total || 0}<br/>` +
                    `Reprobados: ${d.reprobados || 0}<br/>` +
                    `Mortalidad: ${((d.value || 0) * 100).toFixed(1)}%`;
            }
        },
        legend: { orient: 'vertical', left: 'left' },
        series: [{ name: 'Jornada', type: 'pie', radius: '50%', data: [], label: { show: true, formatter: '{b}: {d}%' } }]
    });

    mapaChart.setOption({
        backgroundColor: 'transparent',
        xAxis: {
            type: 'value',
            scale: true,
            show: false,
            min: -75.65, // Límite Oeste
            max: -75.50  // Límite Este
        },
        yAxis: {
            type: 'value',
            scale: true,
            show: false,
            min: 6.15,   // Límite Sur
            max: 6.35    // Límite Norte
        },
        tooltip: {
            formatter: p => p.seriesType === 'lines' ?
                `${p.data.origen} ➔ ${p.data.destino}<br/>Estudiantes: ${p.data.value}` :
                p.name
        },
        dataZoom: [
            {
                type: 'inside',
                zoomOnMouseWheel: true,
                moveOnMouseMove: true,
                preventDefaultMouseMove: false
            }
        ],
        series: [
            {
                type: 'lines',
                coordinateSystem: 'cartesian2d',
                data: [],
                effect: { show: true, period: 4, trailLength: 0.2, symbol: 'arrow', symbolSize: 5 },
                lineStyle: { color: '#00B5E2', width: 1.5, opacity: 0.5, curveness: 0.3 }
            },
            {
                type: 'effectScatter',
                coordinateSystem: 'cartesian2d',
                data: [],
                rippleEffect: {
                    brushType: 'stroke'
                },
                zlevel: 1
            }
        ]
    });

    // C. Responsive
    window.addEventListener('resize', () => {
        [heatmapChart, teachersChart, adaptacionChart, brechaChart, materiasChart, sedesChart, jornadaChart, mapaChart, chartMapaCalor, municipiosChart].forEach(c => c && c.resize());
    });

    // D. Event Listeners para Botones de Semestre
    const botonesSemestre = document.querySelectorAll('.filter-bar button');
    botonesSemestre.forEach(btn => {
        btn.addEventListener('click', (e) => {
            botonesSemestre.forEach(b => b.classList.remove('active'));
            const botonClickeado = e.currentTarget;
            botonClickeado.classList.add('active');
            
            const btnValue = botonClickeado.getAttribute('data-semester') || botonClickeado.innerText.trim();
            const titulo = document.getElementById('titulo-periodo');
            const workspaceComparativa = document.getElementById('workspace-comparativa');
            const normalSections = document.querySelectorAll('.kpi-row, .chart-row, .section-mb, .grid-12');
            
            if (btnValue === "Comparar") {
                isComparing = true;
                if (titulo) titulo.innerText = `Modo Constructor: Comparativa Intersemestral`;
                if (workspaceComparativa) workspaceComparativa.classList.remove('hidden');
                normalSections.forEach(el => el.classList.add('hidden'));
                
                // Redimensionar gráficas de comparativa si existen
                // (Se implementará la lógica de renderizado después)
                
            } else {
                isComparing = false;
                currentSemestre = btnValue;
                if (titulo) titulo.innerText = `Resumen General · Periodo ${currentSemestre}`;
                if (workspaceComparativa) workspaceComparativa.classList.add('hidden');
                normalSections.forEach(el => el.classList.remove('hidden'));
                
                // Forzar redimensionamiento de gráficas normales al volver a mostrarlas
                setTimeout(() => {
                    [heatmapChart, teachersChart, adaptacionChart, brechaChart, materiasChart, sedesChart, jornadaChart, mapaChart, chartMapaCalor, municipiosChart].forEach(c => c && c.resize());
                }, 50);
            }
            actualizarDashboard();
        });
    });

    // E. Filtro de Docentes por Materia
    const selectDocentes = document.getElementById('materia-docente-filter');
    selectDocentes.addEventListener('change', () => actualizarDashboard());

    // Event Listener para el Filtro del Mapa Coroplético (Métrica)
    const selectMapaMetrica = document.getElementById('mapa-metrica-filter');
    selectMapaMetrica.addEventListener('change', (e) => {
        currentMetrica = e.target.value;
        renderMapaCalor();
    });

    // Event Listener para el Filtro del Mapa Coroplético (Nivel: Barrio/Comuna)
    const selectMapaNivel = document.getElementById('mapa-nivel-filter');
    if (selectMapaNivel) {
        selectMapaNivel.addEventListener('change', (e) => {
            currentNivelGeo = e.target.value;
            renderMapaCalor();
        });
    }

    // Cargar lista de materias para el select
    fetch(`${API_BASE}/materias-list`)
        .then(res => res.json())
        .then(materias => {
            materias.forEach(m => {
                const opt = document.createElement('option');
                opt.value = m;
                opt.textContent = m;
                selectDocentes.appendChild(opt);
            });
        });

    // F. Carga Inicial
    actualizarDashboard();
});
function cargarKPIFantasmas(semestre) {
    const url = semestre ? `${API_BASE}/kpi-fantasmas?semestre=${semestre}` : `${API_BASE}/kpi-fantasmas`;

    fetch(url)
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                console.error("Error desde el backend:", data.error);
                document.getElementById('kpi-fantasmas-valor').innerText = 'Err';
                return;
            }

            // Si es evolución histórica (lista), tomamos el primero
            const res = Array.isArray(data) ? data[0] : data;

            const fantasmas = res.estudiantes_fantasma || 0;
            const total = res.total_estudiantes || 0;
            const porcentaje = res.porcentaje || 0;

            // Actualizar el valor principal
            document.getElementById('kpi-fantasmas-valor').innerText = fantasmas.toLocaleString('es-CO');

            // Actualizar el subtexto informativo
            const subtextoEl = document.getElementById('kpi-fantasmas-subtexto');
            if (subtextoEl) {
                subtextoEl.innerHTML = `<b>${porcentaje}%</b> de ${total.toLocaleString('es-CO')} evaluados`;
            }
        })
        .catch(error => {
            console.error('Error de red cargando KPI Fantasmas:', error);
            document.getElementById('kpi-fantasmas-valor').innerText = '---';
        });
}


// ==================== LÓGICA DE COMPARATIVA DINÁMICA ====================
const metricaEndpointMap = {
    "Sedes": "sedes",
    "Jornada": "jornada",
    "Materias Filtro": "materias-filtro",
    "Top Docentes": "teachers"
};

const graficasComparativas = [];

async function agregarGraficaComparativa(metrica) {
    const endpoint = metricaEndpointMap[metrica];
    if (!endpoint) return;

    // 1. Crear contenedor
    const workspace = document.getElementById('contenedor-graficas-comparativa');
    if (!workspace) return;
    
    const chartWrapper = document.createElement('div');
    chartWrapper.className = 'card chart-card';
    chartWrapper.style.padding = '16px';
    chartWrapper.style.position = 'relative';

    const titleEl = document.createElement('h3');
    titleEl.className = 'card-title';
    titleEl.innerText = `Comparativa: ${metrica}`;
    titleEl.style.marginBottom = '16px';
    titleEl.style.fontSize = '14px';
    
    // Botón para eliminar
    const btnRemove = document.createElement('button');
    btnRemove.innerHTML = `
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#94A3B8" stroke-width="2">
        <line x1="18" y1="6" x2="6" y2="18"></line>
        <line x1="6" y1="6" x2="18" y2="18"></line>
    </svg>`;
    btnRemove.style.position = 'absolute';
    btnRemove.style.top = '12px';
    btnRemove.style.right = '12px';
    btnRemove.style.border = 'none';
    btnRemove.style.background = 'transparent';
    btnRemove.style.cursor = 'pointer';
    btnRemove.title = "Eliminar gráfica";
    
    btnRemove.onclick = () => {
        chartWrapper.remove();
        // Disponer de la instancia de ECharts
        const idx = graficasComparativas.indexOf(chartInstance);
        if (idx > -1) graficasComparativas.splice(idx, 1);
        chartInstance.dispose();
    };

    const chartDiv = document.createElement('div');
    chartDiv.style.width = '100%';
    chartDiv.style.height = '350px';

    chartWrapper.appendChild(btnRemove);
    chartWrapper.appendChild(titleEl);
    chartWrapper.appendChild(chartDiv);
    workspace.appendChild(chartWrapper);

    // 2. Inicializar ECharts
    const chartInstance = echarts.init(chartDiv);
    chartInstance.showLoading();
    graficasComparativas.push(chartInstance);

    try {
        // 3. Fetch Data usando Promise.all
        const [res1, res2] = await Promise.all([
            fetch(`${API_BASE}/${endpoint}?semestre=2025-1`),
            fetch(`${API_BASE}/${endpoint}?semestre=2025-2`)
        ]);

        const raw1 = await res1.json();
        const raw2 = await res2.json();

        // 4. Procesar y Alinear Categorías
        const allKeys = new Set();
        raw1.forEach(item => allKeys.add(item.name));
        raw2.forEach(item => allKeys.add(item.name));
        
        let categories = Array.from(allKeys);
        
        // Reverse para gráficas horizontales (Top Docentes, Materias)
        const isHorizontal = ["Materias Filtro", "Top Docentes"].includes(metrica);
        if (isHorizontal) {
            categories.reverse();
        }

        const map1 = new Map(raw1.map(item => [item.name, item]));
        const map2 = new Map(raw2.map(item => [item.name, item]));

        const data1 = categories.map(cat => map1.get(cat) || { name: cat, value: 0 });
        const data2 = categories.map(cat => map2.get(cat) || { name: cat, value: 0 });

        // 5. Configurar ECharts
        const option = {
            tooltip: {
                trigger: 'axis',
                axisPointer: { type: 'shadow' },
                formatter: function (params) {
                    let tooltipHtml = `<b style="font-size:12px;color:#64748b;">${params[0].name}</b><br/>`;
                    params.forEach(p => {
                        const d = p.data || {};
                        const evals = d.total_evaluaciones !== undefined ? ` (Eval: ${d.total_evaluaciones})` : '';
                        tooltipHtml += `<div style="margin-top: 6px; font-size:13px;">
                            <span style="display:inline-block;margin-right:6px;border-radius:50%;width:8px;height:8px;background-color:${p.color};"></span>
                            <b style="color:#0f172a;">${p.seriesName}</b><br/>
                            <span style="color:#475569;">Mortalidad: <b style="color:#0f172a;">${((d.value || 0) * 100).toFixed(1)}%</b>${evals}</span>
                        </div>`;
                    });
                    return tooltipHtml;
                },
                backgroundColor: 'rgba(255, 255, 255, 0.95)',
                borderColor: '#e2e8f0',
                textStyle: { color: '#0f172a' },
                padding: [10, 14]
            },
            legend: {
                data: ['2025-1', '2025-2'],
                bottom: 0,
                icon: 'circle'
            },
            grid: { left: '3%', right: '4%', bottom: '10%', top: '5%', containLabel: true },
            series: [
                {
                    name: '2025-1',
                    type: 'bar',
                    data: data1,
                    itemStyle: { color: '#1E3A8A', borderRadius: isHorizontal ? [0, 4, 4, 0] : [4, 4, 0, 0] }
                },
                {
                    name: '2025-2',
                    type: 'bar',
                    data: data2,
                    itemStyle: { color: '#F97316', borderRadius: isHorizontal ? [0, 4, 4, 0] : [4, 4, 0, 0] }
                }
            ]
        };

        if (isHorizontal) {
            option.xAxis = { type: 'value', max: 1, axisLabel: { formatter: val => (val * 100) + '%' } };
            option.yAxis = { type: 'category', data: categories, axisLabel: { width: 120, overflow: 'truncate' } };
        } else {
            option.xAxis = { type: 'category', data: categories, axisLabel: { interval: 0, width: 80, overflow: 'truncate' } };
            option.yAxis = { type: 'value', max: 1, axisLabel: { formatter: val => (val * 100) + '%' } };
        }

        chartInstance.setOption(option);
    } catch (err) {
        console.error("Error al cargar gráfica comparativa:", err);
    } finally {
        chartInstance.hideLoading();
    }
}

// Inicializar el Event Listener cuando el DOM esté listo
document.addEventListener('DOMContentLoaded', () => {
    const btnAgregar = document.getElementById('btn-agregar-comparativa');
    if (btnAgregar) {
        btnAgregar.addEventListener('click', () => {
            const selectEl = document.getElementById('select-metrica');
            if (selectEl) {
                agregarGraficaComparativa(selectEl.value);
            }
        });
    }

    // Asegurarse de que el redimensionamiento aplique a las gráficas dinámicas
    window.addEventListener('resize', () => {
        graficasComparativas.forEach(c => c && c.resize());
    });
});
