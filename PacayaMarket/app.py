import csv
import io
import os
import sqlite3
import sys
from datetime import date, datetime, timedelta
from functools import wraps

from flask import (Flask, Response, flash, g, jsonify, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "pacayita.db")

app = Flask(__name__)
app.secret_key = "cambia-esta-clave-por-algo-largo-y-secreto"

# ---------- Configuración del negocio (edítala a tu gusto) ----------
NEGOCIO = {
    "nombre": "Mini Market Pacayita",
    "direccion": "",
    "telefono": "",
    "moneda": "C$",
}
CATEGORIAS = ["Licor", "Abarrotes", "Snacks", "Cigarros", "Jabones y limpieza", "Otros"]
METODOS = ["Efectivo", "Tarjeta", "Transferencia"]
MOTIVOS = ["Vencido", "Quebrado", "Dañado", "Otro"]
ROLES = ("admin", "vendedor")
DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario TEXT UNIQUE NOT NULL,
    nombre TEXT NOT NULL,
    password TEXT NOT NULL,
    rol TEXT NOT NULL DEFAULT 'vendedor',
    activo INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS proveedores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    contacto TEXT,
    telefono TEXT,
    notas TEXT,
    activo INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS productos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    categoria TEXT NOT NULL DEFAULT 'Otros',
    costo REAL NOT NULL DEFAULT 0,
    precio REAL NOT NULL,
    stock INTEGER NOT NULL DEFAULT 0,
    stock_min INTEGER NOT NULL DEFAULT 3,
    proveedor_id INTEGER REFERENCES proveedores(id),
    activo INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS ventas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    total REAL NOT NULL,
    metodo TEXT NOT NULL,
    recibido REAL NOT NULL,
    cambio REAL NOT NULL,
    estado TEXT NOT NULL DEFAULT 'ok'
);
CREATE TABLE IF NOT EXISTS venta_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venta_id INTEGER NOT NULL REFERENCES ventas(id),
    producto_id INTEGER NOT NULL REFERENCES productos(id),
    nombre TEXT NOT NULL,
    cantidad INTEGER NOT NULL,
    precio REAL NOT NULL,
    costo REAL NOT NULL DEFAULT 0,
    subtotal REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS mermas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL,
    producto_id INTEGER NOT NULL REFERENCES productos(id),
    cantidad INTEGER NOT NULL,
    motivo TEXT NOT NULL,
    nota TEXT,
    costo REAL NOT NULL DEFAULT 0,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id)
);
"""


class Aviso(Exception):
    """Error con mensaje listo para mostrar al usuario."""


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_=None):
    con = g.pop("db", None)
    if con:
        con.close()


def _cols(con, tabla):
    return [r[1] for r in con.execute(f"PRAGMA table_info({tabla})")]


def init_db():
    con = sqlite3.connect(DB)
    con.executescript(SCHEMA)
    # Migración de bases de datos de la versión anterior
    if "proveedor_id" not in _cols(con, "productos"):
        con.execute("ALTER TABLE productos ADD COLUMN proveedor_id INTEGER REFERENCES proveedores(id)")
    if "costo" not in _cols(con, "venta_items"):
        con.execute("ALTER TABLE venta_items ADD COLUMN costo REAL NOT NULL DEFAULT 0")
        con.execute("UPDATE venta_items SET costo=COALESCE((SELECT costo FROM productos WHERE id=producto_id),0)")
    con.execute("UPDATE usuarios SET rol='vendedor' WHERE rol='cajero'")
    if not con.execute("SELECT 1 FROM usuarios").fetchone():
        con.execute(
            "INSERT INTO usuarios (usuario, nombre, password, rol) VALUES (?,?,?,?)",
            ("admin", "Administrador", generate_password_hash("admin123"), "admin"),
        )
    con.commit()
    con.close()


# ---------- Auth ----------
def login_required(f):
    @wraps(f)
    def w(*a, **k):
        if "uid" not in session:
            if request.path.startswith("/api/"):
                return jsonify(error="Sesión expirada"), 401
            return redirect(url_for("login"))
        return f(*a, **k)
    return w


def admin_required(f):
    @wraps(f)
    @login_required
    def w(*a, **k):
        if session.get("rol") != "admin":
            flash("Solo el administrador puede entrar ahí", "error")
            return redirect(url_for("caja"))
        return f(*a, **k)
    return w


@app.context_processor
def inject():
    alertas = 0
    if session.get("rol") == "admin":
        alertas = db().execute(
            "SELECT COUNT(*) FROM productos WHERE activo=1 AND stock<=stock_min").fetchone()[0]
    return dict(n=NEGOCIO, categorias=CATEGORIAS, metodos=METODOS, motivos=MOTIVOS, alertas=alertas)


@app.template_filter("m")
def moneda(v):
    return f"{NEGOCIO['moneda']} {float(v or 0):,.2f}"


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = db().execute(
            "SELECT * FROM usuarios WHERE usuario=? AND activo=1",
            (request.form.get("usuario", "").strip().lower(),),
        ).fetchone()
        if u and check_password_hash(u["password"], request.form.get("password", "")):
            session.clear()
            session.update(uid=u["id"], usuario=u["usuario"], nombre=u["nombre"], rol=u["rol"])
            return redirect(url_for("inicio"))
        flash("Usuario o contraseña incorrectos", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------- Dashboard (admin) ----------
@app.route("/")
@login_required
def inicio():
    if session["rol"] != "admin":
        return redirect(url_for("caja"))
    con = db()
    hoy = date.today()
    hoy_s = hoy.isoformat()
    resumen = con.execute(
        "SELECT COALESCE(SUM(total),0) t, COUNT(*) c FROM ventas WHERE date(fecha)=? AND estado='ok'",
        (hoy_s,)).fetchone()
    mes = con.execute(
        "SELECT COALESCE(SUM(total),0) t FROM ventas WHERE date(fecha)>=? AND estado='ok'",
        (hoy.replace(day=1).isoformat(),)).fetchone()

    # Ventas de los últimos 7 días
    desde7 = hoy - timedelta(days=6)
    filas = {r["d"]: r["t"] for r in con.execute(
        "SELECT date(fecha) d, SUM(total) t FROM ventas WHERE estado='ok' AND date(fecha)>=? GROUP BY d",
        (desde7.isoformat(),))}
    dias = []
    for i in range(7):
        d = desde7 + timedelta(days=i)
        dias.append({"label": DIAS[d.weekday()], "total": filas.get(d.isoformat(), 0)})
    mx = max([d["total"] for d in dias] + [1])
    for d in dias:
        d["pct"] = round(d["total"] / mx * 100)

    # Más vendidos (30 días)
    top = [dict(r) for r in con.execute(
        "SELECT vi.nombre, SUM(vi.cantidad) c, SUM(vi.subtotal) t FROM venta_items vi "
        "JOIN ventas v ON v.id=vi.venta_id WHERE v.estado='ok' AND date(v.fecha)>=? "
        "GROUP BY vi.producto_id ORDER BY c DESC LIMIT 5",
        ((hoy - timedelta(days=30)).isoformat(),))]
    mxt = max([t["c"] for t in top] + [1])
    for t in top:
        t["pct"] = round(t["c"] / mxt * 100)

    bajo = con.execute(
        "SELECT p.*, pr.nombre proveedor, pr.telefono prov_tel FROM productos p "
        "LEFT JOIN proveedores pr ON pr.id=p.proveedor_id "
        "WHERE p.activo=1 AND p.stock<=p.stock_min ORDER BY p.stock, p.nombre").fetchall()
    agotados = sum(1 for p in bajo if p["stock"] <= 0)
    ultimas = con.execute(
        "SELECT v.*, u.nombre vendedor FROM ventas v JOIN usuarios u ON u.id=v.usuario_id "
        "ORDER BY v.id DESC LIMIT 6").fetchall()
    return render_template("index.html", resumen=resumen, mes=mes, dias=dias, top=top,
                           bajo=bajo, agotados=agotados, ultimas=ultimas)


# ---------- Caja ----------
@app.route("/caja")
@login_required
def caja():
    rows = db().execute(
        "SELECT id, nombre, categoria, precio, stock, stock_min FROM productos "
        "WHERE activo=1 ORDER BY nombre").fetchall()
    return render_template("caja.html", productos=[dict(r) for r in rows])


@app.post("/api/venta")
@login_required
def api_venta():
    data = request.get_json(force=True, silent=True) or {}
    items = data.get("items") or []
    metodo = "Efectivo"
    if not items:
        return jsonify(error="El carrito está vacío"), 400
    con = db()
    try:
        lineas, total = [], 0.0
        for it in items:
            cant = int(it["cant"])
            p = con.execute("SELECT * FROM productos WHERE id=? AND activo=1", (it["id"],)).fetchone()
            if not p or cant <= 0:
                raise Aviso("Producto inválido en el carrito")
            if p["stock"] < cant:
                raise Aviso(f"Stock insuficiente de {p['nombre']} (quedan {p['stock']})")
            sub = round(p["precio"] * cant, 2)
            total += sub
            lineas.append((p, cant, sub))
        total = round(total, 2)
        recibido = float(data.get("recibido") or 0)
        if recibido < total:
            raise Aviso("El monto recibido es menor al total")
        cur = con.execute(
            "INSERT INTO ventas (fecha, usuario_id, total, metodo, recibido, cambio) VALUES (?,?,?,?,?,?)",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), session["uid"], total, metodo,
             recibido, round(recibido - total, 2)))
        vid = cur.lastrowid
        for p, cant, sub in lineas:
            con.execute(
                "INSERT INTO venta_items (venta_id, producto_id, nombre, cantidad, precio, costo, subtotal) "
                "VALUES (?,?,?,?,?,?,?)", (vid, p["id"], p["nombre"], cant, p["precio"], p["costo"], sub))
            con.execute("UPDATE productos SET stock=stock-? WHERE id=?", (cant, p["id"]))
        con.commit()
        alertas = []
        for p, cant, _ in lineas:
            q = p["stock"] - cant
            if q <= p["stock_min"]:
                alertas.append(f"{p['nombre']}: " + ("agotado" if q <= 0 else f"quedan {q}"))
        if alertas:
            flash("Pocas unidades → " + " | ".join(alertas), "warn")
        return jsonify(ok=True, id=vid)
    except Aviso as e:
        con.rollback()
        return jsonify(error=str(e)), 400
    except (ValueError, KeyError, TypeError):
        con.rollback()
        return jsonify(error="Datos inválidos"), 400


# ---------- Productos ----------
@app.route("/productos")
@admin_required
def productos():
    con = db()
    lista = con.execute(
        "SELECT p.*, pr.nombre proveedor FROM productos p "
        "LEFT JOIN proveedores pr ON pr.id=p.proveedor_id WHERE p.activo=1 ORDER BY p.nombre").fetchall()
    provs = con.execute("SELECT * FROM proveedores WHERE activo=1 ORDER BY nombre").fetchall()
    editar = None
    if request.args.get("editar"):
        editar = con.execute("SELECT * FROM productos WHERE id=?", (request.args["editar"],)).fetchone()
    return render_template("productos.html", lista=lista, provs=provs, editar=editar)


@app.post("/productos/guardar")
@admin_required
def productos_guardar():
    f = request.form
    try:
        datos = (
            f["nombre"].strip(), f["categoria"], float(f.get("costo") or 0), float(f["precio"]),
            int(f.get("stock") or 0), int(f.get("stock_min") or 0), f.get("proveedor_id") or None,
        )
        if not datos[0] or datos[3] < 0:
            raise ValueError
    except (ValueError, KeyError):
        flash("Revisa los datos del producto: nombre y precio son obligatorios", "error")
        return redirect(url_for("productos"))
    con = db()
    if f.get("id"):
        con.execute(
            "UPDATE productos SET nombre=?, categoria=?, costo=?, precio=?, stock=?, stock_min=?, "
            "proveedor_id=? WHERE id=?", datos + (f["id"],))
    else:
        con.execute(
            "INSERT INTO productos (nombre, categoria, costo, precio, stock, stock_min, proveedor_id) "
            "VALUES (?,?,?,?,?,?,?)", datos)
    con.commit()
    flash("Producto guardado", "ok")
    return redirect(url_for("productos"))


@app.post("/productos/<int:pid>/eliminar")
@admin_required
def productos_eliminar(pid):
    con = db()
    con.execute("UPDATE productos SET activo=0 WHERE id=?", (pid,))
    con.commit()
    flash("Producto eliminado", "ok")
    return redirect(url_for("productos"))


# ---------- Proveedores ----------
@app.route("/proveedores")
@admin_required
def proveedores():
    con = db()
    lista = con.execute(
        "SELECT pr.*, COUNT(p.id) n, GROUP_CONCAT(p.nombre, ', ') productos FROM proveedores pr "
        "LEFT JOIN productos p ON p.proveedor_id=pr.id AND p.activo=1 "
        "WHERE pr.activo=1 GROUP BY pr.id ORDER BY pr.nombre").fetchall()
    editar = None
    if request.args.get("editar"):
        editar = con.execute("SELECT * FROM proveedores WHERE id=?", (request.args["editar"],)).fetchone()
    return render_template("proveedores.html", lista=lista, editar=editar)


@app.post("/proveedores/guardar")
@admin_required
def proveedores_guardar():
    f = request.form
    nombre = f.get("nombre", "").strip()
    if not nombre:
        flash("El nombre del proveedor es obligatorio", "error")
        return redirect(url_for("proveedores"))
    datos = (nombre, f.get("contacto", "").strip(), f.get("telefono", "").strip(), f.get("notas", "").strip())
    con = db()
    if f.get("id"):
        con.execute("UPDATE proveedores SET nombre=?, contacto=?, telefono=?, notas=? WHERE id=?",
                    datos + (f["id"],))
    else:
        con.execute("INSERT INTO proveedores (nombre, contacto, telefono, notas) VALUES (?,?,?,?)", datos)
    con.commit()
    flash("Proveedor guardado", "ok")
    return redirect(url_for("proveedores"))


@app.post("/proveedores/<int:pid>/eliminar")
@admin_required
def proveedores_eliminar(pid):
    con = db()
    con.execute("UPDATE productos SET proveedor_id=NULL WHERE proveedor_id=?", (pid,))
    con.execute("UPDATE proveedores SET activo=0 WHERE id=?", (pid,))
    con.commit()
    flash("Proveedor eliminado", "ok")
    return redirect(url_for("proveedores"))


# ---------- Merma (admin y vendedor) ----------
@app.route("/merma")
@login_required
def merma():
    hoy = date.today()
    desde = request.args.get("desde") or hoy.replace(day=1).isoformat()
    hasta = request.args.get("hasta") or hoy.isoformat()
    con = db()
    lista = con.execute(
        "SELECT m.*, p.nombre producto, u.nombre usuario FROM mermas m "
        "JOIN productos p ON p.id=m.producto_id JOIN usuarios u ON u.id=m.usuario_id "
        "WHERE date(m.fecha) BETWEEN ? AND ? ORDER BY m.id DESC", (desde, hasta)).fetchall()
    perdida = sum(r["cantidad"] * r["costo"] for r in lista)
    prods = [dict(r) for r in con.execute(
        "SELECT id, nombre, stock FROM productos WHERE activo=1 ORDER BY nombre")]
    editar = None
    if request.args.get("editar"):
        editar = con.execute(
            "SELECT m.*, p.nombre producto FROM mermas m JOIN productos p ON p.id=m.producto_id "
            "WHERE m.id=?", (request.args["editar"],)).fetchone()
    return render_template("merma.html", lista=lista, perdida=perdida, prods=prods,
                           editar=editar, desde=desde, hasta=hasta)


@app.post("/merma/guardar")
@login_required
def merma_guardar():
    f = request.form
    con = db()
    try:
        try:
            cant = int(f["cantidad"])
        except (ValueError, KeyError):
            raise Aviso("Escribe una cantidad válida")
        if cant <= 0:
            raise Aviso("La cantidad debe ser mayor a 0")
        motivo = f.get("motivo") if f.get("motivo") in MOTIVOS else "Otro"
        nota = f.get("nota", "").strip()
        if f.get("id"):
            m = con.execute("SELECT * FROM mermas WHERE id=?", (f["id"],)).fetchone()
            if not m:
                raise Aviso("Merma no encontrada")
            p = con.execute("SELECT * FROM productos WHERE id=?", (m["producto_id"],)).fetchone()
            diff = cant - m["cantidad"]
            if diff > p["stock"]:
                raise Aviso(f"Solo quedan {p['stock']} unidades más en stock")
            con.execute("UPDATE productos SET stock=stock-? WHERE id=?", (diff, p["id"]))
            con.execute("UPDATE mermas SET cantidad=?, motivo=?, nota=? WHERE id=?",
                        (cant, motivo, nota, m["id"]))
        else:
            p = con.execute("SELECT * FROM productos WHERE id=? AND activo=1",
                            (f.get("producto_id"),)).fetchone()
            if not p:
                raise Aviso("Elige un producto de la lista")
            if cant > p["stock"]:
                raise Aviso(f"Solo hay {p['stock']} de {p['nombre']} en stock")
            con.execute(
                "INSERT INTO mermas (fecha, producto_id, cantidad, motivo, nota, costo, usuario_id) "
                "VALUES (?,?,?,?,?,?,?)",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), p["id"], cant, motivo, nota,
                 p["costo"], session["uid"]))
            con.execute("UPDATE productos SET stock=stock-? WHERE id=?", (cant, p["id"]))
        con.commit()
        flash("Merma guardada y stock actualizado", "ok")
    except Aviso as e:
        con.rollback()
        flash(str(e), "error")
    return redirect(url_for("merma"))


@app.post("/merma/<int:mid>/eliminar")
@admin_required
def merma_eliminar(mid):
    con = db()
    m = con.execute("SELECT * FROM mermas WHERE id=?", (mid,)).fetchone()
    if m:
        con.execute("UPDATE productos SET stock=stock+? WHERE id=?", (m["cantidad"], m["producto_id"]))
        con.execute("DELETE FROM mermas WHERE id=?", (mid,))
        con.commit()
        flash("Merma eliminada y stock devuelto", "ok")
    return redirect(url_for("merma"))


# ---------- Ventas y tickets ----------
@app.route("/ventas")
@admin_required
def ventas():
    hoy = date.today().isoformat()
    desde = request.args.get("desde") or hoy
    hasta = request.args.get("hasta") or hoy
    con = db()
    lista = con.execute(
        "SELECT v.*, u.nombre vendedor FROM ventas v JOIN usuarios u ON u.id=v.usuario_id "
        "WHERE date(v.fecha) BETWEEN ? AND ? ORDER BY v.id DESC", (desde, hasta)).fetchall()
    por_metodo = con.execute(
        "SELECT metodo, SUM(total) t, COUNT(*) c FROM ventas "
        "WHERE date(fecha) BETWEEN ? AND ? AND estado='ok' GROUP BY metodo", (desde, hasta)).fetchall()
    total = sum(r["t"] for r in por_metodo)
    return render_template("ventas.html", lista=lista, por_metodo=por_metodo,
                           total=total, desde=desde, hasta=hasta)


@app.route("/ticket/<int:vid>")
@login_required
def ticket(vid):
    con = db()
    v = con.execute(
        "SELECT v.*, u.nombre vendedor FROM ventas v JOIN usuarios u ON u.id=v.usuario_id WHERE v.id=?",
        (vid,)).fetchone()
    if not v:
        flash("Factura no encontrada", "error")
        return redirect(url_for("caja"))
    items = con.execute("SELECT * FROM venta_items WHERE venta_id=?", (vid,)).fetchall()
    return render_template("ticket.html", v=v, items=items)


@app.post("/ventas/<int:vid>/anular")
@admin_required
def anular(vid):
    con = db()
    v = con.execute("SELECT estado FROM ventas WHERE id=?", (vid,)).fetchone()
    if v and v["estado"] == "ok":
        for it in con.execute("SELECT producto_id, cantidad FROM venta_items WHERE venta_id=?", (vid,)):
            con.execute("UPDATE productos SET stock=stock+? WHERE id=?", (it["cantidad"], it["producto_id"]))
        con.execute("UPDATE ventas SET estado='anulada' WHERE id=?", (vid,))
        con.commit()
        flash(f"Factura #{vid} anulada y stock devuelto", "ok")
    return redirect(request.referrer or url_for("ventas"))


# ---------- Reportes (admin) ----------
def _periodo():
    hoy = date.today()
    return (request.args.get("desde") or hoy.replace(day=1).isoformat(),
            request.args.get("hasta") or hoy.isoformat())


@app.route("/reportes")
@admin_required
def reportes():
    desde, hasta = _periodo()
    con = db()
    P = (desde, hasta)
    V = "v.estado='ok' AND date(v.fecha) BETWEEN ? AND ?"
    r = con.execute(f"SELECT COALESCE(SUM(v.total),0) total, COUNT(*) n FROM ventas v WHERE {V}", P).fetchone()
    costo = con.execute(
        f"SELECT COALESCE(SUM(vi.cantidad*vi.costo),0) FROM venta_items vi "
        f"JOIN ventas v ON v.id=vi.venta_id WHERE {V}", P).fetchone()[0]
    perdida = con.execute(
        "SELECT COALESCE(SUM(cantidad*costo),0) FROM mermas WHERE date(fecha) BETWEEN ? AND ?", P).fetchone()[0]
    ganancia = r["total"] - costo
    datos = dict(
        desde=desde, hasta=hasta, total=r["total"], n=r["n"],
        promedio=(r["total"] / r["n"] if r["n"] else 0),
        costo=costo, ganancia=ganancia, perdida=perdida, neta=ganancia - perdida,
        por_dia=con.execute(
            f"SELECT date(v.fecha) dia, COUNT(*) n, SUM(v.total) t FROM ventas v WHERE {V} "
            "GROUP BY dia ORDER BY dia", P).fetchall(),
        por_cat=con.execute(
            f"SELECT p.categoria, SUM(vi.cantidad) u, SUM(vi.subtotal) t FROM venta_items vi "
            f"JOIN ventas v ON v.id=vi.venta_id JOIN productos p ON p.id=vi.producto_id "
            f"WHERE {V} GROUP BY p.categoria ORDER BY t DESC", P).fetchall(),
        por_vend=con.execute(
            f"SELECT u.nombre, COUNT(*) n, SUM(v.total) t FROM ventas v JOIN usuarios u ON u.id=v.usuario_id "
            f"WHERE {V} GROUP BY u.id ORDER BY t DESC", P).fetchall(),
        por_met=con.execute(
            f"SELECT v.metodo, COUNT(*) n, SUM(v.total) t FROM ventas v WHERE {V} "
            "GROUP BY v.metodo ORDER BY t DESC", P).fetchall(),
        top=con.execute(
            f"SELECT vi.nombre, SUM(vi.cantidad) u, SUM(vi.subtotal) t, "
            f"SUM(vi.subtotal - vi.cantidad*vi.costo) g FROM venta_items vi "
            f"JOIN ventas v ON v.id=vi.venta_id WHERE {V} GROUP BY vi.producto_id "
            "ORDER BY u DESC LIMIT 10", P).fetchall(),
        mermas=con.execute(
            "SELECT motivo, SUM(cantidad) u, SUM(cantidad*costo) t FROM mermas "
            "WHERE date(fecha) BETWEEN ? AND ? GROUP BY motivo ORDER BY t DESC", P).fetchall(),
        inv=con.execute(
            "SELECT COALESCE(SUM(stock*costo),0) costo, COALESCE(SUM(stock*precio),0) venta, "
            "COALESCE(SUM(stock),0) unidades FROM productos WHERE activo=1").fetchone(),
    )
    return render_template("reportes.html", **datos)


@app.route("/reportes/ventas.csv")
@admin_required
def reportes_csv():
    desde, hasta = _periodo()
    rows = db().execute(
        "SELECT v.id, v.fecha, u.nombre vendedor, v.metodo, v.estado, vi.nombre, vi.cantidad, "
        "vi.precio, vi.subtotal FROM venta_items vi JOIN ventas v ON v.id=vi.venta_id "
        "JOIN usuarios u ON u.id=v.usuario_id WHERE date(v.fecha) BETWEEN ? AND ? ORDER BY v.id",
        (desde, hasta)).fetchall()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Factura", "Fecha", "Vendedor", "Pago", "Estado", "Producto", "Cantidad", "Precio", "Subtotal"])
    for r in rows:
        w.writerow(list(r))
    return Response("\ufeff" + out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=ventas_{desde}_{hasta}.csv"})


# ---------- Usuarios (admin) ----------
@app.route("/usuarios")
@admin_required
def usuarios():
    con = db()
    lista = con.execute("SELECT * FROM usuarios WHERE activo=1 ORDER BY nombre").fetchall()
    editar = None
    if request.args.get("editar"):
        editar = con.execute("SELECT * FROM usuarios WHERE id=?", (request.args["editar"],)).fetchone()
    return render_template("usuarios.html", lista=lista, editar=editar)


@app.post("/usuarios/guardar")
@admin_required
def usuarios_guardar():
    f = request.form
    pw = f.get("password", "")
    rol = f.get("rol") if f.get("rol") in ROLES else "vendedor"
    con = db()
    if f.get("id"):
        uid = int(f["id"])
        if uid == session["uid"]:
            rol = "admin"  # no te puedes quitar el rol a ti mismo
        if pw and len(pw) < 4:
            flash("La contraseña debe tener al menos 4 caracteres", "error")
            return redirect(url_for("usuarios", editar=uid))
        con.execute("UPDATE usuarios SET rol=? WHERE id=?", (rol, uid))
        if pw:
            con.execute("UPDATE usuarios SET password=? WHERE id=?", (generate_password_hash(pw), uid))
        con.commit()
        flash("Usuario actualizado", "ok")
        return redirect(url_for("usuarios"))
    usuario = f.get("usuario", "").strip().lower()
    if not usuario or len(pw) < 4:
        flash("Escribe el usuario y una contraseña de al menos 4 caracteres", "error")
        return redirect(url_for("usuarios"))
    try:
        con.execute("INSERT INTO usuarios (usuario, nombre, password, rol) VALUES (?,?,?,?)",
                    (usuario, usuario.capitalize(), generate_password_hash(pw), rol))
        con.commit()
        flash("Usuario creado", "ok")
    except sqlite3.IntegrityError:
        flash("Ese usuario ya existe", "error")
    return redirect(url_for("usuarios"))


@app.post("/usuarios/<int:uid>/eliminar")
@admin_required
def usuarios_eliminar(uid):
    if uid == session["uid"]:
        flash("No puedes eliminar tu propio usuario", "error")
    else:
        con = db()
        con.execute("UPDATE usuarios SET activo=0 WHERE id=?", (uid,))
        con.commit()
        flash("Usuario eliminado", "ok")
    return redirect(url_for("usuarios"))


init_db()

if __name__ == "__main__":
    if "--web" in sys.argv:  # modo navegador para depurar: python app.py --web
        app.run(debug=True)
    else:
        from flaskwebgui import FlaskUI
        FlaskUI(app=app, server="flask", width=1280, height=800).run()
