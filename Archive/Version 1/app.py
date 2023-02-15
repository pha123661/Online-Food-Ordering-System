import sqlite3
import os
import hashlib
from functools import wraps
import base64
from flask import (
    Flask, render_template, g, request,
    session, flash, redirect, url_for,
    json, jsonify,
)

DATABASE = "HWDB.db"
SCHEMA = 'schema.sql'

# distance boundary
DISTANCE_BOUNDARY = {'medium': 5, 'far': 10}

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


def login_required(function):
    '''
    function wrapper that checks login status
    '''
    @wraps(function)
    def wrap(*args, **kwargs):
        user_info = session.get('user_info', None)
        if user_info is None:
            # not logged in
            flash("Please login first")
            return redirect(url_for("index"))
        else:
            # logged in
            return function(*args, **kwargs)
    return wrap


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
    user_info = db.cursor().execute(
        """ select *
            from Users
            where U_account = ? and U_password = ?""", (Account, password)
    ).fetchone()
    if user_info is None:
        # login failed
        flash("Login failed, please try again")
        return redirect(url_for('index'))
    else:
        # login successfully
        session['user_info'] = dict(user_info)
        return redirect(url_for('nav'))


@app.route("/logout", methods=['POST'])
@login_required
def logout():
    session['user_info'] = None
    flash("Logged out")
    return redirect(url_for('index'))


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
    for k, v in request.form.items():
        if v == '':
            flash(f"Please check: '{k}' is not filled")
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
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        flash("Please check: latitude and longitude must be in range")
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


@app.route('/get_session', methods=['GET'])
def get_session():
    if request.method == 'GET':
        data = {}
        try:
            data['user_info'] = session['user_info']
        except:
            print('fail to get session')
        return jsonify(data)
    else:
        return jsonify({'user_info': 'nothing'})


def search_menu(SID, upper, lower, meal):
    db = get_db()
    rst = db.cursor().execute('''
        select P_image, P_name, P_price, P_quantity, P_imagetype
        from Products
        where P_store = ? and P_price <= ? and P_price >= ? and instr(lower(P_name), lower(?)) > 0
        ''', (SID, upper, lower, meal)).fetchall()
    # instr(a, b) > 0 means if a contains substring b
    return [{'P_image': base64.b64encode(P_image).decode(), 'P_name': P_name, 'P_price': P_price, 'P_quantity': P_quantity, 'P_imagetype': P_imagetype}
            for P_image, P_name, P_price, P_quantity, P_imagetype in rst]


@app.route("/search-shops", methods=['POST'])
def search_shops():
    search = {i: request.form[i] for i in [
        'shop', 'sel1', 'price_low', 'price_high', 'meal', 'category', 'U_lat', 'U_lon']}
    desc = 'desc' if request.form["desc"] == 'true' else ''
    search['medium'] = DISTANCE_BOUNDARY['medium']
    search['far'] = DISTANCE_BOUNDARY['far']
    db = get_db()
    rst = db.cursor().execute(
        f'''
        with dis(SID, manhattan) as (
                select SID, ABS(S_latitude - :U_lat) + ABS(S_longitude - :U_lon) as manhattan
                from Stores
            ),
            dis_cat(SID, distance) as (
                select SID, case 
                    when manhattan >= :far then 'far'
                    when manhattan >= :medium then 'medium'
                    else 'near'
                end as distance
                from Stores natural join dis
            )

        select SID, S_name, S_foodtype, distance
        from Stores natural join dis natural join dis_cat
        where instr(lower(S_name), lower(:shop)) > 0
        and instr(lower(S_foodtype), lower(:category)) > 0
        and distance like :sel1
        order by {request.form['ordering']}
        ''' + desc,
        search
    ).fetchall()
    # instr(a, b) > 0 means if a contains substring b
    # latitude and longitude are checked, ordering is a list(user can only select), so don't worry about SQL injection
    table = {'tableRow': []}
    append = table['tableRow'].append
    for SID, S_name, S_foodtype, distance in rst:
        menu = search_menu(
            SID, search['price_high'], search['price_low'], search['meal'])
        if menu:
            append({'shop_name': S_name, 'foodtype': S_foodtype, 'distance': distance,
                    'menu': menu})
    response = jsonify(table)
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.status_code = 200
    return response


@app.route("/nav.html")
@login_required
def nav():
    # update session info every time
    user_info = session.get('user_info')
    UID = user_info['UID']
    db = get_db()
    user_info = db.cursor().execute(
        """ select *
            from Users
            where UID = ?""", (UID,)
    ).fetchone()
    session['user_info'] = dict(user_info)

    # fetch shop_info
    db = get_db()
    shop_info = db.cursor().execute(
        """ select *
            from Stores
            where S_owner = ?""", (UID,)
    ).fetchone()

    # fetch product_info
    db = get_db()
    product_info = db.cursor().execute(
        """ select *
            from Products
            where P_owner = ?""", (UID,)
    ).fetchall()

    image_info = [tple[4].decode("utf-8") for tple in product_info]
    # print(image_info)

    return render_template("nav.html", user_info=user_info, shop_info=shop_info, product_info=product_info, image_info=image_info)


@app.route("/edit_location", methods=['POST'])
@login_required
def edit_location():
    user_info = session.get('user_info')
    UID = user_info['UID']
    latitude = request.form['latitude']
    longitude = request.form['longitude']

    # check any blanks:
    for k, v in request.form.items():
        if v == '':
            flash(f"Please check: '{k}' is not filled")
            return redirect(url_for("nav"))

    # check validity
    try:
        latitude, longitude = float(latitude), float(longitude)
    except ValueError:
        flash("Please check: locations can only be float")
        return redirect(url_for("nav"))

    if not (-90 <= int(latitude) <= 90 and -180 <= int(longitude) <= 180):
        flash("Please check: locations not possible")
        return redirect(url_for("nav"))

    # update location
    db = get_db()
    db.cursor().execute("""
        update Users
        set U_latitude = ?, U_longitude = ?
        where UID = ?
    """, (latitude, longitude, UID))
    db.commit()

    return redirect(url_for('nav'))


@app.route("/shop_register", methods=['POST'])
@login_required
def shop_register():
    # get input values
    user_info = session.get('user_info')
    UID = user_info['UID']
    owner_phone = user_info['U_phone']
    shop_name = request.form['shop_name']
    shop_category = request.form['shop_category']
    shop_latitude = request.form['shop_latitude']
    shop_longitude = request.form['shop_longitude']

    # check any blanks:
    for k, v in request.form.items():
        if v == '':
            flash(f"Please check: '{k}' is not filled")
            return redirect(url_for("nav"))

    # check formats:
    # latitude and longitude
    try:
        latitude = float(shop_latitude)
        longitude = float(shop_longitude)
    except ValueError:
        flash("Please check: locations can only be float")
        return redirect(url_for("nav"))

    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        flash("Please check: locations not possible")
        return redirect(url_for("nav"))

    # store newly registered store informations
    db = get_db()
    try:
        shop_info = db.cursor().execute('''
            insert into Stores (S_name, S_latitude, S_longitude, S_phone, S_foodtype, S_owner)
            values (?, ?, ?, ?, ?, ?)
        ''', (shop_name, latitude, longitude, owner_phone, shop_category, UID))
        #print(shop_name, latitude, longitude, owner_phone, shop_category, UID)
    except sqlite3.IntegrityError:
        flash("shop name has been registered !!")
        return redirect(url_for("nav"))
    session['shop_info'] = dict(shop_info)
    db.commit()

    # change user's type to owner
    db = get_db()
    try:
        user_info = db.cursor().execute('''
            update Users
            set U_type = ?
            where UID = ?
        ''', (1, UID))
    except sqlite3.IntegrityError:
        flash("show owner update failed")
        return redirect(url_for("nav"))
    #session['user_info'] = dict(user_info)
    db.commit()

    # Register successfully
    flash("Shop registered successfully")
    return redirect(url_for("nav"))


@app.route("/register-shop_name-check", methods=['POST'])
def register_shop_name_check():
    '''
    checks if shop_name is already registered
    helper function handling ajax request
    '''
    shop_name = request.form.get('shop_name')
    db = get_db()
    rst = db.cursor().execute(
        "select S_name from Stores where S_name = ?", (shop_name,)).fetchone()

    # empty string
    if shop_name is None or shop_name == '':
        response = jsonify(
            '<span style=\'color:red;\'>Please enter your shop name</span>')
    # account used
    elif rst:
        response = jsonify(
            '<span style=\'color:red;\'>Shop name has been registered</span>')
    else:
        response = jsonify(
            '<span style=\'color:green;\'>Shop name has not been registered</span>')

    # **Important**
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.status_code = 200
    return response


@app.route("/shop_add", methods=['POST'])
@login_required
def shop_add():
    # get input values
    user_info = session.get('user_info')
    UID = user_info['UID']
    meal_name = request.form['meal_name']
    meal_price = request.form['meal_price']
    meal_quantity = request.form['meal_quantity']
    meal_pic = request.files['meal_pic']    # image file

    # check if user is owner
    if(user_info['U_type'] == 0):
        flash("Please register your store first")
        return redirect(url_for("nav"))

    # fetch shop_info
    db = get_db()
    shop_info = db.cursor().execute(
        """ select *
            from Stores
            where S_owner = ?""", (UID,)
    ).fetchone()
    SID = shop_info['SID']

    # check any blanks:
    for k, v in request.form.items():
        if v == '':
            flash(f"Please check: '{k}' is not filled")
            return redirect(url_for("nav"))
    if(meal_pic.filename == ''):
        flash("Please upload a picture for the product")
        return redirect(url_for("nav"))

    # get the extension of the file ex: png, jpeg
    meal_pic_extension = meal_pic.filename.split('.')[1]

    # check formats:
    # price and quantity
    if(int(meal_price) < 0 or int(meal_quantity) < 0):
        flash("Please check: price and quantity can only be non-negatives")
        return redirect(url_for("nav"))

    # store newly added product informations
    db = get_db()
    try:
        db.cursor().execute('''
            insert into Products (P_name, P_price, P_quantity, P_image, P_imagetype, P_owner, P_store)
            values (?, ?, ?, ?, ?, ?, ?)
        ''', (meal_name, meal_price, meal_quantity, base64.b64encode(meal_pic.read()), meal_pic_extension, UID, SID))
    except sqlite3.IntegrityError:
        #print("something went wrong!!")
        flash(" oops something went wrong!!")
        return redirect(url_for("nav"))
    # session['product_info'] = dict(product_info)       # not sure if needed
    db.commit()

    # Register successfully
    flash("Product added successfully")
    return redirect(url_for("nav"))


@app.route("/edit_price_and_quantity", methods=['POST'])
def edit_price_and_quantity():
    #print("inside edit_price_and_quantity")
    edit_price = request.form['edit_price']
    edit_quantity = request.form['edit_quantity']
    edit_PID = request.form['edit_PID']

    # check any blanks:
    for k, v in request.form.items():
        if v == '':
            flash(f"Please check: '{k}' is not filled")
            return redirect(url_for("nav"))

    # check formats:
    # price and quantity
    if(int(edit_price) < 0 or int(edit_quantity) < 0):
        flash("Please check: price and quantity can only be non-negatives")
        return redirect(url_for("nav"))

    # update price & quantity
    db = get_db()
    db.cursor().execute("""
        update Products
        set P_price = ?, P_quantity = ?
        where PID = ?
    """, (edit_price, edit_quantity, edit_PID))
    #print("edit_PID: ", edit_PID)
    db.commit()

    flash("Edit Successful")
    return redirect(url_for('nav'))


@app.route("/delete_product", methods=['POST'])
def delete_product():
    #print("In delete_product")
    delete_PID = request.form['delete_PID']

    # delete product from Products db
    db = get_db()
    db.cursor().execute("""
        delete from Products
        where PID = ?
    """, (delete_PID,))
    #print("delete_PID: ", delete_PID)
    db.commit()

    flash("Delete Successful")
    return redirect(url_for('nav'))


def main():
    init_db()
    app.run('0.0.0.0', debug=True)


if __name__ == '__main__':
    main()
