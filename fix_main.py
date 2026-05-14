import re

with open('static/main.js', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Remove the dynamic logic
marker = "// ==================== LÓGICA DE COMPARATIVA DINÁMICA ===================="
if marker in content:
    content = content[:content.find(marker)].strip() + "\n"

# 2. Fix the Event Listener
old_listener = re.search(r"// D\. Event Listeners para Botones de Semestre.*?actualizarDashboard\(\);\n        \}\);\n    \}\);", content, re.DOTALL)

new_listener = """// D. Event Listeners para Botones de Semestre
    const botonesSemestre = document.querySelectorAll('.filter-bar button');
    botonesSemestre.forEach(btn => {
        btn.addEventListener('click', (e) => {
            botonesSemestre.forEach(b => b.classList.remove('active'));
            const botonClickeado = e.currentTarget;
            botonClickeado.classList.add('active');
            
            const btnValue = botonClickeado.getAttribute('data-semester') || botonClickeado.innerText.trim();
            const titulo = document.getElementById('titulo-periodo');
            
            if (btnValue === "Comparar") {
                isComparing = true;
                if (titulo) titulo.innerText = `Comparativa: 2025-1 vs 2025-2`;
            } else {
                isComparing = false;
                currentSemestre = btnValue;
                if (titulo) titulo.innerText = `Resumen General · Periodo ${currentSemestre}`;
            }
            actualizarDashboard();
        });
    });"""

if old_listener:
    content = content.replace(old_listener.group(0), new_listener)

with open('static/main.js', 'w', encoding='utf-8') as f:
    f.write(content)

print("Main.js updated successfully")
