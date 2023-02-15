import os
import math
import json
import base64
import sqlite3
import hashlib
from functools import wraps
from flask import (
    Flask, render_template, g, request,
    session, flash, redirect, url_for,
    json, jsonify,
)

sqlite3.enable_callback_tracebacks(True)

DATABASE = "HWDB.db"
SCHEMA = 'schema.sql'

# distance boundary
DISTANCE_BOUNDARY = {'medium': 200, 'far': 600}

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
        db.create_function('_GIO_DIS', 4, _distance_between_locations)
        g._database = db
    db.cursor().execute("PRAGMA foreign_keys=ON")
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


def _distance_between_locations(lat1, lon1, lat2, lon2):
    '''
    calculates distance between two locations
    '''

    # approximate radius of earth in km
    R = 6373.0

    lat1 = math.radians(float(lat1))
    lon1 = math.radians(float(lon1))
    lat2 = math.radians(float(lat2))
    lon2 = math.radians(float(lon2))

    dlon = lon2 - lon1
    dlat = lat2 - lat1

    a = math.sin(dlat / 2)**2 + math.cos(lat1) * \
        math.cos(lat2) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    distance = R * c

    return str(distance)


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


@app.route("/order_made", methods=['POST'])
@login_required
def order_made():
    '''
    called when any order has been made
    '''

    json_data = request.json
    '''
    request.json format:
    {
        "PIDs": List[int],
        "Quantities": List[int],
        "S_owner": int,
        "Type": int,
    }
    '''

    # get user data
    UID = session['user_info']['UID']
    db = get_db()
    user_info = db.cursor().execute('''
        select *
        from Users
        where UID = ?
        ''', (UID,)).fetchone()

    # get shop owner UID & shop SID
    shop_owner_UID = json_data['S_owner']
    SID = db.cursor().execute('''
        select SID
        from Stores
        where S_owner = ?
    ''', (shop_owner_UID,)).fetchone()['SID']
    print("shop_owner_UID:", shop_owner_UID)

    # check all ordered products one by one
    Subtotal = 0
    Products = []
    non_sufficient_product_name = []
    for PID, Quantity in zip(json_data['PIDs'], json_data['Quantities']):
        db = get_db()
        rst = db.cursor().execute('''
            select *
            from Products
            where PID = ?
            ''', (PID,)).fetchone()
        # check if product exists
        if rst is None:
            return jsonify({
                'message': 'Failed to create order: one or more products does not exist'
            }), 200
        # product exists, check if product is sufficient
        elif Quantity > rst['P_quantity']:
            non_sufficient_product_name.append(rst['P_name'])
        # calculate subtotal
        Subtotal += rst['P_price'] * Quantity

        rst = dict(rst)
        rst['P_image'] = base64.b64encode(rst['P_image']).decode()
        rst['Order_quantity'] = Quantity
        del rst['P_quantity']  # useless
        Products.append(rst)

    # check if product quantity sufficient
    if len(non_sufficient_product_name) > 0:
        return jsonify({
            'message': "Failed to create order: insufficient quantity of {}".format(
                non_sufficient_product_name)
        }), 200
    # check if wallet ballence sufficient
    # calculate fee
    lat1, lon1 = db.cursor().execute("select U_latitude, U_longitude from Users where UID = ?",
                                     (UID, )).fetchone()
    lat2, lon2 = db.cursor().execute("select S_latitude, S_longitude from Stores where S_owner = ?",
                                     (shop_owner_UID, )).fetchone()
    distance = float(_distance_between_locations(lat1, lon1, lat2, lon2))

    Delivery_fee = 0 if json_data['Type'] == '0' else max(
        int(round(distance * 10)), 10)
    Total = Subtotal + Delivery_fee
    if Total > user_info['U_balance']:
        return jsonify({
            'message': "Failed to create order: insufficient balance"
        }), 200

    # create successful, update database
    try:
        # update Users
        # customer
        db = get_db()
        db.cursor().execute('''
            update Users
            set U_balance = U_balance - ?
            where UID = ?
        ''', (Total, user_info['UID']))
        # shop owner
        db.cursor().execute('''
            update Users
            set U_balance = U_balance + ?
            where UID = ?
        ''', (Total, shop_owner_UID))

        # update Orders
        details_str = json.dumps({
            'Products': Products,
            'Subtotal': Subtotal,
            'Delivery_fee': Delivery_fee,
        })
        rst = db.cursor().execute('''
            insert into Orders (O_status, O_end_time, O_distance, O_amount, O_type, O_details, SID)
            values (?, ?, ?, ?, ?, ?, ?)
        ''', (0, None, distance, Total, json_data['Type'], details_str, SID))

        # update Process_Order
        OID = rst.lastrowid
        db.cursor().execute('''
            insert into Process_Order (UID, OID, PO_type)
            values (?, ?, ?)
        ''', (UID, OID, 0))

        # update Transaction_Record
        # user -> shop
        db.cursor().execute('''
            insert into Transaction_Record (T_action, T_amount, T_Subject, T_Object)
            values (?, ?, ?, ?)
        ''', (0, -Total, UID, shop_owner_UID))
        # shop <- user
        db.cursor().execute('''
            insert into Transaction_Record (T_action, T_amount, T_Subject, T_Object)
            values (?, ?, ?, ?)
        ''', (1, Total, shop_owner_UID, UID))

        # update Products
        for PID, Quantity in zip(json_data['PIDs'], json_data['Quantities']):
            db.cursor().execute('''
                update Products
                set P_quantity = P_quantity - ?
                where PID = ?
            ''', (Quantity, PID))
    except Exception as e:
        print(type(e), str(e))
        db.rollback()
        return jsonify({
            'message': 'Failed to create order: please try again'
        }), 200

    db.commit()

    return jsonify({
        'message': 'Order made successfully'
    }), 200


@app.route("/order_preview", methods=['POST'])
@login_required
def order_preview():
    '''
    called before any order has been made
    caculates the price
    '''
    try:
        PIDs = []
        Quantities = []

        for PID, Q in zip(request.form.getlist('PIDs'), request.form.getlist('Quantities')):
            Q = 0 if Q == '' else int(Q)
            if Q > 0:
                PIDs.append(PID)
                Quantities.append(Q)

        if len(Quantities) == 0:
            return jsonify('Failed to create order: please select at least on product'), 500
    except ValueError:
        return jsonify('Please check: order content must be valid'), 500

    # query product infos
    db = get_db()
    db.cursor().execute("DROP TABLE IF EXISTS PID_list")
    db.cursor().execute("""
        create temp table PID_list(PID INTEGER PRIMARY KEY)
    """)
    for P in PIDs:
        db.cursor().execute("""
        insert into PID_list values (?)
        """, (P, ))

    rst = db.cursor().execute("""
    select * from PID_list natural join Products
    """).fetchall()

    # decode image + calculate price
    if len(rst) != len(Quantities):
        return "Product modified by store, please try again!", 500
    Products = [dict(r) for r in rst]

    Subtotal = 0
    for r, q in zip(Products, Quantities):
        r['P_image'] = base64.b64encode(r['P_image']).decode()
        r['Order_quantity'] = q
        Subtotal += r['P_price'] * q

    # calculate fee
    lat1, lon1 = db.cursor().execute("select U_latitude, U_longitude from Users where UID = ?",
                                     (session['user_info']['UID'], )).fetchone()
    lat2, lon2 = db.cursor().execute("select S_latitude, S_longitude from Stores where S_owner = ?",
                                     (Products[0]['P_owner'], )).fetchone()
    distance = float(_distance_between_locations(lat1, lon1, lat2, lon2))

    Delivery_fee = 0 if request.form['Dilivery'] == '0' else max(
        int(round(distance * 10)), 10)

    db.cursor().execute("drop table PID_list")

    return jsonify({
        'Products': Products,
        'Subtotal': Subtotal,
        'Delivery_fee': Delivery_fee,
        'Distance': distance,
        'Type': request.form['Dilivery'],
        'S_owner': Products[0]['P_owner']
    }), 200


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
        select *
        from Products
        where P_store = ? and P_price <= ? and P_price >= ? and instr(lower(P_name), lower(?)) > 0
        ''', (SID, upper, lower, meal)).fetchall()
    # instr(a, b) > 0 means if a contains substring b

    rst = [dict(r) for r in rst]
    for r in rst:
        r['P_image'] = base64.b64encode(r['P_image']).decode()
    return rst


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
        with dis(SID, gio_dis) as (
                select SID, _GIO_DIS(S_latitude, S_longitude, :U_lat, :U_lon) as gio_dis
                from Stores
            ),
            dis_cat(SID, distance) as (
                select SID, case
                    when gio_dis >= :far then 'far'
                    when gio_dis >= :medium then 'medium'
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


@app.route("/order-detail", methods=['POST'])
def order_detail():
    OID = request.form['OID']
    db = get_db()
    details_str = db.cursor().execute(
        'select O_details from Orders where OID = ?', (OID, )).fetchone()[0]
    details = json.loads(details_str)
    return jsonify(details), 200


@app.route("/search-MyOrders", methods=['POST'])
def search_MyOrders():
    UID = int(request.form['UID'])
    db = get_db()
    rst = db.cursor().execute(
        '''
        select 
            case
                when O_status = 0 then 'Not finished'
                when O_status = 1 then 'Finished'
                else 'Canceled'
            end as Status, 
            strftime('%Y/%m/%d %H:%M', O_start_time) as start_time, 
            case
                when O_end_time is not NULL then strftime('%Y/%m/%d %H:%M', O_end_time)
                else ''
            end as end_time, S_name, OID, O_amount
        from Process_Order natural join Orders natural join Stores
        where UID = ?
        ''', (UID,)
    ).fetchall()
    table = {'tableRow': []}
    append = table['tableRow'].append
    for Status, start_time, end_time, S_name, OID, O_amount in rst:
        append({'Status': Status, 'start_time': start_time, 'end_time': end_time, 'S_name': S_name,
                'OID': OID, 'total_price': O_amount})
    print(table['tableRow'])
    response = jsonify(table)
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.status_code = 200
    return response


@app.route('/search-ShopOrders', methods=['POST'])
def search_ShopOrders():
    UID = int(request.form['UID'])
    db = get_db()
    rst = db.cursor().execute(
        '''
        select SID
        from Stores
        where S_owner = ?
        ''', (UID,)
    ).fetchone()
    table = {'tableRow': []}
    append = table['tableRow'].append
    if rst is not None:
        SID = rst
        rst = db.cursor().execute(
            '''
            select OID,
                case
                    when O_status = 0 then 'Not finished'
                    when O_status = 1 then 'Finished'
                    else 'Canceled'
                end as Status,
                strftime('%Y/%m/%d %H:%M', O_start_time) as start_time, 
                case
                    when O_end_time is not NULL then strftime('%Y/%m/%d %H:%M', O_end_time)
                    else ''
                end as end_time,
                S_name, O_amount
            from Orders natural join Stores
            where SID = ?
            ''', (SID[0],)
        ).fetchall()
        for OID, Status, start_time, end_time, S_name, O_amount in rst:
            append({'Status': Status, 'start_time': start_time, 'end_time': end_time, 'S_name': S_name,
                    'OID': OID, 'total_price': O_amount})
    print(table['tableRow'])
    response = jsonify(table)
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.status_code = 200
    return response


@app.route("/search-transactionRecord", methods=['POST'])
def search_transactionRecord():
    UID = request.form['UID']
    db = get_db()
    rst = db.cursor().execute(
        '''
        with Shop_Name(TID, S_name) as (
                select TID, S_name 
                from Transaction_Record left join Stores
                on T_Object = S_owner
            ),
            Subj_Name(TID, Subj_name) as (
                select TID, U_name as Subj_name
                from Transaction_Record, Users
                where T_Subject = UID
            ),
            Obj_Name(TID, Obj_name) as (
                select TID, U_name as Obj_name
                from Transaction_Record, Users
                where T_Object = UID
            )
        select TID, 
            case 
                when T_action = 2 then 'Recharge'
                when T_action = 1 then 'Recieve'
                when T_action = 0 then 'Payment'
            end as Action, 
            strftime('%Y/%m/%d %H:%M', T_time) as Time,
            case
                when T_action = 2 then Subj_name
                when T_action = 1 and is_refund = 0 then Obj_name
                when T_action = 1 and is_refund = 1 then S_name
                when T_action = 0 and is_refund = 0 then S_name
                when T_action = 0 and is_refund = 1 then Obj_name
            end as Trader,
            T_amount
        from Transaction_Record natural join Subj_Name natural join Obj_Name natural join Shop_Name
        where T_Subject = ?
        ''', (UID,)
    ).fetchall()
    transaction = [{'TID': TID, 'Action': Action, 'Time': Time, 'Trader': Trader, 'T_amount': T_amount}
                   for TID, Action, Time, Trader, T_amount in rst]
    table = {'tableRow': transaction}
    print(table['tableRow'])
    response = jsonify(table)
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.status_code = 200
    return response


@app.route("/order-delete", methods=['POST'])
def order_delete():
    delete_OID = int(request.form['OID'])
    is_shopowner = request.form['is_shopowner']
    print("delete_OID: ", delete_OID, "is_shopowner? ", is_shopowner)
    # get user ID and shop owner ID
    db = get_db()
    customer_ID = db.cursor().execute(
        'select UID from Process_Order where OID = ?', (delete_OID, )
    ).fetchone()[0]
    SID = db.cursor().execute(
        'select SID from Orders where OID = ?', (delete_OID, )
    ).fetchone()[0]
    shop_owner_ID = db.cursor().execute(
        'select S_owner from Stores where SID = ?', (SID, )
    ).fetchone()[0]
    print("customer_ID: ", customer_ID, "shop_owner_ID: ", shop_owner_ID)

    # get canceled order data from db
    rst = db.cursor().execute("""
        select * 
        from Orders 
        where OID = ?
        """, (delete_OID, )).fetchone()

    if rst is None:
        return jsonify('Order not found'), 500
    try:
        # check if order is finished
        if rst['O_status'] == 0:
            # update order status to 'calceled'
            db.cursor().execute(
                'update Orders set O_status = -1 where OID = ?', (delete_OID, )
            )
        else:
            return jsonify('Order is already finished / canceled'), 500
        # update process order status to 'owner canceled' or 'user canceled'
        if is_shopowner == 'true':
            print("Shopowner cancels order")
            db.cursor().execute(
                'update Process_Order set PO_type = 3 where OID = ?', (
                    delete_OID, )
            )
        elif is_shopowner == 'false':
            print("User cancels order")
            db.cursor().execute(
                'update Process_Order set PO_type = 1 where OID = ?', (
                    delete_OID, )
            )
        # refund: add transaction record and update user balance
        # add transaction record: user <- shop
        db.cursor().execute('''
            insert into Transaction_Record (T_action, T_amount, is_refund, T_Subject, T_Object)
            values (?, ?, ?, ?, ?)
        ''', (1, rst['O_amount'], 1, customer_ID, shop_owner_ID))
        # add transaction record: shop -> user
        db.cursor().execute('''
            insert into Transaction_Record (T_action, T_amount, is_refund, T_Subject, T_Object)
            values (?, ?, ?, ?, ?)
        ''', (0, -rst['O_amount'], 1, shop_owner_ID, customer_ID))
        # update user balance
        db.cursor().execute('''
            update Users set U_balance = U_balance + ? where UID = ?
        ''', (rst['O_amount'], customer_ID))
        db.cursor().execute('''
            update Users set U_balance = U_balance - ? where UID = ?
        ''', (rst['O_amount'], shop_owner_ID))

        # update product quantity
        rst = db.cursor().execute('''
            select O_details
            from Orders
            where OID = ?
        ''', (delete_OID, )).fetchone()[0]
        product_details = json.loads(rst)['Products']
        # get all PIDs and Quantities
        PIDs = []
        Quantities = []
        for product in product_details:
            print(product.keys())
            PIDs.append(product['PID'])
            Quantities.append(product['Order_quantity'])

        # add quantity back to product, Note: if PID doesn't exist, this function does nothing(no error)
        for PID, quantity in zip(PIDs, Quantities):
            print(PID, quantity)
            db.cursor().execute(
                'update Products set P_quantity = P_quantity + ? where PID = ?', (
                    quantity, PID)
            )

    except Exception as e:
        print("ERROR : " + str(e))
        db.rollback()
        response = jsonify('cancel order failed')
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.status_code = 500
        return response

    db.commit()
    response = jsonify({'msg': 'cancel order successfully'})
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.status_code = 200
    return response


@app.route("/order-complete", methods=['POST'])
def order_complete():
    complete_OID = int(request.form['OID'])
    print("complete_OID: ", complete_OID)

    # get user ID and shop owner ID
    db = get_db()
    customer_ID = db.cursor().execute(
        'select UID from Process_Order where OID = ?', (complete_OID, )
    ).fetchone()[0]
    SID = db.cursor().execute(
        'select SID from Orders where OID = ?', (complete_OID, )
    ).fetchone()[0]
    shop_owner_ID = db.cursor().execute(
        'select S_owner from Stores where SID = ?', (SID, )
    ).fetchone()[0]
    print("customer_ID: ", customer_ID, "shop_owner_ID: ", shop_owner_ID)

    # get completed order data from db
    rst = db.cursor().execute("""
        select * 
        from Orders 
        where OID = ?
        """, (complete_OID, )).fetchone()

    if rst is None:
        return jsonify('Order not found'), 500
    try:
        # check if order is finished
        if rst['O_status'] == 0:
            # update order status to 'completed' and set end time
            db.cursor().execute('''
                update Orders set O_status = 1, O_end_time = datetime('now', 'localtime') where OID = ?
                ''', (complete_OID, ))
        else:
            return jsonify('Order is already finished / canceled'), 500

        # update process order status to 'order completed'
        db.cursor().execute(
            'update Process_Order set PO_type = 2 where OID = ?', (
                complete_OID, )
        )

    except:
        db.rollback()
        response = jsonify('complete order failed')
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.status_code = 500
        return response

    db.commit()
    response = jsonify({'msg': 'complete order successfully'})
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
    shop_info = db.cursor().execute(
        """ select *
            from Stores
            where S_owner = ?""", (UID,)
    ).fetchone()

    # fetch product_info
    product_info = db.cursor().execute(
        """ select *
            from Products
            where P_owner = ?""", (UID,)
    ).fetchall()

    image_info = [tple['P_image'].decode("utf-8") for tple in product_info]

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
        # print(shop_name, latitude, longitude, owner_phone, shop_category, UID)
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
    # session['user_info'] = dict(user_info)
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
        # print("something went wrong!!")
        flash(" oops something went wrong!!")
        return redirect(url_for("nav"))
    # session['product_info'] = dict(product_info)       # not sure if needed
    db.commit()

    # Register successfully
    flash("Product added successfully")
    return redirect(url_for("nav"))


@app.route("/edit_price_and_quantity", methods=['POST'])
def edit_price_and_quantity():
    edit_price = request.form['edit_price']
    edit_quantity = request.form['edit_quantity']
    edit_PID = request.form['edit_PID']

    # check any blanks:
    for k, v in request.form.items():
        if v == '':
            flash(f"Please check: '{k}' is not filled")
            return redirect(url_for("nav"))

    try:
        int(edit_price)
        int(edit_quantity)
    except ValueError:
        flash("Invalid Value")
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
    db.commit()

    flash("Edit Successful")
    return redirect(url_for('nav'))


@app.route("/delete_product", methods=['POST'])
def delete_product():
    delete_PID = request.form['delete_PID']

    # delete product from Products db
    db = get_db()
    db.cursor().execute("""
        delete from Products
        where PID = ?
    """, (delete_PID,))
    db.commit()

    flash("Delete Successful")
    return redirect(url_for('nav'))


@app.route('/top_up', methods=['POST'])
@login_required
def top_up():
    UID = session['user_info']['UID']
    try:
        value = int(request.form['value'])
        if value <= 0:
            flash('Invalid value')
            return redirect(url_for('nav'))
    except ValueError:
        flash('Invalid value')
        return redirect(url_for('nav'))

    db = get_db()
    # update Users
    db.cursor().execute("""
        update Users
        set U_balance = U_balance + ?
        where UID = ?
    """, (value, UID))

    # update Transaction_Record
    db.cursor().execute("""
        insert into Transaction_Record(T_action, T_amount, T_Subject, T_Object)
        values (?, ?, ?, ?)
    """, (2, value, UID, UID))

    db.commit()

    flash('Top-up successful')
    return redirect(url_for('nav'))


@app.errorhandler(Exception)
def all_exception_handler(error):
    print("**all_exception_handler**")
    print(error)
    return "invalid", 500


def main():
    init_db()
    app.run('0.0.0.0', debug=True, threaded=False)


if __name__ == '__main__':
    main()
