// 1. Variables Globales de Estado y Gráficas
let heatmapChart, teachersChart, adaptacionChart, brechaChart, materiasChart, sedesChart, jornadaChart, mapaChart, chartMapaCalor;
let currentSemestre = '2025-2';
let currentMetrica = 'poblacion';
let geojsonLoaded = false;

const API_BASE = window.location.origin + '/api';
const days = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'];
const hours = ['06:00-08:00', '08:00-10:00', '10:00-12:00', '12:00-14:00', '14:00-16:00', '16:00-18:00', '18:00-20:00', '20:00-22:00'];

// 2. Función Centralizada de Actualización
function actualizarDashboard() {
    console.log("Actualizando dashboard para el semestre:", currentSemestre);
    loadData(currentSemestre);
    renderMapaCalor();
}

// 3. Función de Carga de Datos (Core)
async function loadData(semestre) {
    // Mostrar estado de carga visual en los charts
    if (heatmapChart) heatmapChart.showLoading();
    if (teachersChart) teachersChart.showLoading();
    if (adaptacionChart) adaptacionChart.showLoading();
    if (brechaChart) brechaChart.showLoading();
    if (materiasChart) materiasChart.showLoading();
    if (sedesChart) sedesChart.showLoading();
    if (jornadaChart) jornadaChart.showLoading();
    if (mapaChart) mapaChart.showLoading();

    try {
        // A. Fetch KPIs
        const kpiRes = await fetch(`${API_BASE}/kpis?semestre=${semestre}`);
        const kpiData = await kpiRes.json();

        document.getElementById('kpi-mortalidad').innerText = kpiData.mortalidad_global;
        document.getElementById('kpi-estudiantes').innerText = kpiData.total_estudiantes.toLocaleString('es-CO');
        document.getElementById('kpi-asignatura-nombre').innerText = kpiData.asignatura_critica.nombre;
        document.getElementById('kpi-asignatura-pct').innerText = kpiData.asignatura_critica.porcentaje + '% de reprobación';
        document.getElementById('page-title-text').innerText = `Resumen General · Periodo ${semestre}`;

        // B. Fetch Heatmap
        const heatmapRes = await fetch(`${API_BASE}/heatmap?semestre=${semestre}`);
        const heatmapRaw = await heatmapRes.json();
        const heatmapFormatted = heatmapRaw.map(item => {
            const x = days.indexOf(item.dia_nombre);
            const y = hours.indexOf(item.franja_horaria);
            return [x, y, item.mortalidad];
        }).filter(item => item[0] !== -1 && item[1] !== -1);
        heatmapChart.setOption({ series: [{ data: heatmapFormatted }] });

        // C. Fetch Docentes
        const materiaFilter = document.getElementById('materia-docente-filter').value;
        let teachersUrl = `${API_BASE}/teachers?semestre=${semestre}`;
        if (materiaFilter) teachersUrl += `&materia=${encodeURIComponent(materiaFilter)}`;
        const teachersRes = await fetch(teachersUrl);
        const teachersRaw = await teachersRes.json();
        teachersRaw.reverse();
        const teacherNames = teachersRaw.map(t => `${t.teacher_name}`);
        const teacherValues = teachersRaw.map(t => t.tasa_mortalidad);
        teachersChart.setOption({
            yAxis: { data: teacherNames },
            series: [{ data: teacherValues }],
            tooltip: {
                formatter: function (params) {
                    const p = Array.isArray(params) ? params[0] : params;
                    const original = teachersRaw[p.dataIndex];
                    const tasa = p.value;
                    const total = original.total_estudiantes;
                    const afectados = Math.round(tasa * total);
                    return `<strong>${original.teacher_name}</strong><br/>
                            Mortalidad: ${(tasa * 100).toFixed(1)}%<br/>
                            ⚠️ <b>${afectados}</b> reprobados de <b>${total}</b> evaluados`;
                }
            }
        });

        // D. Fetch Adaptacion
        const adaptacionRes = await fetch(`${API_BASE}/adaptacion?semestre=${semestre}`);
        let adaptacionRaw = await adaptacionRes.json();
        if (!adaptacionRaw || adaptacionRaw.length === 0) {
            adaptacionRaw = Array.from({ length: 10 }, (_, i) => ({ semestre: i + 1, mortalidad: 0.45 - (i * 0.03) }));
        }
        const semestresLabels = adaptacionRaw.map(item => 'Sem ' + item.semestre);
        const mortalidadesData = adaptacionRaw.map(item => (item.mortalidad * 100).toFixed(1));
        adaptacionChart.setOption({
            xAxis: { type: 'category', data: semestresLabels },
            series: [{ data: mortalidadesData }]
        });

        // E. Fetch Brecha de Género
        const brechaRes = await fetch(`${API_BASE}/brecha-ciencias?semestre=${semestre}`);
        const brechaRaw = await brechaRes.json();
        brechaChart.setOption({
            xAxis: { data: brechaRaw.map(item => item.sexo) },
            series: [{ data: brechaRaw.map(item => item.tasa_mortalidad) }],
            tooltip: {
                formatter: function (params) {
                    const p = Array.isArray(params) ? params[0] : params;
                    const original = brechaRaw[p.dataIndex];
                    const tasa = p.value;
                    const total = original.total_estudiantes;
                    const afectados = Math.round(tasa * total);
                    return `<strong>Género: ${original.sexo}</strong><br/>
                            Mortalidad: ${(tasa * 100).toFixed(1)}%<br/>
                            ⚠️ <b>${afectados}</b> reprobados de <b>${total}</b> evaluados`;
                }
            }
        });

        // F. Fetch Materias Filtro
        const materiasRes = await fetch(`${API_BASE}/materias-filtro?semestre=${semestre}`);
        const materiasRaw = await materiasRes.json();
        materiasRaw.reverse();
        materiasChart.setOption({
            yAxis: { data: materiasRaw.map(m => m.asignatura) },
            series: [{ data: materiasRaw.map(m => m.tasa_mortalidad) }],
            tooltip: {
                formatter: function (params) {
                    const p = Array.isArray(params) ? params[0] : params;
                    const original = materiasRaw[p.dataIndex];
                    const tasa = p.value;
                    const total = original.total_estudiantes;
                    const afectados = Math.round(tasa * total);
                    return `<strong>${original.asignatura}</strong><br/>
                            Mortalidad: ${(tasa * 100).toFixed(1)}%<br/>
                            ⚠️ <b>${afectados}</b> reprobados de <b>${total}</b> evaluados`;
                }
            }
        });

        // G. Fetch Sedes
        const sedesRes = await fetch(`${API_BASE}/sedes?semestre=${semestre}`);
        const sedesRaw = await sedesRes.json();
        sedesChart.setOption({
            xAxis: { data: sedesRaw.map(s => s.sede) },
            series: [{ data: sedesRaw.map(s => s.tasa_mortalidad) }],
            tooltip: {
                formatter: function (params) {
                    const p = Array.isArray(params) ? params[0] : params;
                    const original = sedesRaw[p.dataIndex];
                    const tasa = p.value;
                    const total = original.total_estudiantes;
                    const afectados = Math.round(tasa * total);
                    return `<strong>Sede: ${original.sede}</strong><br/>
                            Mortalidad: ${(tasa * 100).toFixed(1)}%<br/>
                            ⚠️ <b>${afectados}</b> reprobados de <b>${total}</b> evaluados`;
                }
            }
        });

        // H. Fetch Jornada
        const jornadaRes = await fetch(`${API_BASE}/jornada?semestre=${semestre}`);
        const jornadaRaw = await jornadaRes.json();
        jornadaChart.setOption({
            series: [{ data: jornadaRaw.map(j => ({ name: j.jornada, value: j.tasa_mortalidad, total: j.total_estudiantes })) }]
        });

        // I. Fetch Rutas Transporte (Mapa)
        const mapaRes = await fetch(`${API_BASE}/rutas-transporte?semestre=${semestre}`);
        const mapaRaw = await mapaRes.json();
        console.log("Datos del mapa:", mapaRaw);

        const nodosMap = new Map();
        mapaRaw.forEach(ruta => {
            // Registrar Origen (Comuna)
            if (!nodosMap.has(ruta.origen)) {
                nodosMap.set(ruta.origen, {
                    name: ruta.origen,
                    value: ruta.coords[0], // [lon, lat]
                    isCampus: false
                });
            }
            // Registrar Destino (Sede)
            if (!nodosMap.has(ruta.destino)) {
                nodosMap.set(ruta.destino, {
                    name: ruta.destino,
                    value: ruta.coords[1], // [lon, lat]
                    isCampus: true
                });
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
            label: {
                show: true,
                position: 'right',
                formatter: '{b}',
                color: '#E2E8F0',
                fontSize: 11,
                fontWeight: nodo.isCampus ? 'bold' : 'normal'
            }
        }));

        mapaChart.setOption({
            series: [
                { data: mapaRaw },
                { data: scatterData }
            ]
        });

    } catch (error) {
        console.error("Error al cargar los datos de la API:", error);
    } finally {
        [heatmapChart, teachersChart, adaptacionChart, brechaChart, materiasChart, sedesChart, jornadaChart, mapaChart].forEach(c => c && c.hideLoading());
    }
}

// Función dedicada para el Mapa de Calor (GeoJSON)
function renderMapaCalor() {
    const chartMapaCalor = echarts.getInstanceByDom(document.getElementById('chart-mapa-calor')) || echarts.init(document.getElementById('chart-mapa-calor'));

    chartMapaCalor.showLoading({ text: 'Cargando mapa de Medellín...' });

    // 1. Verificar si el mapa ya está registrado
    if (!echarts.getMap('medellin')) {
        fetch('./medellin.geojson')
            .then(response => {
                if (!response.ok) throw new Error("No se encontró medellin.geojson (Error 404)");
                return response.json();
            })
            .then(geojsonData => {
                // Imprimir en consola para descubrir la propiedad del nombre
                console.log("Propiedades del primer barrio:", geojsonData.features[0].properties);

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
    fetch(`/api/mapa-poligonos?semestre=${currentSemestre}&metrica=${currentMetrica}`)
        .then(res => res.json())
        .then(datosDelBackend => {
            chartInstance.hideLoading();
            chartInstance.setOption({
                tooltip: {
                    trigger: 'item',
                    formatter: '{b}<br/>Valor: {c}'
                },
                visualMap: {
                    left: 'right',
                    min: 0,
                    max: Math.max(...datosDelBackend.map(d => d.value)) || 100,
                    inRange: { color: ['#fee0d2', '#de2d26'] }, // Colores de calor
                    text: ['Alto', 'Bajo'],
                    calculable: true
                },
                series: [{
                    type: 'map',
                    map: 'medellin',
                    roam: true,
                    nameProperty: 'NOMBRE', // Cambiar a 'Name' o 'Barrio' si la consola lo indica
                    data: datosDelBackend
                }]
            });
        })
        .catch(err => {
            console.error("Error cargando datos del backend para el mapa:", err);
            chartInstance.hideLoading();
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
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, backgroundColor: 'rgba(15, 23, 42, 0.9)', textStyle: { color: '#fff' } },
        grid: { left: '3%', right: '10%', bottom: '3%', top: '5%', containLabel: true },
        xAxis: { type: 'value', max: 1, axisLabel: { formatter: v => Math.round(v * 100) + '%' } },
        yAxis: { type: 'category', data: [], axisLabel: { interval: 0, width: 150, overflow: 'truncate' } },
        series: [{ type: 'bar', data: [], itemStyle: { color: '#dc2626' }, label: { show: true, position: 'right', formatter: p => (p.value * 100).toFixed(1) + '%' }, emphasis: { focus: 'series' } }]
    });

    adaptacionChart.setOption({
        tooltip: { trigger: 'axis', backgroundColor: 'rgba(15, 23, 42, 0.9)', textStyle: { color: '#fff' } },
        grid: { left: '5%', right: '5%', bottom: '5%', top: '10%', containLabel: true },
        xAxis: { type: 'category', data: [] },
        yAxis: { type: 'value', axisLabel: { formatter: v => Math.round(v * 100) + '%' } },
        series: [{ type: 'line', smooth: true, symbolSize: 8, itemStyle: { color: '#00B5E2' }, lineStyle: { width: 3 }, label: { show: true, position: 'top', formatter: p => (p.value * 100).toFixed(1) + '%' }, emphasis: { focus: 'series' } }]
    });

    brechaChart.setOption({
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, backgroundColor: 'rgba(15, 23, 42, 0.9)', textStyle: { color: '#fff' } },
        xAxis: { type: 'category', data: [] },
        yAxis: { type: 'value', axisLabel: { formatter: v => Math.round(v * 100) + '%' } },
        legend: { show: true, bottom: 0, textStyle: { color: '#94a3b8' } },
        series: [{ type: 'bar', data: [], barWidth: '50%', itemStyle: { color: p => ['#8B5CF6', '#00B5E2', '#10B981', '#F59E0B'][p.dataIndex % 4] }, label: { show: true, position: 'top', formatter: p => (p.value * 100).toFixed(1) + '%' }, emphasis: { focus: 'series' } }]
    });

    materiasChart.setOption({
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, backgroundColor: 'rgba(15, 23, 42, 0.9)', textStyle: { color: '#fff' } },
        xAxis: { type: 'value', max: 1, axisLabel: { formatter: v => Math.round(v * 100) + '%' } },
        yAxis: { type: 'category', data: [] },
        series: [{ type: 'bar', data: [], itemStyle: { color: '#dc2626' }, label: { show: true, position: 'right', formatter: p => (p.value * 100).toFixed(1) + '%' }, emphasis: { focus: 'series' } }]
    });

    sedesChart.setOption({
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, backgroundColor: 'rgba(15, 23, 42, 0.9)', textStyle: { color: '#fff' } },
        xAxis: { type: 'category', data: [], axisLabel: { rotate: 30, interval: 0 } },
        yAxis: { type: 'value', max: 1, axisLabel: { formatter: v => Math.round(v * 100) + '%' } },
        series: [{ type: 'bar', data: [], itemStyle: { color: '#7C3AED' }, label: { show: true, position: 'top', formatter: p => (p.value * 100).toFixed(1) + '%' }, emphasis: { focus: 'series' } }]
    });

    jornadaChart.setOption({
        tooltip: { trigger: 'item', formatter: p => `<strong>${p.name}</strong><br/>Mortalidad: ${(p.value * 100).toFixed(1)}%<br/>Total: ${p.data.total}` },
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
                type: 'inside', // Scroll para zoom
                xAxisIndex: 0,
                yAxisIndex: 0,
                zoomOnMouseWheel: true,
                moveOnMouseMove: true,
                moveOnMouseWheel: false
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
        [heatmapChart, teachersChart, adaptacionChart, brechaChart, materiasChart, sedesChart, jornadaChart, mapaChart, chartMapaCalor].forEach(c => c && c.resize());
    });

    // D. Event Listeners para Botones de Semestre
    const botonesSemestre = document.querySelectorAll('.filter-bar button');
    botonesSemestre.forEach(btn => {
        btn.addEventListener('click', (e) => {
            botonesSemestre.forEach(b => b.classList.remove('active'));
            const botonClickeado = e.currentTarget;
            botonClickeado.classList.add('active');
            currentSemestre = botonClickeado.getAttribute('data-semestre') || botonClickeado.innerText.trim();
            if (currentSemestre !== "Comparar") {
                actualizarDashboard();
            }
        });
    });

    // E. Filtro de Docentes por Materia
    const selectDocentes = document.getElementById('materia-docente-filter');
    selectDocentes.addEventListener('change', () => actualizarDashboard());

    // Event Listener para el Filtro del Mapa Coroplético
    const selectMapaMetrica = document.getElementById('mapa-metrica-filter');
    selectMapaMetrica.addEventListener('change', (e) => {
        currentMetrica = e.target.value;
        renderMapaCalor();
    });

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
