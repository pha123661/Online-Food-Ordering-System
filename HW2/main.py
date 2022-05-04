import sqlite3
import os
import hashlib
from flask import (
    Flask, render_template, g, request,
    session, flash, redirect, url_for,
    json, jsonify,
)

DATABASE = "HWDB.db"
SCHEMA = 'schema.sql'

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(99)


def get_db():
    '''
    helper function to get database connection
    '''
    db = getattr(g, '_database', None)
    if db is None:
        db = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
        g._database = db
    return db


@app.teardown_appcontext
def close_connection(exception):
    '''
    close database after session ends
    '''
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


def init_db():
    '''
    initialize database
    '''
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
    '''
    renders login page
    '''
    return render_template("index.html")


@app.route("/login", methods=['POST'])
def login():
    Account = request.form['Account']
    password = request.form['password']
    # hash password
    password = hashlib.sha256((password + Account).encode()).hexdigest()

    # check if user in stored in database
    db = get_db()
    user_info = db.cursor().execute(""" select *
                                        from Users
                                        where U_account = ?
                                        and   U_password = ?""", (Account, password)).fetchone()
    if user_info is None:
        # login failed
        flash("Login failed, please try again")
        return redirect(url_for('index'))
    else:
        # login successfully
        session['user_info'] = dict(user_info)
        return redirect(url_for('nav'))


@app.route("/sign-up.html")
def sign_up():
    return render_template("sign-up.html")


@app.route("/register-account-check", methods=['POST'])
def register_account_check():
    '''
    checks if account is already registered
    helper function handling ajax request
    '''
    account = request.form.get('Account')
    db = get_db()
    rst = db.cursor().execute(
        "select U_account from Users where U_account = ?", (account,)).fetchone()

    # empty string
    if account is None or account == '':
        response = jsonify(
            '<span style=\'color:red;\'>Please enter your account</span>')
    # account used
    elif rst:
        response = jsonify(
            '<span style=\'color:red;\'>Account has been registered</span>')
    else:
        response = jsonify(
            '<span style=\'color:green;\'>Account has not been registered</span>')

    # **Important**
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.status_code = 200
    return response


@app.route("/register", methods=['POST'])
def register():
    # get input values
    name = request.form['name']
    phonenumber = request.form['phonenumber']
    Account = request.form['Account']
    password = request.form['password']
    latitude = request.form['latitude']
    longitude = request.form['longitude']

    # check re-type password
    if password != request.form['re-password']:
        # sign-up fail
        flash("Please check: password and re-password need to be the same!")
        return redirect(url_for("sign_up"))

    # check any blanks:
    for e in (Account, password, name, latitude, longitude, phonenumber):
        if e == '':
            flash("Please make sure all fields are filled in")
            return redirect(url_for("sign_up"))

    # check formats:
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

    # store newly registered user informations
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

    # Register successfully
    flash("Registered Successfully, you may login now")
    return redirect(url_for("index"))


@ app.route("/nav.html")
def nav():
    user_info = session.get('user_info', None)
    if user_info is None:
        # not logged in
        flash("Please login first")
        return redirect(url_for("index"))
    return render_template("nav.html", user_info=user_info)


def main():
    init_db()
    app.run(debug=True)


if __name__ == '__main__':
    main()
