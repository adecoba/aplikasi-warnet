"""
ETL (Extract, Transform, Load) Module
======================================
Modul ini bertanggung jawab untuk memindahkan data dari database operasional (OLTP)
ke Data Warehouse (OLAP) dengan arsitektur Star Schema.

Alur ETL:
  EXTRACT  → Ambil data mentah dari warnet.db (OLTP)
  TRANSFORM → Bersihkan, enriched, dan bentuk sesuai skema DW
  LOAD     → Masukkan ke warehouse.db (Data Warehouse)

Star Schema:
  Fact Table    : fact_sessions
  Dimension     : dim_time, dim_pc, dim_package
"""

import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import os
import pytz


OLTP_PATH = "data/warnet.db"
DW_PATH   = "data/warehouse.db"

# TAMBAHKAN TIMEZONE
TIMEZONE = pytz.timezone('Asia/Jakarta')

def get_current_time():
    return datetime.now(TIMEZONE)

# ─────────────────────────────────────────────
# INISIALISASI DATA WAREHOUSE (Star Schema)
# ─────────────────────────────────────────────

def init_warehouse():
    """Buat skema Data Warehouse jika belum ada."""
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DW_PATH)
    cur  = conn.cursor()

    # Dimensi Waktu
    cur.execute('''
        CREATE TABLE IF NOT EXISTS dim_time (
            time_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            full_date    DATE UNIQUE,
            day_of_week  TEXT,
            day_number   INTEGER,
            week_number  INTEGER,
            month_number INTEGER,
            month_name   TEXT,
            quarter      INTEGER,
            year         INTEGER,
            is_weekend   INTEGER
        )
    ''')

    # Dimensi PC
    cur.execute('''
        CREATE TABLE IF NOT EXISTS dim_pc (
            pc_id      INTEGER PRIMARY KEY,
            pc_number  INTEGER UNIQUE,
            specs      TEXT
        )
    ''')

    # Dimensi Paket
    cur.execute('''
        CREATE TABLE IF NOT EXISTS dim_package (
            package_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            duration_minutes INTEGER UNIQUE,
            duration_label   TEXT,
            price_per_minute REAL
        )
    ''')

    # Tabel Fakta Sesi
    cur.execute('''
        CREATE TABLE IF NOT EXISTS fact_sessions (
            fact_id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id       INTEGER UNIQUE,
            time_id          INTEGER,
            pc_id            INTEGER,
            package_id       INTEGER,
            customer_name    TEXT,
            start_hour       INTEGER,
            duration_minutes INTEGER,
            total_price      INTEGER,
            revenue_per_min  REAL,
            FOREIGN KEY (time_id)   REFERENCES dim_time(time_id),
            FOREIGN KEY (pc_id)     REFERENCES dim_pc(pc_id),
            FOREIGN KEY (package_id) REFERENCES dim_package(package_id)
        )
    ''')

    # Tabel log ETL untuk audit trail
    cur.execute('''
        CREATE TABLE IF NOT EXISTS etl_log (
            log_id        INTEGER PRIMARY KEY AUTOINCREMENT,
            run_timestamp TIMESTAMP,
            rows_extracted INTEGER,
            rows_transformed INTEGER,
            rows_loaded   INTEGER,
            status        TEXT,
            message       TEXT
        )
    ''')

    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
# TAHAP 1: EXTRACT
# ─────────────────────────────────────────────

def extract():
    """
    Extract: Ambil semua sesi yang sudah selesai dari database OLTP
    yang belum ada di Data Warehouse.
    """
    oltp = sqlite3.connect(OLTP_PATH)
    dw   = sqlite3.connect(DW_PATH)

    # Ambil session_id yang sudah ada di DW agar tidak duplikat
    existing = pd.read_sql_query("SELECT session_id FROM fact_sessions", dw)
    existing_ids = set(existing['session_id'].tolist()) if not existing.empty else set()

    query = '''
        SELECT
            s.id          AS session_id,
            s.pc_id,
            s.customer_name,
            s.start_time,
            s.end_time,
            s.duration_minutes,
            s.total_price,
            c.pc_number,
            c.specs
        FROM sessions s
        JOIN computers c ON s.pc_id = c.id
        WHERE s.status = 'completed'
    '''
    raw = pd.read_sql_query(query, oltp)

    oltp.close()
    dw.close()

    # Filter hanya data baru
    if not raw.empty and existing_ids:
        raw = raw[~raw['session_id'].isin(existing_ids)]

    return raw


# ─────────────────────────────────────────────
# TAHAP 2: TRANSFORM
# ─────────────────────────────────────────────

def transform(raw_df: pd.DataFrame):
    """
    Transform: Bersihkan dan enriched data untuk masuk ke star schema.
    Menghasilkan dict berisi dataframe untuk tiap tabel DW.
    """
    if raw_df.empty:
        return None

    df = raw_df.copy()

    # Parse datetime
    df['start_time'] = pd.to_datetime(df['start_time'])
    df['end_time']   = pd.to_datetime(df['end_time'])

    # ── Dimensi Waktu ──────────────────────────────
    df['full_date'] = df['start_time'].dt.date
    dates = df['full_date'].unique()

    time_rows = []
    for d in dates:
        dt = pd.Timestamp(d)
        time_rows.append({
            'full_date'   : str(d),
            'day_of_week' : dt.strftime('%A'),
            'day_number'  : dt.weekday(),        # 0=Senin, 6=Minggu
            'week_number' : dt.isocalendar()[1],
            'month_number': dt.month,
            'month_name'  : dt.strftime('%B'),
            'quarter'     : (dt.month - 1) // 3 + 1,
            'year'        : dt.year,
            'is_weekend'  : 1 if dt.weekday() >= 5 else 0
        })
    dim_time_df = pd.DataFrame(time_rows)

    # ── Dimensi PC ─────────────────────────────────
    dim_pc_df = df[['pc_id','pc_number','specs']].drop_duplicates('pc_id')
    dim_pc_df = dim_pc_df.rename(columns={'pc_id': 'pc_id'})

    # ── Dimensi Paket (berdasarkan durasi) ─────────
    df['duration_label'] = df['duration_minutes'].apply(
        lambda x: f"{x//60} Jam" if x % 60 == 0 else f"{x//60}j {x%60}m"
    )
    df['price_per_minute'] = df.apply(
        lambda r: round(r['total_price'] / r['duration_minutes'], 2) if r['duration_minutes'] > 0 else 0,
        axis=1
    )
    dim_package_df = df[['duration_minutes','duration_label','price_per_minute']].drop_duplicates('duration_minutes')

    # ── Tabel Fakta ────────────────────────────────
    df['start_hour']      = df['start_time'].dt.hour
    df['revenue_per_min'] = df['price_per_minute']

    fact_df = df[['session_id','pc_id','customer_name',
                  'start_hour','duration_minutes',
                  'total_price','revenue_per_min','full_date','duration_minutes']].copy()

    return {
        'dim_time'   : dim_time_df,
        'dim_pc'     : dim_pc_df,
        'dim_package': dim_package_df,
        'fact'       : fact_df,
        'raw'        : df   # bawa raw untuk resolusi FK saat load
    }


# ─────────────────────────────────────────────
# TAHAP 3: LOAD
# ─────────────────────────────────────────────

def load(transformed: dict):
    """
    Load: Masukkan data hasil transformasi ke tabel-tabel Data Warehouse.
    Mengembalikan jumlah baris yang berhasil di-load.
    """
    if transformed is None:
        return 0

    dw  = sqlite3.connect(DW_PATH)
    cur = dw.cursor()
    raw = transformed['raw']
    loaded = 0

    # ── Load dim_time ──────────────────────────────
    for _, row in transformed['dim_time'].iterrows():
        cur.execute('''
            INSERT OR IGNORE INTO dim_time
              (full_date, day_of_week, day_number, week_number,
               month_number, month_name, quarter, year, is_weekend)
            VALUES (?,?,?,?,?,?,?,?,?)
        ''', (row['full_date'], row['day_of_week'], row['day_number'],
              row['week_number'], row['month_number'], row['month_name'],
              row['quarter'], row['year'], row['is_weekend']))

    # ── Load dim_pc ────────────────────────────────
    for _, row in transformed['dim_pc'].iterrows():
        cur.execute('''
            INSERT OR IGNORE INTO dim_pc (pc_id, pc_number, specs)
            VALUES (?,?,?)
        ''', (int(row['pc_id']), int(row['pc_number']), row['specs']))

    # ── Load dim_package ───────────────────────────
    for _, row in transformed['dim_package'].iterrows():
        cur.execute('''
            INSERT OR IGNORE INTO dim_package
              (duration_minutes, duration_label, price_per_minute)
            VALUES (?,?,?)
        ''', (int(row['duration_minutes']), row['duration_label'],
              float(row['price_per_minute'])))

    dw.commit()

    # Bangun lookup FK
    time_map    = {r[0]: r[1] for r in cur.execute("SELECT full_date, time_id FROM dim_time")}
    package_map = {r[0]: r[1] for r in cur.execute("SELECT duration_minutes, package_id FROM dim_package")}

    # ── Load fact_sessions ─────────────────────────
    for _, row in raw.iterrows():
        date_str   = str(row['full_date'])
        time_id    = time_map.get(date_str)
        package_id = package_map.get(int(row['duration_minutes']))

        if time_id is None or package_id is None:
            continue

        cur.execute('''
            INSERT OR IGNORE INTO fact_sessions
              (session_id, time_id, pc_id, package_id, customer_name,
               start_hour, duration_minutes, total_price, revenue_per_min)
            VALUES (?,?,?,?,?,?,?,?,?)
        ''', (int(row['session_id']), time_id, int(row['pc_id']), package_id,
              row['customer_name'], int(row['start_hour']),
              int(row['duration_minutes']), int(row['total_price']),
              float(row['revenue_per_min'])))
        loaded += 1

    dw.commit()
    dw.close()
    return loaded


# ─────────────────────────────────────────────
# PIPELINE UTAMA ETL
# ─────────────────────────────────────────────

def run_etl():
    """
    Jalankan pipeline ETL lengkap: Extract → Transform → Load.
    Mengembalikan dict hasil untuk ditampilkan di UI.
    """
    init_warehouse()
    timestamp = get_current_time()
    result = {
        'timestamp'       : timestamp,
        'rows_extracted'  : 0,
        'rows_transformed': 0,
        'rows_loaded'     : 0,
        'status'          : 'success',
        'message'         : ''
    }

    try:
        # EXTRACT
        raw = extract()
        result['rows_extracted'] = len(raw)

        # TRANSFORM
        transformed = transform(raw)
        result['rows_transformed'] = len(raw) if transformed else 0

        # LOAD
        loaded = load(transformed)
        result['rows_loaded'] = loaded
        result['message'] = f"ETL selesai: {loaded} sesi baru dimuat ke Data Warehouse."

    except Exception as e:
        result['status']  = 'error'
        result['message'] = str(e)

    # Catat ke etl_log
    try:
        dw  = sqlite3.connect(DW_PATH)
        cur = dw.cursor()
        cur.execute('''
            INSERT INTO etl_log
              (run_timestamp, rows_extracted, rows_transformed, rows_loaded, status, message)
            VALUES (?,?,?,?,?,?)
        ''', (result['timestamp'], result['rows_extracted'],
              result['rows_transformed'], result['rows_loaded'],
              result['status'], result['message']))
        dw.commit()
        dw.close()
    except Exception:
        pass

    return result


# ─────────────────────────────────────────────
# QUERY ANALITIK (dari Data Warehouse)
# ─────────────────────────────────────────────

def get_dw_connection():
    init_warehouse()
    return sqlite3.connect(DW_PATH)

def query_revenue_trend(period='weekly'):
    """Tren pendapatan mingguan atau bulanan."""
    conn = get_dw_connection()
    if period == 'weekly':
        query = '''
            SELECT
                t.year,
                t.week_number,
                t.year || '-W' || printf('%02d', t.week_number) AS label,
                SUM(f.total_price)      AS total_revenue,
                COUNT(f.fact_id)        AS total_sessions,
                AVG(f.duration_minutes) AS avg_duration
            FROM fact_sessions f
            JOIN dim_time t ON f.time_id = t.time_id
            GROUP BY t.year, t.week_number
            ORDER BY t.year, t.week_number
        '''
    else:  # monthly
        query = '''
            SELECT
                t.year,
                t.month_number,
                t.month_name || ' ' || t.year AS label,
                SUM(f.total_price)      AS total_revenue,
                COUNT(f.fact_id)        AS total_sessions,
                AVG(f.duration_minutes) AS avg_duration
            FROM fact_sessions f
            JOIN dim_time t ON f.time_id = t.time_id
            GROUP BY t.year, t.month_number
            ORDER BY t.year, t.month_number
        '''
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def query_busiest_hours():
    """Analisis jam dan hari tersibuk."""
    conn = get_dw_connection()

    # Per jam
    hour_q = '''
        SELECT
            start_hour,
            COUNT(*)        AS total_sessions,
            SUM(total_price) AS total_revenue,
            AVG(duration_minutes) AS avg_duration
        FROM fact_sessions
        GROUP BY start_hour
        ORDER BY start_hour
    '''

    # Per hari
    day_q = '''
        SELECT
            t.day_of_week,
            t.day_number,
            COUNT(*)         AS total_sessions,
            SUM(f.total_price) AS total_revenue,
            AVG(f.duration_minutes) AS avg_duration
        FROM fact_sessions f
        JOIN dim_time t ON f.time_id = t.time_id
        GROUP BY t.day_number, t.day_of_week
        ORDER BY t.day_number
    '''

    hour_df = pd.read_sql_query(hour_q, conn)
    day_df  = pd.read_sql_query(day_q, conn)
    conn.close()
    return hour_df, day_df

def query_pc_performance():
    """Laporan performa per PC."""
    conn = get_dw_connection()
    query = '''
        SELECT
            p.pc_number,
            p.specs,
            COUNT(f.fact_id)         AS total_sessions,
            SUM(f.total_price)       AS total_revenue,
            AVG(f.duration_minutes)  AS avg_duration,
            SUM(f.duration_minutes)  AS total_usage_minutes
        FROM fact_sessions f
        JOIN dim_pc p ON f.pc_id = p.pc_id
        GROUP BY p.pc_number, p.specs
        ORDER BY total_revenue DESC
    '''
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def query_forecasting():
    """
    Prediksi pendapatan 4 periode ke depan menggunakan
    metode Simple Linear Regression atas data historis.
    """
    conn = get_dw_connection()
    query = '''
        SELECT
            t.year,
            t.week_number,
            t.year * 100 + t.week_number AS period_key,
            SUM(f.total_price) AS total_revenue
        FROM fact_sessions f
        JOIN dim_time t ON f.time_id = t.time_id
        GROUP BY t.year, t.week_number
        ORDER BY period_key
    '''
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def query_etl_log():
    """Ambil riwayat eksekusi ETL."""
    conn = get_dw_connection()
    df = pd.read_sql_query(
        "SELECT * FROM etl_log ORDER BY run_timestamp DESC LIMIT 20", conn
    )
    conn.close()
    return df

def get_dw_summary():
    """Ringkasan isi Data Warehouse untuk ditampilkan di UI."""
    conn = get_dw_connection()
    facts    = pd.read_sql_query("SELECT COUNT(*) AS n FROM fact_sessions", conn).iloc[0]['n']
    dim_time = pd.read_sql_query("SELECT COUNT(*) AS n FROM dim_time", conn).iloc[0]['n']
    dim_pc   = pd.read_sql_query("SELECT COUNT(*) AS n FROM dim_pc", conn).iloc[0]['n']
    dim_pkg  = pd.read_sql_query("SELECT COUNT(*) AS n FROM dim_package", conn).iloc[0]['n']
    conn.close()
    return {
        'fact_sessions': int(facts),
        'dim_time'     : int(dim_time),
        'dim_pc'       : int(dim_pc),
        'dim_package'  : int(dim_pkg)
    }