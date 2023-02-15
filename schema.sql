CREATE TABLE
    if NOT EXISTS Users(
        UID INTEGER PRIMARY KEY AUTOINCREMENT,
        U_account VARCHAR(256) UNIQUE NOT NULL,
        U_password VARCHAR(64) NOT NULL,
        U_name VARCHAR(256) NOT NULL,
        -- {First name}  {Last name}
        U_type INT NOT NULL,
        -- 0: Normal user, 1: Shop owner
        U_latitude FLOAT NOT NULL,
        U_longitude FLOAT NOT NULL,
        U_phone VARCHAR(10) NOT NULL,
        U_balance INT NOT NULL,
        -- constraints --
        CONSTRAINT U_balance_non_negative CHECK (U_balance >= 0)
    );

CREATE TABLE
    if NOT EXISTS Stores(
        SID INTEGER PRIMARY KEY AUTOINCREMENT,
        S_name VARCHAR(256) UNIQUE NOT NULL,
        S_latitude FLOAT NOT NULL,
        S_longitude FLOAT NOT NULL,
        S_phone VARCHAR(10) NOT NULL,
        S_foodtype VARCHAR(256) NOT NULL,
        S_owner INT NOT NULL,
        FOREIGN key (S_owner) REFERENCES Users(UID)
    );

CREATE TABLE
    if NOT EXISTS Orders(
        OID INTEGER PRIMARY KEY AUTOINCREMENT,
        O_status INT NOT NULL,
        -- 0: not done, 1: done, -1: canceled
        O_start_time datetime DEFAULT (datetime('now', 'localtime')) NOT NULL,
        -- insert current time using datetime('now', 'localtime')
        -- format: 'yyyy-mm-dd hh:mi:ss'
        O_end_time datetime,
        O_distance FLOAT NOT NULL,
        O_amount INT NOT NULL,
        -- total amount (could be removed)
        O_type INT NOT NULL,
        -- 0: take-out, 1: delivery
        O_details BLOB NOT NULL,
        -- stores current order details (in case of updating product properties)
        SID INT NOT NULL,
        FOREIGN key (SID) REFERENCES Stores(SID),
        -- constraints --
        CONSTRAINT O_amount_gt_zero CHECK (O_amount > 0)
    );

CREATE TABLE
    if NOT EXISTS Process_Order(
        UID INT NOT NULL,
        OID INT NOT NULL,
        PO_type INT NOT NULL,
        -- 0: User order, 1: User cancel, 2: Order completed, 3: Owner cancel
        PRIMARY key (UID, OID),
        FOREIGN key (UID) REFERENCES Users(UID),
        FOREIGN key (OID) REFERENCES Orders(OID)
    );

CREATE TABLE
    if NOT EXISTS Transaction_Record(
        TID INTEGER PRIMARY KEY AUTOINCREMENT,
        T_action INT NOT NULL,
        -- 0: S(-) -> O(+), 1: O(-) -> S(+), 2: O(+) == S(+)
        -- actually its a redundant column
        T_amount INT NOT NULL,
        -- amount could be negative if action == 0
        is_refund INT DEFAULT 0 NOT NULL,
        -- 0: not refund, 1: refund
        T_time datetime DEFAULT (datetime('now', 'localtime')) NOT NULL,
        T_Subject INT,
        T_Object INT,
        FOREIGN key (T_Subject) REFERENCES Users(UID),
        FOREIGN key (T_Object) REFERENCES Users(UID)
    );

CREATE TABLE
    if NOT EXISTS Products(
        PID INTEGER PRIMARY KEY AUTOINCREMENT,
        P_name VARCHAR(256) NOT NULL,
        P_price INT unsigned NOT NULL,
        P_quantity INT unsigned NOT NULL,
        P_image BLOB NOT NULL,
        -- image encoded by base64
        P_imagetype VARCHAR(25) NOT NULL,
        P_owner INT NOT NULL,
        P_store INT NOT NULL,
        FOREIGN key (P_owner) REFERENCES Users(UID),
        FOREIGN key (P_store) REFERENCES Stores(SID),
        -- constraints --
        CONSTRAINT P_quantity_non_negative CHECK (P_quantity >= 0)
    );