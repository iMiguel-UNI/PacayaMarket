from flask import Flask, render_template, request, redirect, session
from flaskwebgui import FlaskUI
import sqlite3

app = Flask(__name__)
app.secret_key = 'pacayita_secreta_123' 

def get_db_connection():
    conn = sqlite3.connect('MinMarketPacaya.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route("/")
def login():
    session.clear()
    return render_template("login.html")

@app.route("/login", methods=["POST"])
def procesar_login():
    usuario = request.form['username']

    return redirect("/inventario")

@app.route("/inventario")
def inventario():
    conn = get_db_connection()
    query = """
        SELECT P.id_producto, P.nombre, P.precio_venta, P.stock, C.nombre_categoria
        FROM PRODUCTO P
        INNER JOIN CATEGORIA C ON P.id_categoria = C.id_categoria
        ORDER BY P.nombre ASC
    """
    productos = conn.execute(query).fetchall()
    conn.close()
    return render_template("inventario.html", productos=productos)

@app.route("/caja")
def caja():
    if 'id_usuario' not in session:
        return redirect("/")
        
    conn = get_db_connection()
    productos = conn.execute("SELECT * FROM PRODUCTO WHERE stock > 0 ORDER BY nombre ASC").fetchall()
    conn.close()
    
    return render_template("caja.html", productos=productos)

@app.route("/inventario")
def inventario():
    conn = get_db_connection()
    
    query = """
        SELECT P.id_producto, P.nombre, P.precio_venta, P.stock, C.nombre_categoria
        FROM PRODUCTO P
        INNER JOIN CATEGORIA C ON P.id_categoria = C.id_categoria
        ORDER BY P.nombre ASC
    """
    productos = conn.execute(query).fetchall()
    conn.close()
    
    return render_template("inventario.html", productos=productos)

@app.route("/caja")
def caja():
    if 'id_usuario' not in session:
        return redirect("/")
        
    conn = get_db_connection()
    productos = conn.execute("SELECT * FROM PRODUCTO WHERE stock > 0 ORDER BY nombre ASC").fetchall()
    conn.close()
    
    return render_template("caja.html", productos=productos)   

if __name__ == "__main__":
    FlaskUI(app=app, server="flask", width=1100, height=700).run()