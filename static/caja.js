// Esperar a que cargue la página y asignarle el clic a todos los botones de agregar
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
});

let carrito = [];
let totalVenta = 0;

// 1. Agregar producto al carrito
function agregarAlCarrito(id, nombre, precio, stockMax) {
    // Buscamos si ya está en el carrito
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

// 3. Quitar un producto de la lista (con la X roja)
function quitarDelCarrito(index) {
    carrito.splice(index, 1);
    actualizarCarrito();
}

// 4. Calcular vuelto automáticamente cuando escriben el billete
function calcularVuelto() {
    let efectivo = parseFloat(document.getElementById('efectivo').value) || 0;
    let vuelto = efectivo - totalVenta;
    
    let vueltoDiv = document.getElementById('vuelto');
    if (vuelto < 0 || carrito.length === 0) {
        vueltoDiv.innerText = "C$ 0.00";
        vueltoDiv.style.color = "#dc2626"; // Rojo si falta plata
    } else {
        vueltoDiv.innerText = `C$ ${vuelto.toFixed(2)}`;
        vueltoDiv.style.color = "#166534"; // Verde si está todo bien
    }
}

// 5. Buscador rápido en la tabla
document.getElementById('buscarProducto').addEventListener('keyup', function() {
    let filtro = this.value.toLowerCase();
    let filas = document.querySelectorAll('#tablaProductos tbody tr');
    
    filas.forEach(fila => {
        let nombre = fila.cells[0].innerText.toLowerCase();
        if(nombre.includes(filtro)) {
            fila.style.display = '';
        } else {
            fila.style.display = 'none';
        }
    });
});

// 6. Botón de cobrar (Por ahora solo avisa, luego lo conectamos a la BD)
function procesarVenta() {
    if (carrito.length === 0) {
        alert("El carrito está vacío, loco.");
        return;
    }
    
    let efectivo = parseFloat(document.getElementById('efectivo').value) || 0;
    if (efectivo < totalVenta) {
        alert("El maje no ha completado el pago. Faltan C$ " + (totalVenta - efectivo).toFixed(2));
        return;
    }

    alert("¡Venta cobrada con éxito! (En el próximo paso guardaremos esto en la Base de Datos)");
    // Aquí mandaremos los datos a Python más adelante
}