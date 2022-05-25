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
        U_balance INT NOT NULL
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
        -- 0: not done, 1: done, -1:canceled
        O_start_time datetime NOT NULL,
        -- format: 'yyyy-mm-dd hh-mi-ss'
        O_end_time datetime NOT NULL,
        O_distance FLOAT NOT NULL,
        O_amount INT NOT NULL,
        O_type INT NOT NULL,
        -- 0: take-out, 1: delivery
        SID INT NOT NULL,
        FOREIGN key (SID) REFERENCES Stores(SID)
    );

CREATE TABLE
    if NOT EXISTS Process_Order(
        UID INT NOT NULL,
        OID INT NOT NULL,
        PO_type INT NOT NULL,
        -- 0: User order, 1: User cancel, 2: Owner deliver, 3:Owner cancel
        PRIMARY key (UID, OID),
        FOREIGN key (UID) REFERENCES Users(UID),
        FOREIGN key (OID) REFERENCES Orders(OID)
    );

CREATE TABLE
    if NOT EXISTS Transaction_Record(
        TID INTEGER PRIMARY KEY AUTOINCREMENT,
        T_action INT NOT NULL,
        -- 0: deduct, 1: top-up
        T_amount INT NOT NULL,
        UID INT,
        FOREIGN key (UID) REFERENCES Users(UID)
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
        FOREIGN key (P_store) REFERENCES Stores(SID)
    );

CREATE TABLE
    if NOT EXISTS O_Contains_P(
        OID INT NOT NULL,
        PID INT NOT NULL,
        Quantity INT unsigned NOT NULL,
        PRIMARY key (OID, PID),
        FOREIGN key (OID) REFERENCES Orders(OID),
        FOREIGN key (PID) REFERENCES Products(PID)
    );