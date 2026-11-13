from flask import Flask, render_template, request, redirect
from flaskwebgui import FlaskUI
import sqlite3  # 1. Importamos la librería de SQLite (ya viene instalada en Python)

app = Flask(__name__)

# 2. Creamos una función para conectarnos fácilmente a la base de datos
def get_db_connection():
    # Usamos el nombre exacto de tu archivo
    conn = sqlite3.connect('MinMarketPacaya.db')
    # Esto es clave: nos permite acceder a los datos por el nombre de la columna (ej: fila['nombre'])
    conn.row_factory = sqlite3.Row
    return conn

@app.route("/")
def login():
    return render_template("login.html")

@app.route("/login", methods=["POST"])
def procesar_login():
    usuario = request.form['username']
    
    # 3. Ejemplo de cómo usarás la conexión para validar el login pronto:
    # conn = get_db_connection()
    # usuario_db = conn.execute("SELECT * FROM USUARIO WHERE username = ?", (usuario,)).fetchone()
    # conn.close()
    
    return redirect("/inventario")

@app.route("/inventario")
def inventario():
    # Cuando quieras mostrar los productos, harás algo así:
    # conn = get_db_connection()
    # productos = conn.execute("SELECT * FROM PRODUCTO").fetchall()
    # conn.close()
    
    return render_template("inventario.html")

@app.route("/caja")
def caja():
    try:
        # 1. Intentamos abrir la conexión
        conn = get_db_connection()
        
        # 2. Hacemos una consulta real a la tabla USUARIO
        usuarios = conn.execute('SELECT * FROM USUARIO').fetchall()
        conn.close()
        
        # 3. Si todo sale bien, armamos un texto con los nombres
        html = "<h1>✅ Conexión Exitosa</h1>"
        html += "<p>Usuarios encontrados en la base de datos:</p><ul>"
        
        for u in usuarios:
            html += f"<li>{u['nombre']} (Usuario: {u['username']})</li>"
        
        html += "</ul>"
        return html
        
    except Exception as e:
        # Si algo falla (ej. archivo no encontrado o nombre de tabla mal), te muestra el error
        return f"<h1>❌ Error conectando a la BD:</h1><p>{e}</p>"   
if __name__ == "__main__":
    FlaskUI(app=app, server="flask", width=1100, height=700).run() 