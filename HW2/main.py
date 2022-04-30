import sqlite3
import os
import hashlib
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
    return redirect(url_for('index'))


@app.route("/index.html")
def index():
    return render_template("index.html")


@app.route("/login", methods=['POST'])
def login():
    Account = request.form['Account']
    password = request.form['password']
    # hash password
    password = hashlib.sha256((password + Account).encode()).hexdigest()

    db = get_db()
    for login_info in db.cursor().execute("select U_account, U_password from Users"):
        if (Account, password) == login_info:
            # successfull
            user_info = next(iter(db.cursor().execute(
                """select U_name, U_type, U_phone, U_balance, U_latitude, U_longitude
                   from Users 
                   where U_account = ?
                   and   U_password = ?""", (Account, password))))
            user_info = {
                'U_name': user_info[0],
                'U_type': 'owner' if user_info[1] else 'user',
                'U_phone': user_info[2],
                'U_balance': user_info[3],
                'U_latitude': user_info[4],
                'U_longitude': user_info[5],
            }
            # login successfully
            session['user_info'] = user_info
            return redirect(url_for('nav'))

    flash("Login failed, please try again")
    return redirect(url_for('index'))


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
        flash("Please check: password and re-password need to be the same!")
        return redirect(url_for("sign_up"))
    latitude = request.form['latitude']
    longitude = request.form['longitude']

    # check any blanks:
    for e in (Account, password, name, latitude, longitude, phonenumber):
        if e == '':
            flash("Please make sure all fields are filled in")
            return redirect(url_for("sign_up"))

    # check format of Account/Password/Phone/Name/Locations:
    # account
    for c in Account:
        if not (c.isdigit() or c.isalpha()):
            flash("Please check: Account can only contain letters and numbers")
            return redirect(url_for("sign_up"))
    # pwd
    for c in password:
        if not (c.isdigit() or c.isalpha()):
            flash("Please check: password can only contain letters and numbers")
            return redirect(url_for("sign_up"))
    # phone
    if len(phonenumber) != 10 or not phonenumber.isdigit():
        flash("Please check: phone number can only contain 10 digits")
        return redirect(url_for("sign_up"))
    # name
    if len(name.split()) != 2:
        flash("Please check: please fill in first name and last name")
        return redirect(url_for("sign_up"))
    for c in name:
        if not (c.isalpha() or c == ' '):
            flash("Please check: name can only contain letters and spaces")
            return redirect(url_for("sign_up"))
    # latitude and longitude
    try:
        latitude = float(latitude)
        longitude = float(longitude)
    except ValueError:
        flash("Please check: locations can only be float")
        return redirect(url_for("sign_up"))

    # hash password + salt (account) before storing it
    password = hashlib.sha256((password + Account).encode()).hexdigest()

    db = get_db()
    try:
        db.cursor().execute('''
            insert into Users (U_account, U_password, U_name, U_type, U_latitude, U_longitude, U_phone, U_balance)
            values (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (Account, password, name, 0, latitude, longitude, phonenumber, 0))
    except sqlite3.IntegrityError:
        flash("User account is already registered, please try another account")
        return redirect(url_for("sign_up"))
    db.commit()
    flash("Registered Successfully, you may login now")
    return redirect(url_for("index"))


@app.route("/nav.html")
def nav():
    user_info = session.get('user_info', None)
    return render_template("nav.html", user_info=user_info)


def main():
    init_db()
    app.run(debug=True)


if __name__ == '__main__':
    main()
