import sqlite3
from datetime import datetime, timedelta
import pandas as pd
import pytz

DB_PATH = "data/warnet.db"
TIMEZONE = pytz.timezone('Asia/Makassar')

def get_current_time():
    """Mengembalikan waktu sekarang dalam GMT+8"""
    return datetime.now(TIMEZONE)

def get_current_date():
    """Mengembalikan tanggal sekarang dalam GMT+8"""
    return get_current_time().date()

def init_database():
    """Inisialisasi database dan tabel-tabel yang diperlukan"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Tabel PC / Komputer
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS computers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pc_number INTEGER UNIQUE NOT NULL,
            status TEXT DEFAULT 'available',
            current_user TEXT,
            session_start TIME,
            specs TEXT DEFAULT 'Standard'
        )
    ''')
    
    # Tabel sesi / transaksi
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pc_id INTEGER,
            customer_name TEXT,
            start_time TIMESTAMP,
            end_time TIMESTAMP,
            duration_minutes INTEGER,
            total_price INTEGER,
            status TEXT DEFAULT 'active',
            FOREIGN KEY (pc_id) REFERENCES computers (id)
        )
    ''')
    
    # Tabel paket harga
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS packages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            duration_minutes INTEGER,
            price INTEGER,
            is_active INTEGER DEFAULT 1
        )
    ''')
    
    # Tabel log transaksi harian
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_date DATE UNIQUE,
            total_revenue INTEGER,
            total_sessions INTEGER,
            avg_duration INTEGER,
            peak_hour INTEGER
        )
    ''')
    
    # Insert data komputer awal (10 PC)
    cursor.execute("SELECT COUNT(*) FROM computers")
    if cursor.fetchone()[0] == 0:
        for i in range(1, 11):
            cursor.execute("INSERT INTO computers (pc_number, status) VALUES (?, ?)", (i, 'available'))
    
    # Insert paket harga default
    cursor.execute("SELECT COUNT(*) FROM packages")
    if cursor.fetchone()[0] == 0:
        default_packages = [
            ('1 Jam', 60, 5000, 1),
            ('2 Jam', 120, 9000, 1),
            ('3 Jam', 180, 12000, 1),
            ('5 Jam', 300, 18000, 1),
        ]
        cursor.executemany("INSERT INTO packages (name, duration_minutes, price, is_active) VALUES (?, ?, ?, ?)", default_packages)
    
    conn.commit()
    conn.close()

def get_connection():
    return sqlite3.connect(DB_PATH)

def get_all_computers():
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM computers ORDER BY pc_number", conn)
    conn.close()
    return df

def update_computer_status(pc_id, status, current_user=None, session_start=None):
    conn = get_connection()
    cursor = conn.cursor()
    if current_user and session_start:
        cursor.execute("UPDATE computers SET status = ?, current_user = ?, session_start = ? WHERE id = ?", 
                      (status, current_user, session_start, pc_id))
    else:
        cursor.execute("UPDATE computers SET status = ?, current_user = NULL, session_start = NULL WHERE id = ?", 
                      (status, pc_id))
    conn.commit()
    conn.close()

def start_session(pc_id, customer_name, duration_minutes, total_price):
    conn = get_connection()
    cursor = conn.cursor()
    
    pc_id = int(pc_id)
    duration_minutes = int(duration_minutes)
    total_price = int(total_price)
    
    # UBAH: dari datetime.now() menjadi get_current_time()
    start_time = get_current_time()
    end_time = start_time + timedelta(minutes=duration_minutes)
    
    cursor.execute('''
        INSERT INTO sessions (pc_id, customer_name, start_time, end_time, duration_minutes, total_price, status)
        VALUES (?, ?, ?, ?, ?, ?, 'active')
    ''', (pc_id, customer_name, start_time, end_time, duration_minutes, total_price))
    
    session_id = cursor.lastrowid
    
    cursor.execute("UPDATE computers SET status = 'occupied', current_user = ?, session_start = ? WHERE id = ?",
                  (customer_name, start_time, pc_id))
    
    conn.commit()
    conn.close()
    return session_id

def end_session(session_id, pc_id):
    conn = get_connection()
    cursor = conn.cursor()
    
    session_id = int(session_id)
    pc_id = int(pc_id)
    # UBAH: dari datetime.now() menjadi get_current_time()
    end_time = get_current_time()
    cursor.execute("UPDATE sessions SET end_time = ?, status = 'completed' WHERE id = ?", (end_time, session_id))
    cursor.execute("UPDATE computers SET status = 'available', current_user = NULL, session_start = NULL WHERE id = ?", (pc_id,))
    
    conn.commit()
    conn.close()

def get_active_sessions():
    conn = get_connection()
    query = '''
        SELECT s.id, s.pc_id, c.pc_number, s.customer_name, s.start_time, s.end_time, s.duration_minutes, s.total_price
        FROM sessions s
        JOIN computers c ON s.pc_id = c.id
        WHERE s.status = 'active'
    '''
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def get_today_revenue():
    conn = get_connection()
    # UBAH: menggunakan get_current_date() untuk GMT+8
    today = get_current_date().strftime('%Y-%m-%d')
    query = '''
        SELECT COALESCE(SUM(total_price), 0) as revenue, COUNT(*) as sessions
        FROM sessions
        WHERE DATE(start_time) = ? AND status = 'completed'
    '''
    df = pd.read_sql_query(query, conn, params=(today,))
    conn.close()
    return df.iloc[0]['revenue'], df.iloc[0]['sessions']

def get_hourly_usage():
    conn = get_connection()
    # UBAH: menggunakan datetime dengan offset GMT+8 di SQLite
    # SQLite tidak native timezone, jadi kita konversi saat query
    query = '''
        SELECT strftime('%H', datetime(start_time, '+8 hours')) as hour, COUNT(*) as total
        FROM sessions
        WHERE date(datetime(start_time, '+8 hours')) = date('now', '+8 hours')
        GROUP BY hour
        ORDER BY hour
    '''
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def get_packages():
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM packages WHERE is_active = 1", conn)
    conn.close()
    return df

def add_package(name, duration_minutes, price):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO packages (name, duration_minutes, price, is_active) VALUES (?, ?, ?, 1)", 
                  (name, duration_minutes, price))
    conn.commit()
    conn.close()

def update_package(package_id, name, duration_minutes, price):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE packages SET name = ?, duration_minutes = ?, price = ? WHERE id = ?",
                  (name, duration_minutes, price, package_id))
    conn.commit()
    conn.close()

def delete_package(package_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE packages SET is_active = 0 WHERE id = ?", (package_id,))
    conn.commit()
    conn.close()

def get_daily_report(date):
    conn = get_connection()
    query = '''
        SELECT 
            COUNT(*) as total_sessions,
            COALESCE(SUM(total_price), 0) as total_revenue,
            COALESCE(AVG(duration_minutes), 0) as avg_duration
        FROM sessions
        WHERE DATE(start_time) = ? AND status = 'completed'
    '''
    df = pd.read_sql_query(query, conn, params=(date,))
    conn.close()
    return df

def add_time_session(pc_id, additional_minutes):
    """Tambah waktu untuk sesi aktif"""
    conn = get_connection()
    cursor = conn.cursor()
    
    pc_id = int(pc_id)  # Fix: pastikan integer
    # Dapatkan sesi aktif untuk PC ini
    cursor.execute('''
        SELECT id, end_time, total_price, duration_minutes
        FROM sessions
        WHERE pc_id = ? AND status = 'active'
    ''', (pc_id,))
    
    session = cursor.fetchone()
    if session:
        session_id, current_end, current_price, current_duration = session
        new_end = datetime.strptime(current_end, '%Y-%m-%d %H:%M:%S.%f') + timedelta(minutes=additional_minutes)
        new_duration = current_duration + additional_minutes
        
        # Hitung harga tambahan (Rp 100 per menit)
        additional_price = additional_minutes * 100
        new_price = current_price + additional_price
        
        cursor.execute('''
            UPDATE sessions 
            SET end_time = ?, duration_minutes = ?, total_price = ?
            WHERE id = ?
        ''', (new_end, new_duration, new_price, session_id))
        
        conn.commit()
    conn.close()

def get_all_completed_sessions():
    """Ambil semua sesi yang sudah selesai untuk laporan"""
    conn = get_connection()
    query = '''
        SELECT s.*, c.pc_number,
               datetime(s.start_time, '+8 hours') as start_time_gmt8,
               datetime(s.end_time, '+8 hours') as end_time_gmt8
        FROM sessions s
        JOIN computers c ON s.pc_id = c.id
        WHERE s.status = 'completed'
        ORDER BY s.start_time DESC
    '''
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df