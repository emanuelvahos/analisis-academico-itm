import re

with open('static/main.js', 'r', encoding='utf-8') as f:
    content = f.read()

# find `    actualizarDashboard();\n});` to insert before it
# wait, let me just append it outside of the `});` or check what line 723 is.
# Actually I'll just append it to the end of the file. It's safer.
# And add a DOMContentLoaded listener specifically for the add-to-board button.
# Oh wait, if the `btn-agregar-comparativa` doesn't exist yet, it's safer to use an interval or just wait for it.
# Actually, if I just append to the end of the file, the DOM is already loaded because scripts are usually at the end of the body.

append_logic = """
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
"""

with open('static/main.js', 'a', encoding='utf-8') as f:
    f.write("\n" + append_logic)

print("Appended dynamic chart logic to main.js")
