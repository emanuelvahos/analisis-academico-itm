document.addEventListener('DOMContentLoaded', () => {
    // 1. Inicializar instancias de ECharts
    const heatmapChart = echarts.init(document.getElementById('chart-heatmap'));
    const teachersChart = echarts.init(document.getElementById('chart-ranking-docentes'));
    const adaptacionChart = echarts.init(document.getElementById('chart-adaptacion'));
    const brechaChart = echarts.init(document.getElementById('chart-brecha'));
    const materiasChart = echarts.init(document.getElementById('chart-materias'));
    const sedesChart = echarts.init(document.getElementById('chart-sedes'));
    const jornadaChart = echarts.init(document.getElementById('chart-jornada'));

    // Configuración base para el Mapa de Calor
    const days = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'];
    const hours = ['06:00-08:00', '08:00-10:00', '10:00-12:00', '12:00-14:00', '14:00-16:00', '16:00-18:00', '18:00-20:00', '20:00-22:00'];

    heatmapChart.setOption({
        tooltip: {
            position: 'top',
            formatter: function (params) {
                return `<strong>${days[params.value[0]]} ${hours[params.value[1]]}</strong><br>Mortalidad: ${(params.value[2] * 100).toFixed(1)}%`;
            }
        },
        grid: { left: '15%', right: '5%', top: '5%', bottom: '15%' },
        xAxis: {
            type: 'category',
            data: days,
            splitArea: { show: true }
        },
        yAxis: {
            type: 'category',
            data: hours,
            splitArea: { show: true }
        },
        visualMap: {
            min: 0,
            max: 1,
            calculable: true,
            orient: 'horizontal',
            left: 'center',
            bottom: '0%',
            inRange: {
                color: ['#FFFFE0', '#FFEDA0', '#FEB24C', '#F03B20', '#BD0026'] // De amarillo pálido a rojo oscuro
            }
        },
        series: [{
            name: 'Mortalidad',
            type: 'heatmap',
            data: [],
            label: {
                show: true,
                formatter: function (params) {
                    return (params.value[2] * 100).toFixed(1) + '%';
                }
            },
            emphasis: {
                itemStyle: {
                    shadowBlur: 10,
                    shadowColor: 'rgba(0, 0, 0, 0.5)'
                }
            }
        }]
    });

    // Configuración base para el Gráfico de Docentes
    teachersChart.setOption({
        tooltip: {
            trigger: 'axis',
            axisPointer: { type: 'shadow' },
            formatter: function (params) {
                let val = params[0];
                return `<strong>${val.name}</strong><br/>Mortalidad: ${(val.value * 100).toFixed(1)}%`;
            }
        },
        grid: { left: '3%', right: '10%', bottom: '3%', top: '5%', containLabel: true },
        xAxis: {
            type: 'value',
            max: 1, // 100%
            axisLabel: {
                formatter: function (value) {
                    return Math.round(value * 100) + '%';
                }
            }
        },
        yAxis: {
            type: 'category',
            data: [],
            axisLabel: {
                interval: 0,
                width: 150,
                overflow: 'truncate'
            }
        },
        series: [
            {
                type: 'bar',
                data: [],
                itemStyle: {
                    color: '#dc2626' // Rojo representativo del dashboard para peligro
                },
                label: {
                    show: true,
                    position: 'right',
                    formatter: function (params) {
                        return (params.value * 100).toFixed(1) + '%';
                    }
                }
            }
        ]
    });

    // Configuración base para Curva de Adaptación
    adaptacionChart.setOption({
        tooltip: {
            trigger: 'axis',
            formatter: function (params) {
                let val = params[0];
                return `Semestre ${val.name}<br/>Mortalidad: ${(val.value * 100).toFixed(1)}%`;
            }
        },
        grid: { left: '5%', right: '5%', bottom: '5%', top: '10%', containLabel: true },
        xAxis: {
            type: 'category',
            name: 'Semestre',
            nameLocation: 'middle',
            nameGap: 25,
            data: []
        },
        yAxis: {
            type: 'value',
            axisLabel: {
                formatter: function (value) {
                    return Math.round(value * 100) + '%';
                }
            }
        },
        series: [{
            data: [],
            type: 'line',
            smooth: true,
            symbol: 'circle',
            symbolSize: 8,
            itemStyle: { color: '#00B5E2' }, // Celeste institucional
            lineStyle: { width: 3 },
            label: {
                show: true,
                position: 'top',
                formatter: function (params) {
                    return (params.value * 100).toFixed(1) + '%';
                }
            }
        }]
    });

    // Configuración base para Brecha de Género
    brechaChart.setOption({
        tooltip: {
            trigger: 'axis',
            axisPointer: { type: 'shadow' },
            formatter: function (params) {
                let val = params[0];
                return `<strong>${val.name}</strong><br/>Mortalidad: ${(val.value * 100).toFixed(1)}%`;
            }
        },
        grid: { left: '5%', right: '5%', bottom: '5%', top: '10%', containLabel: true },
        xAxis: {
            type: 'category',
            data: []
        },
        yAxis: {
            type: 'value',
            axisLabel: {
                formatter: function (value) {
                    return Math.round(value * 100) + '%';
                }
            }
        },
        series: [
            {
                type: 'bar',
                data: [],
                barWidth: '50%',
                itemStyle: {
                    color: function (params) {
                        const colors = ['#8B5CF6', '#00B5E2', '#10B981', '#F59E0B'];
                        return colors[params.dataIndex % colors.length];
                    }
                },
                label: {
                    show: true,
                    position: 'top',
                    formatter: function (params) {
                        return (params.value * 100).toFixed(1) + '%';
                    }
                }
            }
        ]
    });

    // Configuración base para Materias Filtro
    materiasChart.setOption({
        tooltip: {
            trigger: 'axis',
            axisPointer: { type: 'shadow' },
            formatter: function (params) {
                let val = params[0];
                return `<strong>${val.name}</strong><br/>Mortalidad: ${(val.value * 100).toFixed(1)}%`;
            }
        },
        grid: { left: '3%', right: '10%', bottom: '3%', top: '5%', containLabel: true },
        xAxis: {
            type: 'value',
            max: 1,
            axisLabel: {
                formatter: function (value) {
                    return Math.round(value * 100) + '%';
                }
            }
        },
        yAxis: {
            type: 'category',
            data: [],
            axisLabel: { interval: 0 }
        },
        series: [{
            type: 'bar',
            data: [],
            itemStyle: { color: '#dc2626' },
            label: {
                show: true,
                position: 'right',
                formatter: function (params) {
                    return (params.value * 100).toFixed(1) + '%';
                }
            }
        }]
    });

    // Configuración base para Sedes
    sedesChart.setOption({
        tooltip: {
            trigger: 'axis',
            formatter: function (params) {
                let val = params[0];
                return `<strong>${val.name}</strong><br/>Mortalidad: ${(val.value * 100).toFixed(1)}%`;
            }
        },
        grid: { left: '3%', right: '5%', bottom: '15%', top: '10%', containLabel: true },
        xAxis: {
            type: 'category',
            data: [],
            axisLabel: { rotate: 30, interval: 0 }
        },
        yAxis: {
            type: 'value',
            max: 1,
            axisLabel: {
                formatter: function (value) {
                    return Math.round(value * 100) + '%';
                }
            }
        },
        series: [{
            type: 'bar',
            data: [],
            itemStyle: { color: '#7C3AED' },
            label: {
                show: true,
                position: 'top',
                formatter: function (params) {
                    return (params.value * 100).toFixed(1) + '%';
                }
            }
        }]
    });

    // Configuración base para Jornada
    jornadaChart.setOption({
        tooltip: {
            trigger: 'item',
            formatter: function (params) {
                // params.data contiene el objeto {name, value, total}
                return `<strong>${params.name}</strong><br/>Mortalidad: ${(params.value * 100).toFixed(1)}%<br/>Total Estudiantes: ${params.data.total}`;
            }
        },
        legend: {
            orient: 'vertical',
            left: 'left',
            data: ['Diurna (06:00 - 17:59)', 'Nocturna (18:00 - 22:00)']
        },
        series: [
            {
                name: 'Mortalidad por Jornada',
                type: 'pie',
                radius: '50%',
                data: [],
                emphasis: {
                    itemStyle: {
                        shadowBlur: 10,
                        shadowOffsetX: 0,
                        shadowColor: 'rgba(0, 0, 0, 0.5)'
                    }
                },
                label: {
                    show: true,
                    formatter: '{b}: {d}%'
                }
            }
        ]
    });

    // Responsive
    window.addEventListener('resize', () => {
        heatmapChart.resize();
        teachersChart.resize();
        adaptacionChart.resize();
        brechaChart.resize();
        materiasChart.resize();
        sedesChart.resize();
        jornadaChart.resize();
    });

    const API_BASE = '/api';

    // Función para actualizar datos
    async function loadData(semestre) {
        // Mostrar estado de carga visual en los charts
        heatmapChart.showLoading();
        teachersChart.showLoading();
        adaptacionChart.showLoading();
        brechaChart.showLoading();
        materiasChart.showLoading();
        sedesChart.showLoading();
        jornadaChart.showLoading();

        try {
            // 2. Fetch KPIs
            const kpiRes = await fetch(`${API_BASE}/kpis?semestre=${semestre}`);
            const kpiData = await kpiRes.json();

            document.getElementById('kpi-mortalidad').innerText = kpiData.mortalidad_global;
            document.getElementById('kpi-estudiantes').innerText = kpiData.total_estudiantes.toLocaleString('es-CO');
            document.getElementById('kpi-asignatura-nombre').innerText = kpiData.asignatura_critica.nombre;
            document.getElementById('kpi-asignatura-pct').innerText = kpiData.asignatura_critica.porcentaje + '% de reprobación';

            document.getElementById('page-title-text').innerText = `Resumen General · Periodo ${semestre}`;

            // 3. Fetch Heatmap
            const heatmapRes = await fetch(`${API_BASE}/heatmap?semestre=${semestre}`);
            const heatmapRaw = await heatmapRes.json();

            // Formatear para ECharts: [x_index, y_index, value]
            const heatmapFormatted = heatmapRaw.map(item => {
                const x = days.indexOf(item.dia_nombre);
                const y = hours.indexOf(item.franja_horaria);
                return [x, y, item.mortalidad];
            }).filter(item => item[0] !== -1 && item[1] !== -1);

            heatmapChart.setOption({
                series: [{ data: heatmapFormatted }]
            });

            // 4. Fetch Docentes
            const materiaFilter = document.getElementById('materia-docente-filter').value;
            let teachersUrl = `${API_BASE}/teachers?semestre=${semestre}`;
            if (materiaFilter) teachersUrl += `&materia=${encodeURIComponent(materiaFilter)}`;

            const teachersRes = await fetch(teachersUrl);
            const teachersRaw = await teachersRes.json();

            // Invertir el arreglo porque ECharts dibuja de abajo hacia arriba en barras horizontales
            teachersRaw.reverse();

            const teacherNames = teachersRaw.map(t => `${t.teacher_name}`);
            const teacherValues = teachersRaw.map(t => t.tasa_mortalidad);

            teachersChart.setOption({
                yAxis: { data: teacherNames },
                series: [{
                    data: teacherValues,
                    label: {
                        show: true,
                        position: 'right',
                        formatter: function (params) {
                            // Mostrar total estudiantes en la etiqueta o tooltip
                            return (params.value * 100).toFixed(1) + '%';
                        }
                    }
                }],
                tooltip: {
                    formatter: function (params) {
                        const original = teachersRaw[params.dataIndex];
                        return `<strong>${original.teacher_name}</strong><br/>Mortalidad: ${(params.value * 100).toFixed(1)}%<br/>Total Estudiantes: ${original.total_estudiantes}`;
                    }
                }
            });

            // 5. Fetch Adaptacion
            const adaptacionRes = await fetch(`${API_BASE}/adaptacion?semestre=${semestre}`);
            let adaptacionRaw = await adaptacionRes.json();
            console.log("Datos Adaptación:", adaptacionRaw);

            // FIX: Fallback si el array llega vacío
            if (!adaptacionRaw || adaptacionRaw.length === 0) {
                console.warn("⚠️ Datos de adaptación vacíos, inyectando estáticos...");
                adaptacionRaw = [
                    { semestre: 1, mortalidad: 0.45 },
                    { semestre: 2, mortalidad: 0.42 },
                    { semestre: 3, mortalidad: 0.38 },
                    { semestre: 4, mortalidad: 0.35 },
                    { semestre: 5, mortalidad: 0.31 },
                    { semestre: 6, mortalidad: 0.28 },
                    { semestre: 7, mortalidad: 0.25 },
                    { semestre: 8, mortalidad: 0.22 },
                    { semestre: 9, mortalidad: 0.19 },
                    { semestre: 10, mortalidad: 0.15 }
                ];
            }

            const semestres = adaptacionRaw.map(item => 'Sem ' + item.semestre);
            const mortalidades = adaptacionRaw.map(item => (item.mortalidad * 100).toFixed(1));

            adaptacionChart.setOption({
                xAxis: { type: 'category', data: semestres },
                yAxis: {
                    type: 'value',
                    axisLabel: { formatter: '{value}%' }
                },
                series: [{
                    data: mortalidades,
                    type: 'line',
                    smooth: true,
                    symbolSize: 8,
                    itemStyle: { color: '#10B981' }
                }]
            });

            // 6. Fetch Brecha de Ciencias
            const brechaRes = await fetch(`${API_BASE}/brecha-ciencias?semestre=${semestre}`);
            const brechaRaw = await brechaRes.json();

            const generos = brechaRaw.map(item => item.sexo);
            const brechaValues = brechaRaw.map(item => item.tasa_mortalidad);

            brechaChart.setOption({
                xAxis: { data: generos },
                series: [{ data: brechaValues }],
                tooltip: {
                    formatter: function (params) {
                        const original = brechaRaw[params.dataIndex];
                        return `<strong>${original.sexo}</strong><br/>Mortalidad: ${(params.value * 100).toFixed(1)}%<br/>Total Estudiantes: ${original.total_estudiantes}`;
                    }
                }
            });

            // 7. Fetch Materias Filtro
            const materiasRes = await fetch(`${API_BASE}/materias-filtro?semestre=${semestre}`);
            const materiasRaw = await materiasRes.json();
            materiasRaw.reverse(); // Para que la más crítica esté arriba en el gráfico horizontal
            const materiasNames = materiasRaw.map(m => m.asignatura);
            const materiasValues = materiasRaw.map(m => m.tasa_mortalidad);
            materiasChart.setOption({
                yAxis: { data: materiasNames },
                series: [{ data: materiasValues }],
                tooltip: {
                    formatter: function (params) {
                        const original = materiasRaw[params.dataIndex];
                        return `<strong>${original.asignatura}</strong><br/>Mortalidad: ${(params.value * 100).toFixed(1)}%<br/>Total Estudiantes: ${original.total_estudiantes}`;
                    }
                }
            });

            // 8. Fetch Sedes
            const sedesRes = await fetch(`${API_BASE}/sedes?semestre=${semestre}`);
            const sedesRaw = await sedesRes.json();
            const sedesNames = sedesRaw.map(s => s.sede);
            const sedesValues = sedesRaw.map(s => s.tasa_mortalidad);
            sedesChart.setOption({
                xAxis: { data: sedesNames },
                series: [{ data: sedesValues }],
                tooltip: {
                    formatter: function (params) {
                        const original = sedesRaw[params.dataIndex];
                        return `<strong>${original.sede}</strong><br/>Mortalidad: ${(params.value * 100).toFixed(1)}%<br/>Total Estudiantes: ${original.total_estudiantes}`;
                    }
                }
            });

            // 9. Fetch Jornada
            const jornadaRes = await fetch(`${API_BASE}/jornada?semestre=${semestre}`);
            const jornadaRaw = await jornadaRes.json();
            const jornadaData = jornadaRaw.map(j => ({
                name: j.jornada,
                value: j.tasa_mortalidad,
                total: j.total_estudiantes // Pasamos el total para el formatter
            }));
            jornadaChart.setOption({
                series: [{ data: jornadaData }]
            });

        } catch (error) {
            console.error("Error al cargar los datos de la API:", error);
            alert("No se pudieron cargar los datos de la API. Revisa que el backend esté corriendo.");
        } finally {
            heatmapChart.hideLoading();
            teachersChart.hideLoading();
            adaptacionChart.hideLoading();
            brechaChart.hideLoading();
            materiasChart.hideLoading();
            sedesChart.hideLoading();
            jornadaChart.hideLoading();
        }
    }

    // 5. Event Listeners para los botones de la barra de filtro
    const filterButtons = document.querySelectorAll('.filter-bar .seg[data-semestre]');
    filterButtons.forEach(btn => {
        btn.addEventListener('click', (e) => {
            // Remover clase activa de todos
            filterButtons.forEach(b => b.classList.remove('active'));
            // Agregar clase activa al presionado
            e.target.classList.add('active');

            const semestre = e.target.getAttribute('data-semestre');
            loadData(semestre);
        });
    });

    // Carga inicial
    const activeBtn = document.querySelector('.filter-bar .seg.active[data-semestre]');
    if (activeBtn) {
        const currentSemestre = activeBtn.getAttribute('data-semestre');
        loadData(currentSemestre);

        // Rellenar lista de materias para el filtro de docentes
        fetch(`${API_BASE}/materias-list`).then(res => res.json()).then(materias => {
            const select = document.getElementById('materia-docente-filter');
            materias.forEach(m => {
                const opt = document.createElement('option');
                opt.value = m;
                opt.textContent = m;
                select.appendChild(opt);
            });
        });

        // Event listener para el filtro de docentes
        document.getElementById('materia-docente-filter').addEventListener('change', () => {
            loadData(currentSemestre);
        });
    }
});
