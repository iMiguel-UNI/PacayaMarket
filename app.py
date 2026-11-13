from flask import Flask, render_template, request, redirect, session, jsonify
from flaskwebgui import FlaskUI
import sqlite3

app = Flask(__name__)
# Llave secreta obligatoria para manejar las sesiones de los usuarios
app.secret_key = 'pacayita_secreta_123' 

# Función para conectarse fácilmente a la base de datos
def get_db_connection():
    conn = sqlite3.connect('MinMarketPacaya.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route("/")
def login():
    # Al entrar al inicio, limpiamos cualquier sesión vieja por seguridad
    session.clear()
    return render_template("login.html")

@app.route("/login", methods=["POST"])
def procesar_login():
    usuario = request.form['username']
    password = request.form['password']
    
    conn = get_db_connection()
    # Validamos usuario y contraseña contra la tabla USUARIO
    user_db = conn.execute("SELECT * FROM USUARIO WHERE username = ? AND password = ?", (usuario, password)).fetchone()
    conn.close()
    
    if user_db:
        # Guardamos los datos clave en la sesión del navegador
        session['id_usuario'] = user_db['id_usuario']
        session['nombre'] = user_db['nombre']
        session['id_rol'] = user_db['id_rol'] # 1: Administrador, 2: Vendedor
        
        # Redirección inteligente según el rol
        if session['id_rol'] == 2:
            return redirect("/caja")
        else:
            return redirect("/inventario")
    else:
        # Si falla, lo devolvemos al login
        return redirect("/")

@app.route("/inventario")
def inventario():
    if 'id_usuario' not in session or session.get('id_rol') != 1:
        return redirect("/caja")
        
    conn = get_db_connection()
    productos = conn.execute("""
        SELECT P.id_producto, P.nombre, P.precio_venta, P.stock, 
               P.id_categoria, P.id_proveedor,
               C.nombre_categoria, PR.empresa AS nombre_proveedor
        FROM PRODUCTO P
        INNER JOIN CATEGORIA C ON P.id_categoria = C.id_categoria
        INNER JOIN PROVEEDOR PR ON P.id_proveedor = PR.id_proveedor
        ORDER BY P.nombre ASC
    """).fetchall()
    
    categorias = conn.execute("SELECT * FROM CATEGORIA ORDER BY nombre_categoria ASC").fetchall()
    proveedores = conn.execute("SELECT * FROM PROVEEDOR ORDER BY empresa ASC").fetchall()
    conn.close()
    
    return render_template("inventario.html", productos=productos, categorias=categorias, proveedores=proveedores)

@app.route("/inventario/agregar", methods=["POST"])
def agregar_producto():
    if session.get('id_rol') != 1:
        return redirect("/")
        
    nombre = request.form['nombre']
    id_categoria = request.form['id_categoria']
    id_proveedor = request.form['id_proveedor']
    precio_venta = float(request.form['precio_venta'])
    costo_unitario = float(request.form['costo_unitario'])
    stock = int(request.form['stock'])
    id_usuario = session['id_usuario']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 1. Insertamos el producto nuevo
        cursor.execute("""
            INSERT INTO PRODUCTO (id_categoria, id_proveedor, nombre, precio_venta, stock)
            VALUES (?, ?, ?, ?, ?)
        """, (id_categoria, id_proveedor, nombre, precio_venta, stock))
        
        id_producto_nuevo = cursor.lastrowid
        
        # 2. Si entra con stock inicial, registramos su lote en ORDEN_REESTOCK para que tenga costo real
        if stock > 0:
            costo_total = round(costo_unitario * stock, 2)
            cursor.execute("""
                INSERT INTO ORDEN_REESTOCK (id_proveedor, id_producto, id_usuario, fecha_pedido, cantidad_solicitada, cantidad_recibida, costo_total, estado)
                VALUES (?, ?, ?, date('now', 'localtime'), ?, ?, ?, 'Completada')
            """, (id_proveedor, id_producto_nuevo, id_usuario, stock, stock, costo_total))
            
        conn.commit()
    except Exception as e:
        conn.rollback()
        print("Error al agregar producto:", e)
    finally:
        conn.close()
        
    return redirect("/inventario")

@app.route("/inventario/editar/<int:id_producto>", methods=["POST"])
def editar_producto(id_producto):
    if session.get('id_rol') != 1:
        return redirect("/")
        
    nombre = request.form['nombre']
    id_categoria = request.form['id_categoria']
    id_proveedor = request.form['id_proveedor']
    precio_venta = float(request.form['precio_venta'])
    stock = int(request.form['stock'])
    
    conn = get_db_connection()
    try:
        conn.execute("""
            UPDATE PRODUCTO 
            SET nombre = ?, id_categoria = ?, id_proveedor = ?, precio_venta = ?, stock = ?
            WHERE id_producto = ?
        """, (nombre, id_categoria, id_proveedor, precio_venta, stock, id_producto))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print("Error al editar producto:", e)
    finally:
        conn.close()
        
    return redirect("/inventario")

@app.route("/inventario/eliminar/<int:id_producto>", methods=["POST"])
def eliminar_producto(id_producto):
    if session.get('id_rol') != 1:
        return redirect("/")
        
    conn = get_db_connection()
    try:
        conn.execute("DELETE FROM PRODUCTO WHERE id_producto = ?", (id_producto,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print("No se puede eliminar (tiene ventas o pedidos asociados):", e)
    finally:
        conn.close()
        
    return redirect("/inventario")

@app.route("/caja")
def caja():
    # Seguridad: Si no hay sesión iniciada, patada al login
    if 'id_usuario' not in session:
        return redirect("/")
        
    conn = get_db_connection()
    # Mostramos únicamente los productos que tienen stock disponible
    productos = conn.execute("SELECT * FROM PRODUCTO WHERE stock > 0 ORDER BY nombre ASC").fetchall()
    conn.close()
    
    return render_template("caja.html", productos=productos)

@app.route("/procesar_venta", methods=["POST"])
def procesar_venta():
    if 'id_usuario' not in session:
        return jsonify({"success": False, "error": "No autorizado"})
    
    datos = request.get_json()
    carrito = datos.get('carrito', [])
    total = datos.get('total', 0)
    id_usuario = session['id_usuario']
    
    if not carrito:
        return jsonify({"success": False, "error": "El carrito está vacío"})
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 1. Insertamos la venta general
        cursor.execute(
            "INSERT INTO VENTA (id_usuario, fecha_hora, total) VALUES (?, datetime('now', 'localtime'), ?)",
            (id_usuario, total)
        )
        id_venta_nueva = cursor.lastrowid
        
        # 2. Recorremos el carrito
        for item in carrito:
            id_prod = item['id']
            cantidad = item['cantidad']
            precio_venta_real = item['precio']
            
            # --- CÁLCULO DINÁMICO DEL COSTO UNITARIO ---
            # Buscamos la última orden de reestock donde sí se recibió producto
            cursor.execute("""
                SELECT (costo_total * 1.0 / cantidad_recibida) AS ultimo_costo
                FROM ORDEN_REESTOCK
                WHERE id_producto = ? AND cantidad_recibida > 0
                ORDER BY id_orden DESC
                LIMIT 1
            """, (id_prod,))
            orden = cursor.fetchone()
            
            if orden and orden['ultimo_costo'] is not None:
                costo_unitario = round(orden['ultimo_costo'], 2)
            else:
                # Respaldo 1: Si no hay reestock aún, buscamos el último costo registrado en ventas anteriores
                cursor.execute("""
                    SELECT costo_unitario FROM DETALLE_VENTA 
                    WHERE id_producto = ? ORDER BY id_detalle DESC LIMIT 1
                """, (id_prod,))
                venta_previa = cursor.fetchone()
                
                if venta_previa:
                    costo_unitario = venta_previa['costo_unitario']
                else:
                    # Respaldo 2: Si es un producto recién creado sin historial, estimamos 70% del precio
                    costo_unitario = round(precio_venta_real * 0.70, 2)
            
            # 3. Guardamos en DETALLE_VENTA con su precio de venta y su costo real del lote
            cursor.execute(
                "INSERT INTO DETALLE_VENTA (id_venta, id_producto, cantidad, precio_unitario, costo_unitario) VALUES (?, ?, ?, ?, ?)",
                (id_venta_nueva, id_prod, cantidad, precio_venta_real, costo_unitario)
            )
            
            # 4. Descontamos el stock
            cursor.execute(
                "UPDATE PRODUCTO SET stock = stock - ? WHERE id_producto = ?",
                (cantidad, id_prod)
            )
            
        conn.commit()
        conn.close()
        return jsonify({"success": True, "mensaje": "¡Venta cobrada con éxito!"})
        
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"success": False, "error": str(e)})

@app.route("/productos")
def ver_productos():
    if 'id_usuario' not in session:
        return redirect("/")
        
    conn = get_db_connection()
    query = """
        SELECT P.id_producto, P.nombre, P.precio_venta, P.stock, C.nombre_categoria
        FROM PRODUCTO P
        INNER JOIN CATEGORIA C ON P.id_categoria = C.id_categoria
        ORDER BY P.nombre ASC
    """
    productos = conn.execute(query).fetchall()
    conn.close()
    
    return render_template("productos.html", productos=productos)

@app.route("/mermas", methods=["GET", "POST"])
def mermas():
    if 'id_usuario' not in session:
        return redirect("/")
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Si enviaron el formulario para reportar una merma
    if request.method == "POST":
        id_producto = request.form['id_producto']
        cantidad = int(request.form['cantidad'])
        motivo = request.form['motivo']
        id_usuario = session['id_usuario']
        
        # Verificamos que haya suficiente stock para descontar
        prod = cursor.execute("SELECT stock FROM PRODUCTO WHERE id_producto = ?", (id_producto,)).fetchone()
        
        if prod and prod['stock'] >= cantidad and cantidad > 0:
            try:
                # 1. Registramos la merma
                cursor.execute("""
                    INSERT INTO MERMA (id_producto, id_usuario, cantidad, motivo, fecha)
                    VALUES (?, ?, ?, ?, datetime('now', 'localtime'))
                """, (id_producto, id_usuario, cantidad, motivo))
                
                # 2. Restamos del inventario real
                cursor.execute("""
                    UPDATE PRODUCTO SET stock = stock - ? WHERE id_producto = ?
                """, (cantidad, id_producto))
                
                conn.commit()
            except Exception as e:
                conn.rollback()
                print("Error al registrar merma:", e)
                
        conn.close()
        return redirect("/mermas")

    # GET: Cargamos productos con stock disponible para el select
    productos = conn.execute("SELECT id_producto, nombre, stock FROM PRODUCTO WHERE stock > 0 ORDER BY nombre ASC").fetchall()
    
    # Cargamos el historial de mermas (si es Vendedor ve las suyas; si es Admin ve todas)
    if session.get('id_rol') == 1:
        historial = conn.execute("""
            SELECT M.id_merma, P.nombre AS producto, U.nombre AS empleado, M.cantidad, M.motivo, M.fecha
            FROM MERMA M
            INNER JOIN PRODUCTO P ON M.id_producto = P.id_producto
            INNER JOIN USUARIO U ON M.id_usuario = U.id_usuario
            ORDER BY M.id_merma DESC
        """).fetchall()
    else:
        historial = conn.execute("""
            SELECT M.id_merma, P.nombre AS producto, U.nombre AS empleado, M.cantidad, M.motivo, M.fecha
            FROM MERMA M
            INNER JOIN PRODUCTO P ON M.id_producto = P.id_producto
            INNER JOIN USUARIO U ON M.id_usuario = U.id_usuario
            WHERE M.id_usuario = ?
            ORDER BY M.id_merma DESC
        """, (session['id_usuario'],)).fetchall()
        
    conn.close()
    return render_template("mermas.html", productos=productos, historial=historial)

@app.route("/mis_ventas")
def mis_ventas():
    if 'id_usuario' not in session:
        return redirect("/")
        
    id_usuario = session['id_usuario']
    conn = get_db_connection()
    
    # 1. Traemos todas las ventas realizadas HOY por este usuario
    ventas_hoy = conn.execute("""
        SELECT V.id_venta, V.fecha_hora, V.total,
               (SELECT SUM(cantidad) FROM DETALLE_VENTA WHERE id_venta = V.id_venta) AS total_articulos
        FROM VENTA V
        WHERE V.id_usuario = ? AND date(V.fecha_hora) = date('now', 'localtime')
        ORDER BY V.id_venta DESC
    """, (id_usuario,)).fetchall()
    
    # 2. Calculamos el total recaudado hoy (sin el alias V. porque no se declaró)
    resumen = conn.execute("""
        SELECT COUNT(id_venta) AS cantidad_ventas, COALESCE(SUM(total), 0) AS total_recaudado
        FROM VENTA
        WHERE id_usuario = ? AND date(fecha_hora) = date('now', 'localtime')
    """, (id_usuario,)).fetchone()
    
    conn.close()
    return render_template("mis_ventas.html", ventas=ventas_hoy, resumen=resumen)

@app.route("/reestock", methods=["GET", "POST"])
def reestock():
    if 'id_usuario' not in session or session.get('id_rol') != 1:
        return redirect("/caja")
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Crear nueva orden de pedido
    if request.method == "POST":
        id_producto = int(request.form['id_producto'])
        id_proveedor = int(request.form['id_proveedor'])
        cantidad_solicitada = int(request.form['cantidad_solicitada'])
        costo_estimado = float(request.form.get('costo_total', 0) or 0)
        id_usuario = session['id_usuario']
        
        try:
            cursor.execute("""
                INSERT INTO ORDEN_REESTOCK (id_proveedor, id_producto, id_usuario, fecha_pedido, cantidad_solicitada, cantidad_recibida, costo_total, estado)
                VALUES (?, ?, ?, date('now', 'localtime'), ?, 0, ?, 'Pendiente')
            """, (id_proveedor, id_producto, id_usuario, cantidad_solicitada, costo_estimado))
            conn.commit()
        except Exception as e:
            conn.rollback()
            print("Error al crear orden de reestock:", e)
        finally:
            conn.close()
        return redirect("/reestock")

    # GET: Listado de órdenes con JOIN para ver nombres reales
    ordenes = conn.execute("""
        SELECT O.id_orden, O.fecha_pedido, O.cantidad_solicitada, O.cantidad_recibida, 
               O.costo_total, O.estado, O.id_producto,
               P.nombre AS producto, PR.empresa AS proveedor, U.nombre AS usuario
        FROM ORDEN_REESTOCK O
        INNER JOIN PRODUCTO P ON O.id_producto = P.id_producto
        INNER JOIN PROVEEDOR PR ON O.id_proveedor = PR.id_proveedor
        INNER JOIN USUARIO U ON O.id_usuario = U.id_usuario
        ORDER BY O.id_orden DESC
    """).fetchall()
    
    productos = conn.execute("SELECT id_producto, nombre, id_proveedor, stock FROM PRODUCTO ORDER BY nombre ASC").fetchall()
    proveedores = conn.execute("SELECT id_proveedor, empresa FROM PROVEEDOR ORDER BY empresa ASC").fetchall()
    conn.close()
    
    return render_template("reestock.html", ordenes=ordenes, productos=productos, proveedores=proveedores)

@app.route("/reestock/recibir/<int:id_orden>", methods=["POST"])
def recibir_reestock(id_orden):
    if session.get('id_rol') != 1:
        return redirect("/")
        
    unidades_nuevas = int(request.form['unidades_recibidas'])
    costo_pagado = float(request.form['costo_total'])
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        orden = cursor.execute("SELECT * FROM ORDEN_REESTOCK WHERE id_orden = ?", (id_orden,)).fetchone()
        
        if orden and unidades_nuevas > 0:
            total_recibido = orden['cantidad_recibida'] + unidades_nuevas
            nuevo_costo_total = orden['costo_total'] + costo_pagado
            
            # Determinamos si la entrega quedó Parcial o Completada
            estado = 'Completada' if total_recibido >= orden['cantidad_solicitada'] else 'Parcial'
            
            # 1. Actualizamos la orden de reestock
            cursor.execute("""
                UPDATE ORDEN_REESTOCK 
                SET cantidad_recibida = ?, costo_total = ?, estado = ?
                WHERE id_orden = ?
            """, (total_recibido, nuevo_costo_total, estado, id_orden))
            
            # 2. Sumamos las unidades recibidas al inventario real
            cursor.execute("""
                UPDATE PRODUCTO SET stock = stock + ? WHERE id_producto = ?
            """, (unidades_nuevas, orden['id_producto']))
            
            conn.commit()
    except Exception as e:
        conn.rollback()
        print("Error al recibir mercancía:", e)
    finally:
        conn.close()
        
    return redirect("/reestock")

@app.route("/registros")
def registros():
    if 'id_usuario' not in session or session.get('id_rol') != 1:
        return redirect("/caja")
        
    conn = get_db_connection()
    
    # Traemos todas las ventas con el nombre del cajero que la realizó
    ventas = conn.execute("""
        SELECT V.id_venta, V.fecha_hora, V.total, U.nombre AS vendedor,
               (SELECT COALESCE(SUM(cantidad), 0) FROM DETALLE_VENTA WHERE id_venta = V.id_venta) AS cant_productos
        FROM VENTA V
        INNER JOIN USUARIO U ON V.id_usuario = U.id_usuario
        ORDER BY V.id_venta DESC
    """).fetchall()
    
    conn.close()
    return render_template("registros.html", ventas=ventas)

@app.route("/registros/detalle/<int:id_venta>")
def detalle_venta_json(id_venta):
    if session.get('id_rol') != 1:
        return jsonify({"error": "No autorizado"}), 403
        
    conn = get_db_connection()
    detalles = conn.execute("""
        SELECT P.nombre AS producto, D.cantidad, D.precio_unitario, D.costo_unitario,
               (D.cantidad * D.precio_unitario) AS subtotal,
               ((D.precio_unitario - D.costo_unitario) * D.cantidad) AS ganancia
        FROM DETALLE_VENTA D
        INNER JOIN PRODUCTO P ON D.id_producto = P.id_producto
        WHERE D.id_venta = ?
    """, (id_venta,)).fetchall()
    conn.close()
    
    return jsonify([dict(row) for row in detalles])

@app.route("/registros/anular/<int:id_venta>", methods=["POST"])
def anular_venta(id_venta):
    if session.get('id_rol') != 1:
        return redirect("/")
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 1. Buscamos qué productos se vendieron en esa factura para devolverlos al stock
        items = cursor.execute("SELECT id_producto, cantidad FROM DETALLE_VENTA WHERE id_venta = ?", (id_venta,)).fetchall()
        
        for item in items:
            cursor.execute("UPDATE PRODUCTO SET stock = stock + ? WHERE id_producto = ?", (item['cantidad'], item['id_producto']))
            
        # 2. Borramos el detalle y la cabecera de la venta
        cursor.execute("DELETE FROM DETALLE_VENTA WHERE id_venta = ?", (id_venta,))
        cursor.execute("DELETE FROM VENTA WHERE id_venta = ?", (id_venta,))
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        print("Error al anular venta:", e)
    finally:
        conn.close()
        
    return redirect("/registros")

@app.route("/economia")
def economia():
    if 'id_usuario' not in session or session.get('id_rol') != 1:
        return redirect("/caja")
        
    fecha_inicio = request.args.get('fecha_inicio', '')
    fecha_fin = request.args.get('fecha_fin', '')
    
    conn = get_db_connection()
    
    # Filtros dinámicos según si el Admin eligió rango de fechas o historial completo
    filtro_ventas = ""
    filtro_mermas = ""
    filtro_reestock = ""
    params = []
    
    if fecha_inicio and fecha_fin:
        filtro_ventas = "WHERE date(V.fecha_hora) BETWEEN ? AND ?"
        filtro_mermas = "WHERE date(M.fecha) BETWEEN ? AND ?"
        filtro_reestock = "WHERE date(O.fecha_pedido) BETWEEN ? AND ?"
        params = [fecha_inicio, fecha_fin]

    # 1. Ingresos, Costos y Ganancia Bruta de Ventas
    balance_ventas = conn.execute(f"""
        SELECT 
            COALESCE(SUM(D.cantidad * D.precio_unitario), 0) AS ingresos_totales,
            COALESCE(SUM(D.cantidad * D.costo_unitario), 0) AS costo_vendido,
            COALESCE(SUM(D.cantidad * (D.precio_unitario - D.costo_unitario)), 0) AS ganancia_ventas
        FROM DETALLE_VENTA D
        INNER JOIN VENTA V ON D.id_venta = V.id_venta
        {filtro_ventas}
    """, params).fetchone()

    # 2. Pérdidas económicas por Mermas (valoradas al último costo conocido o 70% del precio)
    mermas_raw = conn.execute(f"""
        SELECT M.cantidad, P.precio_venta,
               (SELECT (costo_total * 1.0 / cantidad_recibida) 
                FROM ORDEN_REESTOCK 
                WHERE id_producto = M.id_producto AND cantidad_recibida > 0 
                ORDER BY id_orden DESC LIMIT 1) AS costo_lote
        FROM MERMA M
        INNER JOIN PRODUCTO P ON M.id_producto = P.id_producto
        {filtro_mermas}
    """, params).fetchall()
    
    perdida_mermas = 0
    for m in mermas_raw:
        costo_u = m['costo_lote'] if m['costo_lote'] is not None else (m['precio_venta'] * 0.70)
        perdida_mermas += m['cantidad'] * costo_u

    # 3. Total invertido en compras a proveedores (Reestock)
    inversion_reestock = conn.execute(f"""
        SELECT COALESCE(SUM(O.costo_total), 0) AS total_invertido
        FROM ORDEN_REESTOCK O
        {filtro_reestock}
    """, params).fetchone()['total_invertido']

    # 4. Top 5 Productos más rentables
    top_productos = conn.execute(f"""
        SELECT P.nombre, 
               SUM(D.cantidad) AS unidades_vendidas,
               SUM(D.cantidad * D.precio_unitario) AS total_generado,
               SUM(D.cantidad * (D.precio_unitario - D.costo_unitario)) AS ganancia_neta
        FROM DETALLE_VENTA D
        INNER JOIN VENTA V ON D.id_venta = V.id_venta
        INNER JOIN PRODUCTO P ON D.id_producto = P.id_producto
        {filtro_ventas}
        GROUP BY P.id_producto
        ORDER BY ganancia_neta DESC
        LIMIT 5
    """, params).fetchall()

    # 5. Rendimiento por Vendedor
    rendimiento_vendedores = conn.execute(f"""
        SELECT U.nombre, 
               COUNT(V.id_venta) AS num_ventas,
               COALESCE(SUM(V.total), 0) AS total_vendido
        FROM VENTA V
        INNER JOIN USUARIO U ON V.id_usuario = U.id_usuario
        {filtro_ventas}
        GROUP BY U.id_usuario
        ORDER BY total_vendido DESC
    """, params).fetchall()

    conn.close()
    
    utilidad_real = balance_ventas['ganancia_ventas'] - perdida_mermas

    return render_template(
        "economia.html",
        balance=balance_ventas,
        perdida_mermas=perdida_mermas,
        utilidad_real=utilidad_real,
        inversion_reestock=inversion_reestock,
        top_productos=top_productos,
        vendedores=rendimiento_vendedores,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin
    )

@app.route("/empleados")
def empleados():
    if 'id_usuario' not in session or session.get('id_rol') != 1:
        return redirect("/caja")
        
    conn = get_db_connection()
    
    usuarios = conn.execute("""
        SELECT id_usuario, nombre, username, id_rol
        FROM USUARIO
        ORDER BY id_rol ASC, nombre ASC
    """).fetchall()
    
    proveedores = conn.execute("SELECT * FROM PROVEEDOR ORDER BY empresa ASC").fetchall()
    categorias = conn.execute("SELECT * FROM CATEGORIA ORDER BY nombre_categoria ASC").fetchall()
    
    # Detectamos columnas extra en PROVEEDOR (por si tiene telefono o contacto)
    cols_prov = [col['name'] for col in conn.execute("PRAGMA table_info(PROVEEDOR)").fetchall()]
    conn.close()
    
    return render_template(
        "empleados.html",
        usuarios=usuarios,
        proveedores=proveedores,
        categorias=categorias,
        cols_prov=cols_prov
    )

@app.route("/empleados/agregar", methods=["POST"])
def agregar_empleado():
    if session.get('id_rol') != 1:
        return redirect("/")
        
    nombre = request.form['nombre']
    username = request.form['username']
    password = request.form['password']
    id_rol = int(request.form['id_rol'])
    
    conn = get_db_connection()
    try:
        conn.execute("""
            INSERT INTO USUARIO (id_rol, nombre, username, password)
            VALUES (?, ?, ?, ?)
        """, (id_rol, nombre, username, password))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print("Error al crear usuario:", e)
    finally:
        conn.close()
        
    return redirect("/empleados")

@app.route("/empleados/editar/<int:id_usuario>", methods=["POST"])
def editar_empleado(id_usuario):
    if session.get('id_rol') != 1:
        return redirect("/")
        
    nombre = request.form['nombre']
    username = request.form['username']
    password = request.form['password'].strip()
    id_rol = int(request.form['id_rol'])
    
    conn = get_db_connection()
    try:
        if password:
            conn.execute("""
                UPDATE USUARIO SET nombre = ?, username = ?, password = ?, id_rol = ?
                WHERE id_usuario = ?
            """, (nombre, username, password, id_rol, id_usuario))
        else:
            conn.execute("""
                UPDATE USUARIO SET nombre = ?, username = ?, id_rol = ?
                WHERE id_usuario = ?
            """, (nombre, username, id_rol, id_usuario))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print("Error al editar usuario:", e)
    finally:
        conn.close()
        
    return redirect("/empleados")

@app.route("/empleados/eliminar/<int:id_usuario>", methods=["POST"])
def eliminar_empleado(id_usuario):
    if session.get('id_rol') != 1 or id_usuario == session.get('id_usuario'):
        return redirect("/empleados")
        
    conn = get_db_connection()
    try:
        conn.execute("DELETE FROM USUARIO WHERE id_usuario = ?", (id_usuario,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print("No se puede eliminar (tiene ventas o mermas asociadas):", e)
    finally:
        conn.close()
        
    return redirect("/empleados")

@app.route("/proveedores/agregar", methods=["POST"])
def agregar_proveedor():
    if session.get('id_rol') != 1:
        return redirect("/")
        
    empresa = request.form['empresa']
    telefono = request.form.get('telefono', '')
    contacto = request.form.get('contacto', '')
    
    conn = get_db_connection()
    try:
        cols = [col['name'] for col in conn.execute("PRAGMA table_info(PROVEEDOR)").fetchall()]
        if 'contacto' in cols and 'telefono' in cols:
            conn.execute("INSERT INTO PROVEEDOR (empresa, contacto, telefono) VALUES (?, ?, ?)", (empresa, contacto, telefono))
        elif 'telefono' in cols:
            conn.execute("INSERT INTO PROVEEDOR (empresa, telefono) VALUES (?, ?)", (empresa, telefono))
        else:
            conn.execute("INSERT INTO PROVEEDOR (empresa) VALUES (?)", (empresa,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print("Error al agregar proveedor:", e)
    finally:
        conn.close()
        
    return redirect("/empleados")

@app.route("/categorias/agregar", methods=["POST"])
def agregar_categoria():
    if session.get('id_rol') != 1:
        return redirect("/")
        
    nombre_categoria = request.form['nombre_categoria']
    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO CATEGORIA (nombre_categoria) VALUES (?)", (nombre_categoria,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print("Error al agregar categoría:", e)
    finally:
        conn.close()
        
    return redirect("/empleados")


FlaskUI(app=app, server="flask", width=1100, height=700).run()