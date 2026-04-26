document.addEventListener('DOMContentLoaded', () => {
    // 1. Inicializar instancias de ECharts
    const heatmapChart = echarts.init(document.getElementById('chart-heatmap'));
    const teachersChart = echarts.init(document.getElementById('chart-ranking-docentes'));

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
            formatter: function(params) {
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
                    formatter: function(params) {
                        return (params.value * 100).toFixed(1) + '%';
                    }
                }
            }
        ]
    });

    // Responsive
    window.addEventListener('resize', () => {
        heatmapChart.resize();
        teachersChart.resize();
    });

    const API_BASE = 'http://127.0.0.1:8001/api';

    // Función para actualizar datos
    async function loadData(semestre) {
        // Mostrar estado de carga visual en los charts
        heatmapChart.showLoading();
        teachersChart.showLoading();

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
            const teachersRes = await fetch(`${API_BASE}/teachers?semestre=${semestre}`);
            const teachersRaw = await teachersRes.json();
            
            // Invertir el arreglo porque ECharts dibuja de abajo hacia arriba en barras horizontales
            teachersRaw.reverse();
            
            const teacherNames = teachersRaw.map(t => `${t.teacher_name} (${t.total_estudiantes} est.)`);
            const teacherValues = teachersRaw.map(t => t.tasa_mortalidad);
            
            teachersChart.setOption({
                yAxis: { data: teacherNames },
                series: [{ data: teacherValues }]
            });
            
        } catch (error) {
            console.error("Error al cargar los datos de la API:", error);
            alert("No se pudieron cargar los datos de la API. Revisa que el backend esté corriendo.");
        } finally {
            heatmapChart.hideLoading();
            teachersChart.hideLoading();
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
        loadData(activeBtn.getAttribute('data-semestre'));
    }
});
