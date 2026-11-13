let carrito = [];
let totalVenta = 0;

// Soporta tanto el onclick directo como los botones con atributos data-
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.btn-agregar').forEach(boton => {
        boton.addEventListener('click', function() {
            let id = parseInt(this.getAttribute('data-id'));
            let nombre = this.getAttribute('data-nombre');
            let precio = parseFloat(this.getAttribute('data-precio'));
            let stock = parseInt(this.getAttribute('data-stock'));
            agregarAlCarrito(id, nombre, precio, stock);
        });
    });

    const buscador = document.getElementById('buscarProducto');
    if (buscador) {
        buscador.addEventListener('keyup', function() {
            let filtro = this.value.toLowerCase();
            let filas = document.querySelectorAll('#tablaProductos tbody tr');
            
            filas.forEach(fila => {
                let nombre = fila.cells[0].innerText.toLowerCase();
                fila.style.display = nombre.includes(filtro) ? '' : 'none';
            });
        });
    }
});

// 1. Agregar producto al carrito
function agregarAlCarrito(id, nombre, precio, stockMax) {
    let item = carrito.find(p => p.id === id);
    
    if (item) {
        if (item.cantidad < stockMax) {
            item.cantidad++;
        } else {
            alert("No hay más stock disponible de este producto.");
        }
    } else {
        carrito.push({ id: id, nombre: nombre, precio: precio, cantidad: 1, stockMax: stockMax });
    }
    actualizarCarrito();
}

// 2. Actualizar la vista del carrito
function actualizarCarrito() {
    const lista = document.getElementById('listaCarrito');
    totalVenta = 0;
    
    if (carrito.length === 0) {
        lista.innerHTML = '<p style="text-align: center; color: #94a3b8; margin-top: 50px;">El carrito está vacío</p>';
        document.getElementById('totalPagar').innerText = "C$ 0.00";
        calcularVuelto();
        return;
    }

    lista.innerHTML = '';
    carrito.forEach((item, index) => {
        let subtotal = item.precio * item.cantidad;
        totalVenta += subtotal;
        
        lista.innerHTML += `
            <div class="carrito-item">
                <div style="flex: 2;"><b>${item.nombre}</b><br><small>C$ ${item.precio.toFixed(2)} c/u</small></div>
                <div style="flex: 1; text-align: center;">
                    <b>x${item.cantidad}</b>
                </div>
                <div style="flex: 1; text-align: right; color: #0284c7; font-weight: bold;">
                    C$ ${subtotal.toFixed(2)}
                </div>
                <div style="flex: 0.5; text-align: right;">
                    <i class="fa-solid fa-xmark" style="color: #ef4444; cursor: pointer;" onclick="quitarDelCarrito(${index})"></i>
                </div>
            </div>
        `;
    });

    document.getElementById('totalPagar').innerText = `C$ ${totalVenta.toFixed(2)}`;
    calcularVuelto();
}

// 3. Quitar un producto de la lista
function quitarDelCarrito(index) {
    carrito.splice(index, 1);
    actualizarCarrito();
}

// 4. Calcular vuelto automáticamente
function calcularVuelto() {
    let efectivo = parseFloat(document.getElementById('efectivo').value) || 0;
    let vuelto = efectivo - totalVenta;
    
    let vueltoDiv = document.getElementById('vuelto');
    if (vuelto < 0 || carrito.length === 0) {
        vueltoDiv.innerText = "C$ 0.00";
        vueltoDiv.style.color = "#dc2626";
    } else {
        vueltoDiv.innerText = `C$ ${vuelto.toFixed(2)}`;
        vueltoDiv.style.color = "#166534";
    }
}

// 5. Enviar la venta real a Python (/procesar_venta)
function procesarVenta() {
    if (carrito.length === 0) {
        alert("El carrito está vacío.");
        return;
    }
    
    let efectivo = parseFloat(document.getElementById('efectivo').value) || 0;
    if (efectivo < totalVenta) {
        alert("Falta dinero para completar el pago. Faltan C$ " + (totalVenta - efectivo).toFixed(2));
        return;
    }

    fetch('/procesar_venta', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ carrito: carrito, total: totalVenta })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            let cambio = (efectivo - totalVenta).toFixed(2);
            alert(`✅ ¡Venta registrada en BD!\nTotal: C$ ${totalVenta.toFixed(2)}\nCambio a entregar: C$ ${cambio}`);
            carrito = [];
            document.getElementById('efectivo').value = '';
            location.reload();
        } else {
            alert("❌ Error al guardar la venta: " + data.error);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert("Error de conexión con el servidor.");
    });
}