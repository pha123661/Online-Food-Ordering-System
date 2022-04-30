create table if not exists Users(
    UID INTEGER PRIMARY KEY AUTOINCREMENT,
    U_account varchar(255) UNIQUE NOT NULL,
    U_password varchar(255) NOT NULL,
    U_name varchar(255) NOT NULL,
    U_type int NOT NULL, -- 0: Normal user, 1: Shop owner
    U_latitude float NOT NULL,
    U_longitude float NOT NULL,
    U_phone varchar(255) NOT NULL,
    U_balance int NOT NULL
);

create table if not exists Stores(
    SID INTEGER PRIMARY KEY AUTOINCREMENT,
    S_name varchar(255) UNIQUE NOT NULL,
    S_latitude float NOT NULL,
    S_longitude float NOT NULL,
    S_phone varchar(255) NOT NULL,
    S_foodtype varchar(255) NOT NULL,
    S_owner int NOT NULL,
    foreign key (S_owner) references Users(UID)
);

create table if not exists Orders(
    OID INTEGER PRIMARY KEY AUTOINCREMENT,
    O_status int NOT NULL, -- 0: not done, 1: done, -1:canceled
    O_start_time datetime NOT NULL, -- format: 'yyyy-mm-dd hh-mi-ss'
    O_end_time datetime NOT NULL,
    O_distance float NOT NULL,
    O_amount int NOT NULL,
    O_type int NOT NULL, -- 0: take-out, 1: delivery
    SID int NOT NULL,
    foreign key (SID) references Stores(SID)
);

create table if not exists Process_Order(
    UID int NOT NULL,
    OID int NOT NULL,
    PO_type int NOT NULL, -- 0: User order, 1: User cancel, 2: Owner deliver, 3:Owner cancel
    primary key (UID, OID),
    foreign key (UID) references Users(UID),
    foreign key (OID) references Orders(OID)
);

create table if not exists Transaction_Record(
    TID INTEGER PRIMARY KEY AUTOINCREMENT,
    T_action int NOT NULL, -- 0: deduct, 1: top-up
    T_amount int NOT NULL,
    UID int,
    foreign key (UID) references Users(UID)
);

create table if not exists Products(
    PID INTEGER PRIMARY KEY AUTOINCREMENT,
    P_name varchar(255) NOT NULL,
    P_price int NOT NULL,
    P_image BLOB NOT NULL, -- image encoded by base64
    P_owner int NOT NULL,
    P_store int NOT NULL,
    foreign key (P_owner) references Users(UID),
    foreign key (P_store) references Stores(SID)
);

create table if not exists O_Contains_P(
    OID int NOT NULL,
    PID int NOT NULL,
    Quantity int NOT NULL,
    primary key (OID, PID),
    foreign key (OID) references Orders(OID),
    foreign key (PID) references Products(PID)
);