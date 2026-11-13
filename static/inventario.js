document.addEventListener('DOMContentLoaded', () => {
    const table = document.querySelector('table');
    const headers = table.querySelectorAll('th');
    const tbody = table.querySelector('tbody');

    headers.forEach((header, index) => {
        // Ignorar la columna de "Acciones" (la número 5)
        if (index === 5) return; 

        header.title = "Clic para ordenar";
        let asc = true;

        header.addEventListener('click', () => {
            const rows = Array.from(tbody.querySelectorAll('tr'));
            
            if (rows.length === 0 || rows[0].cells.length === 1) return;

            const sortedRows = rows.sort((a, b) => {
                let aText = a.cells[index].innerText.trim();
                let bText = b.cells[index].innerText.trim();

                // Limpiar símbolos para poder ordenar números
                aText = aText.replace('C$', '').replace('#', '').trim();
                bText = bText.replace('C$', '').replace('#', '').trim();

                const aNum = parseFloat(aText);
                const bNum = parseFloat(bText);

                // Lógica de ordenamiento matemático o alfabético
                if (!isNaN(aNum) && !isNaN(bNum)) {
                    return asc ? aNum - bNum : bNum - aNum;
                } else {
                    return asc ? aText.localeCompare(bText) : bText.localeCompare(aText);
                }
            });

            asc = !asc;
            tbody.append(...sortedRows);
        });
    });
});