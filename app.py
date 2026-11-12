from flask import Flask, render_template, request, redirect
from flaskwebgui import FlaskUI

app = Flask(__name__)

@app.route("/")
def login():
    return render_template("login.html")

@app.route("/login", methods=["POST"])
def procesar_login():
    usuario = request.form['username']
    #SQL para verificar usuario y contraseña
    return redirect("/inventario")

@app.route("/inventario")
def inventario():
    return render_template("inventario.html")

@app.route("/caja")
def caja():
    return "<h1>Caja</h1>"

if __name__ == "__main__":
    FlaskUI(app=app, server="flask", width=1100, height=700).run()