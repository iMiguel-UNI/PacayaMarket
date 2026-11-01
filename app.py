from flask import Flask, render_template
from flaskwebgui import FlaskUI

app = Flask(__name__)

# Ruta principal que carga tu HTML
@app.route("/")
def inicio():
    return render_template("index.html")

if __name__ == "__main__":
    # Arrancamos la ventana nativa de escritorio
    FlaskUI(app=app, server="flask", width=1000, height=600).run()