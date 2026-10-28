import streamlit as st
import streamlit.components.v1 as components
from supabase import create_client, Client
import bcrypt
from datetime import datetime
import html

# -----------------------------------------------------------------------------
# 0. KONFIGURASI HALAMAN & INTI DATABASE
# -----------------------------------------------------------------------------
st.set_page_config(page_title="ASCII Chat & Signal Lab", page_icon="💬", layout="wide")

@st.cache_resource
def get_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = get_supabase()

# Inisialisasi Sesi
if "user" not in st.session_state:
    st.session_state.user = None
if "active_contact" not in st.session_state:
    st.session_state.active_contact = None

# -----------------------------------------------------------------------------
# 1. MODUL AUTENTIKASI & SANDI
# -----------------------------------------------------------------------------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def check_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))

def register_user(user_id: str, email: str, password: str) -> bool:
    try:
        pw_hash = hash_password(password)
        supabase.table("users").insert({
            "user_id": user_id,
            "email": email,
            "password_hash": pw_hash
        }).execute()
        return True
    except Exception as e:
        st.error(f"Gagal mendaftar: {e}")
        return False

def login_user(user_id: str, email: str, password: str):
    res = supabase.table("users").select("*").eq("user_id", user_id).eq("email", email).execute()
    if res.data:
        user_data = res.data[0]
        if check_password(password, user_data["password_hash"]):
            return user_data
    return None

def render_auth_view():
    st.title("🔐 Akses Sistem Komunikasi Data")
    tab_masuk, tab_daftar = st.tabs(["Masuk", "Daftar"])

    with tab_masuk:
        st.subheader("Login Pengguna")
        u_id = st.text_input("ID Pengguna", key="l_id")
        u_email = st.text_input("Email", key="l_email")
        u_pass = st.text_input("Password", type="password", key="l_pass")
        
        if st.button("Masuk", type="primary"):
            if not (u_id and u_email and u_pass):
                st.warning("Semua bidang input wajib diisi.")
            else:
                user = login_user(u_id, u_email, u_pass)
                if user:
                    st.session_state.user = user
                    st.rerun()
                else:
                    st.error("Kombinasi ID Pengguna, Email, dan Password tidak cocok.")

    with tab_daftar:
        st.subheader("Pendaftaran Akun Baru")
        reg_id = st.text_input("ID Pengguna (Unik)", key="r_id")
        reg_email = st.text_input("Email (Unik)", key="r_email")
        reg_pass = st.text_input("Password (min. 6 karakter)", type="password", key="r_pass")
        reg_pass_confirm = st.text_input("Konfirmasi Password", type="password", key="r_pass_confirm")

        if st.button("Daftar"):
            if not (reg_id and reg_email and reg_pass and reg_pass_confirm):
                st.warning("Semua bidang input wajib diisi.")
            elif len(reg_pass) < 6:
                st.warning("Password minimal 6 karakter.")
            elif reg_pass != reg_pass_confirm:
                st.error("Konfirmasi password tidak cocok.")
            else:
                if register_user(reg_id, reg_email, reg_pass):
                    st.success("Pendaftaran berhasil! Silakan berpindah ke tab 'Masuk'.")

# -----------------------------------------------------------------------------
# 2. LOGIKA ASCII ENCODING & PARITY (EVEN)
# -----------------------------------------------------------------------------
def validate_ascii(text: str):
    for ch in text:
        code = ord(ch)
        if code < 32 or code > 126:
            u_hex = f"U+{code:04X}"
            return False, f"Karakter '{ch}' ({u_hex}) tidak didukung. Hanya ASCII 7 bit (kode 32-126)."
    return True, ""

def get_char_analysis(ch: str):
    code = ord(ch)
    hex_str = f"{code:02X}"
    bin_7bit = f"{code:07b}"  # MSB first
    ones_count = bin_7bit.count('1')
    parity_even = 1 if (ones_count % 2 != 0) else 0
    
    # Structure 10-bit frame: S(0) + 7-bit + P + E(1)
    frame_bits = f"0{bin_7bit}{parity_even}1"
    
    return {
        "char": ch,
        "ascii_code": code,
        "hex": hex_str,
        "bin_7bit": bin_7bit,
        "parity_even": parity_even,
        "end": 1,
        "frame_bits": frame_bits
    }

# -----------------------------------------------------------------------------
# 3. PENGGAMBAR SINYAL SVG NRZ-I
# -----------------------------------------------------------------------------
def generate_nrzi_svg(text: str, initial_level: str = "LOW") -> str:
    if not text:
        return "<p>Tidak ada pesan untuk ditampilkan.</p>"

    frames = [get_char_analysis(ch) for ch in text]
    
    # Konfigurasi SVG Dimensi
    bit_width = 24
    top_margin = 40
    wave_top = 70
    wave_bottom = 150
    bottom_text_y = 180
    bracket_y = 205
    label_y = 225
    height = 250
    
    total_bits = len(frames) * 10
    width = max(800, total_bits * bit_width + 40)
    
    current_level = 0 if initial_level == "LOW" else 1  # 0: Low (-V), 1: High (+V)
    
    svg_parts = []
    svg_parts.append(f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg" style="background-color:#ffffff; font-family: monospace;">')
    
    # Sub-fungsi menggambar kurung siku penyangga bit
    def draw_bracket(x1, x2, y, text_label):
        mid = (x1 + x2) / 2
        return f'''
            <path d="M {x1+2} {y} L {x1+2} {y+6} L {x2-2} {y+6} L {x2-2} {y}" stroke="#444" stroke-width="1.5" fill="none"/>
            <text x="{mid}" y="{y+20}" font-size="11" text-anchor="middle" fill="#333">{text_label}</text>
        '''

    global_bit_idx = 0
    wave_path = ""
    
    for f_idx, frame in enumerate(frames):
        frame_start_x = global_bit_idx * bit_width + 20
        frame_end_x = frame_start_x + 10 * bit_width
        
        # Header Karakter
        escaped_char = html.escape(frame["char"])
        svg_parts.append(f'<text x="{(frame_start_x + frame_end_x)/2}" y="25" font-size="14" font-weight="bold" text-anchor="middle" fill="#111">Huruf {escaped_char}</text>')
        
        # Line Batas Frame (Sebelah Kiri)
        svg_parts.append(f'<line x1="{frame_start_x}" y1="35" x2="{frame_start_x}" y2="{wave_bottom+10}" stroke="#000" stroke-width="2"/>')
        
        for b_idx, bit_char in enumerate(frame["frame_bits"]):
            x1 = (global_bit_idx) * bit_width + 20
            x2 = x1 + bit_width
            
            # Pembagi Bit Sub-kolom
            if b_idx > 0:
                svg_parts.append(f'<line x1="{x1}" y1="55" x2="{x1}" y2="{wave_bottom+5}" stroke="#e0e0e0" stroke-width="1" stroke-dasharray="3,3"/>')
            
            # Kalkulasi NRZ-I
            bit_val = int(bit_char)
            if bit_val == 1:
                current_level = 1 - current_level  # Invert level pada bit 1
            
            y_val = wave_top if current_level == 1 else wave_bottom
            
            if global_bit_idx == 0:
                wave_path += f"M {x1} {y_val} L {x2} {y_val} "
            else:
                wave_path += f"L {x1} {y_val} L {x2} {y_val} "

            # Teks Bit Nilai
            svg_parts.append(f'<text x="{(x1+x2)/2}" y="{bottom_text_y}" font-size="13" font-weight="bold" text-anchor="middle" fill="#222">{bit_char}</text>')
            
            global_bit_idx += 1

        # Kurung & Label bagian bawah frame
        svg_parts.append(draw_bracket(frame_start_x, frame_start_x + bit_width, bracket_y, "S"))
        svg_parts.append(draw_bracket(frame_start_x + bit_width, frame_start_x + 8*bit_width, bracket_y, f'Data "{escaped_char}"'))
        svg_parts.append(draw_bracket(frame_start_x + 8*bit_width, frame_start_x + 9*bit_width, bracket_y, "P"))
        svg_parts.append(draw_bracket(frame_start_x + 9*bit_width, frame_end_x, bracket_y, "E"))

    # Line Batas Frame Paling Akhir
    last_x = global_bit_idx * bit_width + 20
    svg_parts.append(f'<line x1="{last_x}" y1="35" x2="{last_x}" y2="{wave_bottom+10}" stroke="#000" stroke-width="2"/>')

    # Gelombang Sinyal Utama
    svg_parts.append(f'<path d="{wave_path}" stroke="#1D9E75" stroke-width="3.5" fill="none" stroke-linejoin="miter"/>')
    svg_parts.append('</svg>')

    return "".join(svg_parts)

# -----------------------------------------------------------------------------
# 4. MODUL PESAN & DUKUNGAN REALTIME (POLLING)
# -----------------------------------------------------------------------------
def fetch_contacts(user_id: str):
    res = supabase.table("contacts").select("contact_id").eq("user_id", user_id).execute()
    return [item["contact_id"] for item in res.data]

def add_contact(user_id: str, contact_id: str):
    if user_id == contact_id:
        return False, "Tidak dapat menambahkan diri sendiri."
    
    # Cek ketersediaan target user
    u_check = supabase.table("users").select("user_id").eq("user_id", contact_id).execute()
    if not u_check.data:
        return False, "ID Pengguna tidak ditemukan."
    
    try:
        supabase.table("contacts").insert({"user_id": user_id, "contact_id": contact_id}).execute()
        # Otomatis menambahkan hubungan timbal balik
        supabase.table("contacts").upsert({"user_id": contact_id, "contact_id": user_id}).execute()
        return True, "Kontak berhasil ditambahkan."
    except Exception as e:
        return False, "Kontak sudah ada dalam daftar."

def fetch_messages(user_id: str, contact_id: str):
    res = supabase.table("messages").select("*").or_(
        f"and(sender_id.eq.{user_id},receiver_id.eq.{contact_id}),and(sender_id.eq.{contact_id},receiver_id.eq.{user_id})"
    ).order("created_at", desc=False).execute()
    return res.data

def send_message(sender_id: str, receiver_id: str, text: str):
    valid, err_msg = validate_ascii(text)
    if not valid:
        return False, err_msg
    
    try:
        supabase.table("messages").insert({
            "sender_id": sender_id,
            "receiver_id": receiver_id,
            "text": text
        }).execute()
        return True, ""
    except Exception as e:
        return False, f"Gagal mengirim pesan: {e}"

@st.fragment(run_every=2)
def render_realtime_chat_box(current_user_id: str, target_user_id: str):
    messages = fetch_messages(current_user_id, target_user_id)
    
    chat_container = st.container(height=400)
    with chat_container:
        if not messages:
            st.info("Belum ada pesan. Mulai percakapan!")
        for msg in messages:
            is_me = (msg["sender_id"] == current_user_id)
            ts = datetime.fromisoformat(msg["created_at"].replace("Z", "+00:00")).strftime("%H:%M")
            align_cls = "flex-end" if is_me else "flex-start"
            bg_color = "#dcf8c6" if is_me else "#ffffff"
            
            # Gelembung Pesan
            st.markdown(f'''
                <div style="display:flex; justify-content:{align_cls}; margin-bottom:8px;">
                    <div style="background-color:{bg_color}; padding:8px 12px; border-radius:8px; max-width:70%; box-shadow:0 1px 2px rgba(0,0,0,0.15);">
                        <div style="font-size:14px; color:#111; word-wrap:break-word;">{html.escape(msg["text"])}</div>
                        <div style="font-size:10px; color:#777; text-align:right; margin-top:3px;">{ts}</div>
                    </div>
                </div>
            ''', unsafe_allow_html=True)
            
            # Expander Analisis Sinyal & Bit
            with st.expander(f"📊 Sinyal & Bit: '{msg['text']}'"):
                rows = [get_char_analysis(ch) for ch in msg["text"]]
                
                # 1. Gunakan st.dataframe (Tabel native Streamlit, 100% rapi tanpa bocor teks HTML)
                data_table = []
                for r in rows:
                    data_table.append({
                        "Karakter": r['char'],
                        "Hex": r['hex'],
                        "Biner 7 bit (MSB)": r['bin_7bit'],
                        "Parity Even": r['parity_even'],
                        "End": r['end']
                    })
                st.dataframe(data_table, use_container_width=True, hide_index=True)
                
                # 2. Render Visual Sinyal NRZ-I SVG
                st.caption("Visual Sinyal NRZ-I (Level Awal: LOW)")
                svg_code = generate_nrzi_svg(msg["text"], initial_level="LOW")
                components.html(
                    f'<div style="overflow-x:auto; background:white; padding:10px; border-radius:5px;">{svg_code}</div>',
                    height=270,
                    scrolling=True
                )
# -----------------------------------------------------------------------------
# 5. HALAMAN UTAMA APLIKASI
# -----------------------------------------------------------------------------
def render_main_view():
    user = st.session_state.user
    
    # Header Navigasi
    c_head1, c_head2 = st.columns([4, 1])
    with c_head1:
        st.subheader(f"👋 Selamat Datang, {user['user_id']}")
    with c_head2:
        if st.button("Keluar", type="secondary"):
            st.session_state.user = None
            st.session_state.active_contact = None
            st.rerun()

    st.caption("Encoding: ASCII 7 bit. ANSI, UTF-8, dan UTF-16 tidak didukung sebagai encoding aplikasi.")

    # Panel Uji Karakter (Stand Alone Tool)
    with st.expander("🧪 Panel Uji Karakter (Validator ASCII)"):
        test_input = st.text_input("Ketik kalimat/teks bebas untuk verifikasi:", "IBNU")
        if test_input:
            res_list = []
            for ch in test_input:
                code = ord(ch)
                if 32 <= code <= 126:
                    res_list.append(f"<li><b>'{html.escape(ch)}'</b> (ASCII {code}): Didukung ✅</li>")
                else:
                    res_list.append(f"<li style='color:red;'><b>'{html.escape(ch)}'</b> (Kode {code} / U+{code:04X}): <b>Tidak didukung (kode > 127 / non-printable)</b> ❌</li>")
            st.markdown(f"<ul>{''.join(res_list)}</ul>", unsafe_allow_html=True)

    st.divider()

    # Layout Utama Chat (Dua Kolom)
    col_left, col_right = st.columns([1, 2])

    with col_left:
        st.subheader("📋 Daftar Kontak")
        
        # Form Tambah Kontak
        with st.form("add_contact_form", clear_on_submit=True):
            new_c_id = st.text_input("Cari ID Pengguna")
            submitted = st.form_submit_button("Tambah Kontak")
            if submitted and new_c_id:
                ok, msg = add_contact(user["user_id"], new_c_id)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
        
        # List Kontak
        contacts = fetch_contacts(user["user_id"])
        if not contacts:
            st.info("Belum ada kontak. Tambahkan kontak berdasarkan ID.")
        else:
            for c_id in contacts:
                btn_type = "primary" if st.session_state.active_contact == c_id else "secondary"
                if st.button(f"👤 {c_id}", key=f"btn_{c_id}", use_container_width=True, type=btn_type):
                    st.session_state.active_contact = c_id
                    st.rerun()

    with col_right:
        active_contact = st.session_state.active_contact
        if not active_contact:
            st.info("👈 Pilih kontak di sebelah kiri untuk memulai obrolan.")
        else:
            st.subheader(f"💬 Percakapan dengan: {active_contact}")
            
            # Area Chat Realtime Fragment
            render_realtime_chat_box(user["user_id"], active_contact)
            
            # Form Pengiriman Pesan
            with st.form("send_msg_form", clear_on_submit=True):
                txt_input = st.text_input("Ketik pesan ASCII (Kode 32-126):", key="chat_input")
                btn_send = st.form_submit_button("Kirim Pesan", type="primary")
                
                if btn_send and txt_input:
                    ok, err = send_message(user["user_id"], active_contact, txt_input)
                    if not ok:
                        st.error(err)
                    else:
                        st.rerun()

# -----------------------------------------------------------------------------
# RUNNER UTAMA
# -----------------------------------------------------------------------------
if st.session_state.user is None:
    render_auth_view()
else:
    render_main_view()