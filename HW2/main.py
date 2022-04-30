import sqlite3
import os
from flask import *

DATABASE = "HWDB.db"
SCHEMA = 'schema.sql'

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)


def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


def init_db():
    with app.app_context():
        db = get_db()
        with app.open_resource(SCHEMA, mode='r') as f:
            db.cursor().executescript(f.read())  # executescript can run multiple commands
        db.commit()


@app.route("/")
def home():
    '''
    redirect user to index.html ie sign-in page
    '''
    return redirect("/index.html")


@app.route("/index.html")
def index():
    return render_template("index.html")


@app.route("/login", methods=['POST'])
def login():
    account = request.form['Account']
    passward = request.form['password']


@app.route("/sign-up.html")
def sign_up():
    return render_template("sign-up.html")


@app.route("/register", methods=['POST'])
def register():
    name = request.form['name']
    phonenumber = request.form['phonenumber']
    Account = request.form['Account']
    password = request.form['password']
    if password != request.form['re-password']:
        # sign-up fail
        pass
    latitude = request.form['latitude']
    longitude = request.form['longitude']


@app.route("/nav.html")
def nav():
    return render_template("nav.html")


def main():
    init_db()
    app.run(debug=True)


if __name__ == '__main__':
    main()
