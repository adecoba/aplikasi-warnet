import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import numpy as np
import database as db
import etl
import pytz

timezone = pytz.timezone('Asia/Makassar')

sessions_js = []
for _, row in active_sessions.iterrows():
    # Konversi waktu ke GMT+8 sebelum dikirim ke JavaScript
    start_time = datetime.fromisoformat(str(row['start_time']))
    end_time = datetime.fromisoformat(str(row['end_time']))
    
    # Jika waktu masih naive (tanpa timezone), beri timezone UTC lalu konversi
    if start_time.tzinfo is None:
        start_time = pytz.UTC.localize(start_time).astimezone(timezone)
    if end_time.tzinfo is None:
        end_time = pytz.UTC.localize(end_time).astimezone(timezone)
    
    sessions_js.append({
        "pc": int(row['pc_number']),
        "name": str(row['customer_name']),
        "start": start_time.isoformat(),
        "end": end_time.isoformat(),
        "duration": int(row['duration_minutes']),
        "price": int(row['total_price']),
        "timezone": "GMT+8"  # tambahkan info timezone
    })

# Konfigurasi halaman
st.set_page_config(
    page_title="Sistem Informasi Warnet",
    page_icon="🖥️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inisialisasi database
db.init_database()


# ==================== LOGIN ADMIN ====================
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "warnet123"

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

def do_login(username, password):
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        st.session_state.logged_in = True
    else:
        st.session_state.login_error = True

def do_logout():
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.markdown("""
    <style>
        .login-box {
            max-width: 400px;
            margin: 80px auto;
            background: #1a1d2e;
            border: 1px solid #2a2d3e;
            border-radius: 16px;
            padding: 40px 36px;
            text-align: center;
        }
        .login-title {
            color: #e8eaf6;
            font-size: 26px;
            font-weight: 700;
            margin-bottom: 6px;
        }
        .login-sub {
            color: #6b7280;
            font-size: 13px;
            margin-bottom: 28px;
        }
    </style>
    <div class="login-box">
        <div class="login-title">🖥️ Warnet System</div>
        <div class="login-sub">Masuk sebagai Administrator</div>
    </div>
    """, unsafe_allow_html=True)

    col_l, col_m, col_r = st.columns([1, 2, 1])
    with col_m:
        username_input = st.text_input("Username", placeholder="Masukkan username")
        password_input = st.text_input("Password", type="password", placeholder="Masukkan password")
        if st.button("🔐 Login", use_container_width=True):
            do_login(username_input, password_input)
            st.rerun()
        if st.session_state.get("login_error"):
            st.error("❌ Username atau password salah!")
            st.session_state.login_error = False
    st.stop()

# CSS Kustom untuk tampilan
st.markdown("""
<style>
    .pc-available {
        background-color: #28a745;
        color: white;
        padding: 15px;
        border-radius: 10px;
        text-align: center;
        font-weight: bold;
    }
    .pc-occupied {
        background-color: #dc3545;
        color: white;
        padding: 15px;
        border-radius: 10px;
        text-align: center;
        font-weight: bold;
    }
    .pc-offline {
        background-color: #6c757d;
        color: white;
        padding: 15px;
        border-radius: 10px;
        text-align: center;
        font-weight: bold;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 10px;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

# Sidebar untuk navigasi
st.sidebar.title("🖥️ Warnet System")
st.sidebar.markdown("---")

menu = st.sidebar.radio(
    "Menu Utama",
    ["📊 Dashboard", "🖥️ Peta PC", "💰 Kasir","⚙️ Manajemen Harga"]
)

st.sidebar.markdown("---")
st.sidebar.caption("Sistem Informasi Warnet v1.0")

# ==================== DASHBOARD ====================
if menu == "📊 Dashboard":
    st.title("📊 Dashboard Monitoring Warnet")
    st.markdown("---")
    
    # Ambil data real-time
    computers = db.get_all_computers()
    active_sessions = db.get_active_sessions()
    today_revenue, today_sessions = db.get_today_revenue()
    
    # Kolom KPI
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_pc = len(computers)
        occupied = len(computers[computers['status'] == 'occupied'])
        available = total_pc - occupied
        st.metric("💻 Total PC", total_pc)
        st.caption(f"🟢 Tersedia: {available} | 🔴 Terpakai: {occupied}")
    
    with col2:
        st.metric("👥 Pelanggan Aktif", len(active_sessions))
    
    with col3:
        st.metric("💰 Pendapatan Hari Ini", f"Rp {today_revenue:,.0f}")
    
    with col4:
        okupansi = (occupied / total_pc * 100) if total_pc > 0 else 0
        st.metric("📊 Tingkat Hunian", f"{okupansi:.0f}%")
    
    st.markdown("---")
    
    # Grafik Jam Sibuk
    st.subheader("📊 Jam Sibuk (Hari Ini)")
    hourly_data = db.get_hourly_usage()
    
    if not hourly_data.empty:
        fig = px.bar(hourly_data, x='hour', y='total', 
                     title="Jumlah Sesi per Jam",
                     labels={'hour': 'Jam', 'total': 'Jumlah Sesi'},
                     color_discrete_sequence=['#FF6B6B'])
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Belum ada data sesi untuk hari ini")
    
    # Daftar sesi aktif dengan countdown real-time
    st.subheader("🟢 Sesi Aktif Saat Ini")
    if not active_sessions.empty:
        # Siapkan data end_time dalam format ISO untuk JavaScript
        sessions_js = []
        for _, row in active_sessions.iterrows():
            sessions_js.append({
                "pc": int(row['pc_number']),
                "name": str(row['customer_name']),
                "start": str(row['start_time']),
                "end": str(row['end_time']),
                "duration": int(row['duration_minutes']),
                "price": int(row['total_price'])
            })

        import json
        sessions_json = json.dumps(sessions_js)

        countdown_html = f"""
        <style>
            @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Sora:wght@400;600;700&display=swap');

            .monitor-wrapper {{
                font-family: 'Sora', sans-serif;
                background: #0f1117;
                border-radius: 16px;
                padding: 20px;
                margin-top: 10px;
            }}
            .monitor-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
                gap: 14px;
            }}
            .session-card {{
                background: linear-gradient(135deg, #1a1d2e 0%, #16192a 100%);
                border: 1px solid #2a2d3e;
                border-radius: 12px;
                padding: 16px 18px;
                position: relative;
                overflow: hidden;
                transition: border-color 0.3s;
            }}
            .session-card::before {{
                content: '';
                position: absolute;
                top: 0; left: 0; right: 0;
                height: 3px;
                background: linear-gradient(90deg, #00d4aa, #0099ff);
                border-radius: 12px 12px 0 0;
            }}
            .session-card.warning::before {{
                background: linear-gradient(90deg, #ff9500, #ff6b00);
                animation: pulse-bar 1s ease-in-out infinite;
            }}
            .session-card.danger::before {{
                background: linear-gradient(90deg, #ff3b3b, #ff0000);
                animation: pulse-bar 0.5s ease-in-out infinite;
            }}
            @keyframes pulse-bar {{
                0%, 100% {{ opacity: 1; }}
                50% {{ opacity: 0.4; }}
            }}
            .card-header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 12px;
            }}
            .pc-badge {{
                background: linear-gradient(135deg, #0099ff22, #00d4aa22);
                border: 1px solid #0099ff44;
                color: #00d4aa;
                font-family: 'JetBrains Mono', monospace;
                font-size: 13px;
                font-weight: 700;
                padding: 4px 10px;
                border-radius: 6px;
                letter-spacing: 1px;
            }}
            .status-dot {{
                width: 8px; height: 8px;
                background: #00d4aa;
                border-radius: 50%;
                box-shadow: 0 0 8px #00d4aa;
                animation: blink 1.5s ease-in-out infinite;
            }}
            .status-dot.warning {{ background: #ff9500; box-shadow: 0 0 8px #ff9500; }}
            .status-dot.danger {{ background: #ff3b3b; box-shadow: 0 0 8px #ff3b3b; animation-duration: 0.5s; }}
            @keyframes blink {{
                0%, 100% {{ opacity: 1; }}
                50% {{ opacity: 0.3; }}
            }}
            .customer-name {{
                color: #e8eaf6;
                font-size: 15px;
                font-weight: 600;
                margin-bottom: 4px;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }}
            .session-meta {{
                color: #6b7280;
                font-size: 11px;
                margin-bottom: 14px;
            }}
            .countdown-block {{
                background: #0d0f1a;
                border-radius: 8px;
                padding: 10px 14px;
                display: flex;
                align-items: center;
                justify-content: space-between;
            }}
            .countdown-label {{
                color: #4b5563;
                font-size: 10px;
                text-transform: uppercase;
                letter-spacing: 1.5px;
                margin-bottom: 2px;
            }}
            .countdown-time {{
                font-family: 'JetBrains Mono', monospace;
                font-size: 22px;
                font-weight: 700;
                color: #00d4aa;
                letter-spacing: 2px;
                line-height: 1;
            }}
            .countdown-time.warning {{ color: #ff9500; }}
            .countdown-time.danger {{ color: #ff3b3b; }}
            .progress-wrap {{
                flex: 1;
                margin-left: 14px;
            }}
            .progress-bar-bg {{
                background: #1e2030;
                border-radius: 4px;
                height: 6px;
                overflow: hidden;
                margin-top: 6px;
            }}
            .progress-bar-fill {{
                height: 100%;
                border-radius: 4px;
                background: linear-gradient(90deg, #00d4aa, #0099ff);
                transition: width 1s linear;
            }}
            .progress-bar-fill.warning {{ background: linear-gradient(90deg, #ff9500, #ffcc00); }}
            .progress-bar-fill.danger {{ background: linear-gradient(90deg, #ff3b3b, #ff6b6b); }}
            .progress-pct {{
                color: #6b7280;
                font-size: 10px;
                text-align: right;
                margin-top: 3px;
            }}
            .clock-strip {{
                text-align: center;
                padding: 10px 0 4px;
                color: #374151;
                font-family: 'JetBrains Mono', monospace;
                font-size: 12px;
                letter-spacing: 1px;
            }}
            #live-clock {{
                color: #4b5563;
                font-size: 11px;
            }}
        </style>

        <div class="monitor-wrapper">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
                <span style="color:#6b7280; font-size:12px; letter-spacing:1px; text-transform:uppercase;">Live Monitor</span>
                <span id="live-clock" style="font-family:'JetBrains Mono',monospace;">--:--:--</span>
            </div>
            <div class="monitor-grid" id="session-grid"></div>
        </div>

        <script>
        const sessions = {sessions_json};

        function parseDate(str) {{
            // Handle format: "2026-04-15 22:01:03.349012"
            return new Date(str.replace(' ', 'T'));
        }}

        function formatCountdown(ms) {{
            if (ms <= 0) return '00:00:00';
            const totalSec = Math.floor(ms / 1000);
            const h = Math.floor(totalSec / 3600);
            const m = Math.floor((totalSec % 3600) / 60);
            const s = totalSec % 60;
            return [h,m,s].map(v => String(v).padStart(2,'0')).join(':');
        }}

        function formatTime(dateStr) {{
            const d = parseDate(dateStr);
            return d.toLocaleTimeString('id-ID', {{hour:'2-digit', minute:'2-digit'}});
        }}

        function getState(ms, totalMs) {{
            const pct = ms / totalMs;
            if (ms <= 0) return 'danger';
            if (pct <= 0.15) return 'danger';
            if (pct <= 0.30) return 'warning';
            return 'normal';
        }}

        function buildCards() {{
            const grid = document.getElementById('session-grid');
            grid.innerHTML = '';
            sessions.forEach((s, i) => {{
                const card = document.createElement('div');
                card.className = 'session-card';
                card.id = 'card-' + i;
                card.innerHTML = `
                    <div class="card-header">
                        <span class="pc-badge">PC ${{s.pc}}</span>
                        <span class="status-dot" id="dot-${{i}}"></span>
                    </div>
                    <div class="customer-name">${{s.name}}</div>
                    <div class="session-meta">Mulai ${{formatTime(s.start)}} &rarr; Selesai ${{formatTime(s.end)}} &bull; ${{s.duration}} menit</div>
                    <div class="countdown-block">
                        <div>
                            <div class="countdown-label">Sisa Waktu</div>
                            <div class="countdown-time" id="timer-${{i}}">--:--:--</div>
                        </div>
                        <div class="progress-wrap">
                            <div class="progress-bar-bg">
                                <div class="progress-bar-fill" id="bar-${{i}}" style="width:100%"></div>
                            </div>
                            <div class="progress-pct" id="pct-${{i}}">100%</div>
                        </div>
                    </div>
                `;
                grid.appendChild(card);
            }});
        }}

        function tick() {{
            const now = new Date();
            // Live clock
            document.getElementById('live-clock').textContent = now.toLocaleTimeString('id-ID');

            sessions.forEach((s, i) => {{
                const endTime = parseDate(s.end);
                const startTime = parseDate(s.start);
                const totalMs = endTime - startTime;
                const remainMs = endTime - now;
                const pct = Math.max(0, Math.min(100, (remainMs / totalMs) * 100));
                const state = getState(remainMs, totalMs);

                const timerEl = document.getElementById('timer-' + i);
                const barEl = document.getElementById('bar-' + i);
                const pctEl = document.getElementById('pct-' + i);
                const dotEl = document.getElementById('dot-' + i);
                const cardEl = document.getElementById('card-' + i);

                if (timerEl) {{
                    timerEl.textContent = remainMs > 0 ? formatCountdown(remainMs) : 'HABIS';
                    timerEl.className = 'countdown-time' + (state !== 'normal' ? ' ' + state : '');
                }}
                if (barEl) {{
                    barEl.style.width = pct.toFixed(1) + '%';
                    barEl.className = 'progress-bar-fill' + (state !== 'normal' ? ' ' + state : '');
                }}
                if (pctEl) pctEl.textContent = pct.toFixed(0) + '%';
                if (dotEl) dotEl.className = 'status-dot' + (state !== 'normal' ? ' ' + state : '');
                if (cardEl) cardEl.className = 'session-card' + (state !== 'normal' ? ' ' + state : '');
            }});
        }}

        buildCards();
        tick();
        setInterval(tick, 1000);
        </script>
        """

        st.components.v1.html(countdown_html, height=max(200, (len(sessions_js) // 3 + 1) * 220 + 80), scrolling=False)

        # Auto-refresh halaman setiap 60 detik untuk sync data dari DB
        st.caption("🔄 Data otomatis diperbarui setiap 60 detik")
        st.markdown("""
        <script>
            setTimeout(function() {{ window.location.reload(); }}, 60000);
        </script>
        """, unsafe_allow_html=True)

    else:
        st.info("Tidak ada sesi aktif")

# ==================== PETA PC ====================
elif menu == "🖥️ Peta PC":
    st.title("🖥️ Peta Komputer Warnet")
    st.markdown("---")
    
    computers = db.get_all_computers()
    
    # Tampilkan dalam grid (3 kolom)
    cols = st.columns(5)
    
    for idx, row in computers.iterrows():
        col_idx = idx % 5
        with cols[col_idx]:
            if row['status'] == 'available':
                status_color = "pc-available"
                status_text = "🟢 TERSEDIA"
            elif row['status'] == 'occupied':
                status_color = "pc-occupied"
                status_text = "🔴 TERPAKAI"
            else:
                status_color = "pc-offline"
                status_text = "⚫ OFFLINE"
            
            st.markdown(f"""
            <div class="{status_color}">
                <h3>PC {row['pc_number']}</h3>
                <small>{status_text}</small>
            </div>
            """, unsafe_allow_html=True)
            
            if row['status'] == 'occupied':
                st.caption(f"👤 {row['current_user']}")
            
            st.markdown("<br>", unsafe_allow_html=True)
    
    # Form untuk tambah waktu atau hentikan sesi
    st.markdown("---")
    st.subheader("🔧 Kontrol PC")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Tambah Waktu**")
        pc_to_add = st.selectbox("Pilih PC", 
                                 computers[computers['status'] == 'occupied']['pc_number'].tolist() if not computers[computers['status'] == 'occupied'].empty else ["Tidak ada"],
                                 key="add_time")
        additional_minutes = st.number_input("Tambah (menit)", min_value=15, max_value=240, step=15, key="add_min")
        
        if st.button("⏰ Tambah Waktu", key="btn_add"):
            if pc_to_add != "Tidak ada":
                pc_id = computers[computers['pc_number'] == pc_to_add]['id'].values[0]
                db.add_time_session(pc_id, additional_minutes)
                st.success(f"Berhasil menambah {additional_minutes} menit untuk PC {pc_to_add}")
                st.rerun()
            else:
                st.warning("Tidak ada PC yang sedang terpakai")
    
    with col2:
        st.markdown("**Hentikan Sesi**")
        pc_to_end = st.selectbox("Pilih PC", 
                                 computers[computers['status'] == 'occupied']['pc_number'].tolist() if not computers[computers['status'] == 'occupied'].empty else ["Tidak ada"],
                                 key="end_session")
        
        if st.button("🛑 Hentikan Sesi", key="btn_end"):
            if pc_to_end != "Tidak ada":
                active = db.get_active_sessions()
                pc_id = computers[computers['pc_number'] == pc_to_end]['id'].values[0]
                session = active[active['pc_id'] == pc_id]
                if not session.empty:
                    db.end_session(session.iloc[0]['id'], pc_id)
                    st.success(f"Sesi PC {pc_to_end} telah dihentikan")
                    st.rerun()
            else:
                st.warning("Tidak ada PC yang sedang terpakai")

# ==================== KASIR ====================
elif menu == "💰 Kasir":
    st.title("💰 Kasir Warnet")
    st.markdown("---")
    
    packages = db.get_packages()
    computers = db.get_all_computers()
    available_pcs = computers[computers['status'] == 'available']
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("🖥️ Pilih PC")
        if not available_pcs.empty:
            selected_pc = st.selectbox("Nomor PC", available_pcs['pc_number'].tolist())
        else:
            st.warning("⚠️ Semua PC sedang terpakai!")
            selected_pc = None
    
    with col2:
        st.subheader("👤 Data Pelanggan")
        customer_name = st.text_input("Nama Pelanggan", placeholder="Masukkan nama")
    
    st.markdown("---")
    
    # Pilihan paket
    st.subheader("📦 Pilih Paket")
    
    # Tampilkan paket dalam bentuk tombol
    if not packages.empty:
        package_cols = st.columns(len(packages))

        # Fix: simpan pilihan paket di session_state agar tidak hilang saat rerun
        if 'selected_package' not in st.session_state:
            st.session_state.selected_package = None

        for idx, row in packages.iterrows():
            with package_cols[idx]:
                hours = row['duration_minutes'] // 60
                mins = row['duration_minutes'] % 60
                duration_text = f"{hours} Jam" if mins == 0 else f"{hours} Jam {mins} Menit"

                is_selected = (
                    st.session_state.selected_package is not None and
                    st.session_state.selected_package['id'] == row['id']
                )
                label = f"✅ {row['name']}\n{duration_text}\nRp {row['price']:,.0f}" if is_selected else f"📦 {row['name']}\n{duration_text}\nRp {row['price']:,.0f}"

                if st.button(label, key=f"pkg_{row['id']}", use_container_width=True):
                    st.session_state.selected_package = row

        selected_package = st.session_state.selected_package
        if selected_package is not None:
            st.success(f"Paket dipilih: **{selected_package['name']}** - Rp {selected_package['price']:,.0f}")
    
    # Form manual (custom durasi)
    st.markdown("---")
    st.subheader("⚙️ Custom Durasi")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        custom_hours = st.number_input("Jam", min_value=0, max_value=12, value=0)
    with col2:
        custom_minutes = st.number_input("Menit", min_value=0, max_value=59, value=30)
    with col3:
        total_custom_minutes = (custom_hours * 60) + custom_minutes
        if total_custom_minutes > 0:
            custom_price = total_custom_minutes * 100  # Rp 100 per menit
            st.metric("Total Harga", f"Rp {custom_price:,.0f}")
        else:
            st.info("Masukkan durasi")
    
    # Proses transaksi
    st.markdown("---")
    
    if st.button("✅ MULAI SESI", type="primary", use_container_width=True):
        if selected_pc is None:
            st.error("Tidak ada PC yang tersedia!")
        elif not customer_name:
            st.error("Masukkan nama pelanggan!")
        else:
            pc_id = available_pcs[available_pcs['pc_number'] == selected_pc]['id'].values[0]
            
            if selected_package is not None:
                duration = selected_package['duration_minutes']
                price = selected_package['price']
            elif total_custom_minutes > 0:
                duration = total_custom_minutes
                price = custom_price
            else:
                st.error("Pilih paket atau masukkan durasi!")
                st.stop()
            
            db.start_session(pc_id, customer_name, duration, price)
            st.success(f"✅ Sesi dimulai!\nPC {selected_pc} - {customer_name} - {duration} menit - Rp {price:,.0f}")
            st.session_state.selected_package = None  # Reset pilihan paket
            st.balloons()
            st.rerun()


# ==================== MANAJEMEN HARGA ====================
elif menu == "⚙️ Manajemen Harga":
    st.title("⚙️ Manajemen Harga & Paket")
    st.markdown("---")
    
    # Tampilkan paket yang ada
    st.subheader("📦 Daftar Paket Aktif")
    packages = db.get_packages()
    
    if not packages.empty:
        # Tabel paket
        display_packages = packages[['name', 'duration_minutes', 'price']]
        display_packages['duration_minutes'] = display_packages['duration_minutes'].apply(
            lambda x: f"{x//60} Jam" if x % 60 == 0 else f"{x//60} Jam {x%60} Menit"
        )
        display_packages['price'] = display_packages['price'].apply(lambda x: f"Rp {x:,.0f}")
        display_packages.columns = ['Nama Paket', 'Durasi', 'Harga']
        st.dataframe(display_packages, use_container_width=True)
    else:
        st.info("Belum ada paket. Silakan tambahkan.")
    
    st.markdown("---")
    
    # Form tambah paket
    st.subheader("➕ Tambah Paket Baru")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        new_name = st.text_input("Nama Paket", placeholder="Contoh: Paket Gaming")
    with col2:
        new_hours = st.number_input("Durasi (Jam)", min_value=0, max_value=12, value=1, key="new_hours")
        new_mins = st.number_input("Durasi (Menit Tambahan)", min_value=0, max_value=59, value=0, key="new_mins")
        new_duration = (new_hours * 60) + new_mins
        st.caption(f"Total: {new_duration} menit")
    with col3:
        new_price = st.number_input("Harga (Rp)", min_value=0, step=1000, value=5000, key="new_price")
    
    if st.button("💾 Simpan Paket", key="save_package"):
        if new_name and new_duration > 0 and new_price > 0:
            try:
                db.add_package(new_name, new_duration, new_price)
                st.success(f"Paket '{new_name}' berhasil ditambahkan!")
                st.rerun()
            except Exception as e:
                st.error(f"Gagal menambahkan: {e}")
        else:
            st.warning("Isi semua field dengan benar!")
    
    st.markdown("---")
    
    # Informasi harga default
    st.info("💡 **Informasi:** Harga default adalah Rp 100 per menit (Rp 6.000 per jam). Anda bisa membuat paket dengan harga khusus di atas.")


    st.title("🗄️ Data Warehouse & Proses ETL")
    st.markdown("---")

    etl.init_warehouse()

    tab_etl, tab_schema, tab_log = st.tabs([
        "▶️ Jalankan ETL",
        "🗂️ Skema Data Warehouse",
        "📋 Log ETL"
    ])

    # ── Tab ETL ──────────────────────────────────────────────
    with tab_etl:
        st.subheader("▶️ Proses ETL (Extract → Transform → Load)")

        st.markdown("""
        **Alur kerja ETL:**
        1. **Extract** — Mengambil data sesi selesai dari database operasional (`warnet.db`)
        2. **Transform** — Membersihkan data, memperkaya dimensi waktu (hari, minggu, bulan, kuartal), dan memetakan ke star schema
        3. **Load** — Memasukkan data ke tabel fakta & dimensi di Data Warehouse (`warehouse.db`)
        """)

        st.markdown("---")

        # Ringkasan DW saat ini
        summary = etl.get_dw_summary()
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("📊 Fact Sessions", summary['fact_sessions'])
        with col2:
            st.metric("📅 Dim. Waktu", summary['dim_time'])
        with col3:
            st.metric("💻 Dim. PC", summary['dim_pc'])
        with col4:
            st.metric("📦 Dim. Paket", summary['dim_package'])

        st.markdown("---")

        # Tombol jalankan ETL
        col_btn, col_info = st.columns([1, 3])
        with col_btn:
            run_btn = st.button("▶️ Jalankan ETL Sekarang", type="primary", use_container_width=True)
        with col_info:
            st.info("ETL hanya memproses data baru (incremental). Data yang sudah ada di DW tidak akan digandakan.")

        if run_btn:
            with st.spinner("Menjalankan ETL... Extract → Transform → Load"):
                result = etl.run_etl()

            if result['status'] == 'success':
                st.success(f"✅ ETL Berhasil! {result['message']}")
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("📤 Diekstrak", result['rows_extracted'])
                with col2:
                    st.metric("🔄 Ditransformasi", result['rows_transformed'])
                with col3:
                    st.metric("📥 Dimuat", result['rows_loaded'])
                st.rerun()
            else:
                st.error(f"❌ ETL Gagal: {result['message']}")

    # ── Tab Skema ────────────────────────────────────────────
    with tab_schema:
        st.subheader("🗂️ Arsitektur Star Schema Data Warehouse")

        st.markdown("""
        Data Warehouse ini menggunakan **Star Schema** yang terdiri dari:
        - **1 Tabel Fakta** → `fact_sessions` (pusat analisis)
        - **3 Tabel Dimensi** → `dim_time`, `dim_pc`, `dim_package`
        """)

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**📊 fact_sessions** *(Tabel Fakta)*")
            fact_schema = pd.DataFrame({
                'Kolom'  : ['fact_id','session_id','time_id','pc_id','package_id',
                            'customer_name','start_hour','duration_minutes',
                            'total_price','revenue_per_min'],
                'Tipe'   : ['INT PK','INT (FK)','INT (FK)','INT (FK)','INT (FK)',
                            'TEXT','INT','INT','INT','REAL'],
                'Keterangan': ['Primary Key','ID sesi dari OLTP','FK ke dim_time',
                               'FK ke dim_pc','FK ke dim_package','Nama pelanggan',
                               'Jam mulai (0–23)','Durasi menit',
                               'Total pembayaran','Pendapatan per menit']
            })
            st.dataframe(fact_schema, use_container_width=True, hide_index=True)

            st.markdown("**📅 dim_time** *(Dimensi Waktu)*")
            time_schema = pd.DataFrame({
                'Kolom'     : ['time_id','full_date','day_of_week','day_number',
                               'week_number','month_number','month_name','quarter','year','is_weekend'],
                'Keterangan': ['PK','Tanggal lengkap','Nama hari','Nomor hari (0=Senin)',
                               'Nomor minggu ISO','Bulan (1–12)','Nama bulan',
                               'Kuartal (1–4)','Tahun','1=Akhir pekan']
            })
            st.dataframe(time_schema, use_container_width=True, hide_index=True)

        with col2:
            st.markdown("**💻 dim_pc** *(Dimensi PC)*")
            pc_schema = pd.DataFrame({
                'Kolom'     : ['pc_id','pc_number','specs'],
                'Keterangan': ['PK (sama dengan OLTP)','Nomor PC','Spesifikasi PC']
            })
            st.dataframe(pc_schema, use_container_width=True, hide_index=True)

            st.markdown("**📦 dim_package** *(Dimensi Paket)*")
            pkg_schema = pd.DataFrame({
                'Kolom'     : ['package_id','duration_minutes','duration_label','price_per_minute'],
                'Keterangan': ['PK','Durasi dalam menit','Label durasi (mis. 2 Jam)',
                               'Harga per menit (Rp)']
            })
            st.dataframe(pkg_schema, use_container_width=True, hide_index=True)

            st.markdown("**📋 etl_log** *(Audit Trail ETL)*")
            log_schema = pd.DataFrame({
                'Kolom'     : ['log_id','run_timestamp','rows_extracted',
                               'rows_transformed','rows_loaded','status','message'],
                'Keterangan': ['PK','Waktu eksekusi','Baris diekstrak',
                               'Baris ditransformasi','Baris dimuat',
                               'success / error','Pesan hasil']
            })
            st.dataframe(log_schema, use_container_width=True, hide_index=True)

        # Diagram relasi (teks)
        st.markdown("---")
        st.markdown("**🔗 Relasi Star Schema:**")
        st.code("""
        dim_time ──────┐
                       │
        dim_pc ────────┼──── fact_sessions
                       │
        dim_package ───┘
        """, language=None)

    # ── Tab Log ──────────────────────────────────────────────
    with tab_log:
        st.subheader("📋 Riwayat Eksekusi ETL")

        log_df = etl.query_etl_log()

        if log_df.empty:
            st.info("Belum ada riwayat ETL. Jalankan ETL terlebih dahulu.")
        else:
            for _, row in log_df.iterrows():
                icon = "✅" if row['status'] == 'success' else "❌"
                with st.expander(f"{icon} {row['run_timestamp']} — {row['message'][:60]}..."):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Diekstrak", row['rows_extracted'])
                    with col2:
                        st.metric("Ditransformasi", row['rows_transformed'])
                    with col3:
                        st.metric("Dimuat", row['rows_loaded'])
                    st.caption(f"Status: **{row['status']}** | {row['message']}")