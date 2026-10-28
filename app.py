# =============================================================================
# IMPORT LIBRARY
# =============================================================================
import streamlit as st                      # Framework utama untuk bikin web app dengan Python
import streamlit.components.v1 as components  # Dipakai untuk menampilkan HTML mentah (SVG gelombang)
from supabase import create_client, Client  # Library untuk konek ke database Supabase (Postgres)
import bcrypt                               # Library untuk hash password (biar password nggak disimpan polos)
from datetime import datetime               # Import waktu (sekarang belum terpakai di kode)
import html                                 # Untuk html.escape(), mencegah teks user merusak/menyusup ke HTML

# =============================================================================
# 0. KONFIGURASI HALAMAN & ENGINES DATABASE (SUPABASE)
# =============================================================================
# Mengatur judul tab browser, ikon tab, dan layout lebar (wide) untuk halaman
# CATATAN: set_page_config harus jadi perintah Streamlit pertama yang dipanggil
st.set_page_config(page_title="ASCII Chat & Signal Lab", page_icon="💬", layout="wide")

@st.cache_resource  # Cache koneksi supaya nggak bikin koneksi baru setiap halaman di-rerun
def get_supabase() -> Client:
    """
    Menginisialisasi koneksi tunggal ke database Supabase.
    Membaca kredensial rahasia (URL & API Key) dari st.secrets.
    """
    url = st.secrets["SUPABASE_URL"]  # Ambil URL project Supabase dari file secrets.toml
    key = st.secrets["SUPABASE_KEY"]  # Ambil API key Supabase dari file secrets.toml
    return create_client(url, key)    # Buat dan kembalikan objek koneksi

# Objek klien Supabase, dipakai di semua fungsi di bawah untuk query ke tabel
supabase = get_supabase()

# Session State = "memori" Streamlit yang bertahan walau halaman di-rerun
if "user" not in st.session_state:
    st.session_state.user = None            # None = belum login, berisi data user kalau sudah login
if "active_contact" not in st.session_state:
    st.session_state.active_contact = None  # ID kontak yang sedang dibuka obrolannya

# =============================================================================
# 1. MODUL AUTENTIKASI & KEAMANAN KATASANDI
# =============================================================================
def hash_password(password: str) -> str:
    """Mengenkripsi password teks biasa menjadi hash bcrypt dengan garam (salt)."""
    # encode -> ubah string jadi bytes (bcrypt butuh bytes)
    # gensalt() -> bikin salt acak, jadi password sama bisa menghasilkan hash berbeda
    # decode -> ubah hasil bytes balik jadi string supaya bisa disimpan di database
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def check_password(password: str, hashed: str) -> bool:
    """Memverifikasi kecocokan antara password teks biasa dan hash tersimpan."""
    # checkpw membandingkan password yang diketik dengan hash dari database
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))

def register_user(user_id: str, email: str, password: str) -> bool:
    """Memasukkan data pendaftaran pengguna baru ke dalam tabel 'users' di Supabase."""
    try:
        pw_hash = hash_password(password)  # Hash dulu password-nya sebelum disimpan
        # Insert 1 baris baru ke tabel 'users'
        supabase.table("users").insert({
            "user_id": user_id,
            "email": email,
            "password_hash": pw_hash  # Yang disimpan hash-nya, BUKAN password asli
        }).execute()
        return True  # Berhasil daftar
    except Exception as e:
        # Biasanya gagal karena user_id/email sudah dipakai (kolom unik)
        st.error(f"Gagal mendaftar: {e}")
        return False

def login_user(user_id: str, email: str, password: str):
    """Memeriksa keberadaan pengguna dan validitas password untuk proses masuk."""
    # Cari user yang user_id DAN email-nya cocok
    res = supabase.table("users").select("*").eq("user_id", user_id).eq("email", email).execute()
    if res.data:                    # Kalau ada hasilnya (user ditemukan)
        user_data = res.data[0]     # Ambil baris pertama
        if check_password(password, user_data["password_hash"]):  # Cocokkan password
            return user_data        # Login sukses, kembalikan data user
    return None                     # User nggak ketemu atau password salah

def render_auth_view():
    """Menampilkan antarmuka tab 'Masuk' dan 'Daftar' sebelum pengguna mengakses chat."""
    st.title("🔐 Akses Sistem Komunikasi Data")
    tab_masuk, tab_daftar = st.tabs(["Masuk", "Daftar"])  # Bikin 2 tab

    # --- TAB MASUK ---
    with tab_masuk:
        st.subheader("Login Pengguna")
        # key= wajib unik biar Streamlit bisa bedakan input di tab Masuk vs Daftar
        u_id = st.text_input("ID Pengguna", key="l_id")
        u_email = st.text_input("Email", key="l_email")
        u_pass = st.text_input("Password", type="password", key="l_pass")  # type=password -> teks disamarkan

        if st.button("Masuk", type="primary"):
            if not (u_id and u_email and u_pass):  # Validasi: semua kolom harus terisi
                st.warning("Semua bidang input wajib diisi.")
            else:
                user = login_user(u_id, u_email, u_pass)
                if user:
                    st.session_state.user = user  # Simpan data user -> tandanya sudah login
                    st.rerun()                    # Muat ulang halaman, nanti masuk ke tampilan utama
                else:
                    st.error("Kombinasi ID Pengguna, Email, dan Password tidak cocok.")

    # --- TAB DAFTAR ---
    with tab_daftar:
        st.subheader("Pendaftaran Akun Baru")
        reg_id = st.text_input("ID Pengguna (Unik)", key="r_id")
        reg_email = st.text_input("Email (Unik)", key="r_email")
        reg_pass = st.text_input("Password (min. 6 karakter)", type="password", key="r_pass")
        reg_pass_confirm = st.text_input("Konfirmasi Password", type="password", key="r_pass_confirm")

        if st.button("Daftar"):
            if not (reg_id and reg_email and reg_pass and reg_pass_confirm):  # Semua wajib diisi
                st.warning("Semua bidang input wajib diisi.")
            elif len(reg_pass) < 6:                # Cek panjang minimal password
                st.warning("Password minimal 6 karakter.")
            elif reg_pass != reg_pass_confirm:     # Cek password dan konfirmasinya sama
                st.error("Konfirmasi password tidak cocok.")
            else:
                if register_user(reg_id, reg_email, reg_pass):  # Simpan ke database
                    st.success("Pendaftaran berhasil! Silakan berpindah ke tab 'Masuk'.")

# =============================================================================
# 2. LOGIKA VALIDASI ASCII & KALKULASI PARITY (EVEN)
# =============================================================================
def validate_ascii(text: str):
    """
    Memvalidasi apakah seluruh karakter berada pada rentang ASCII tercetak (32-126).
    Menolak pengiriman jika terdapat karakter non-ASCII/Emoji.
    """
    for ch in text:                # Periksa karakter satu per satu
        code = ord(ch)             # ord() = ubah karakter jadi nomor ASCII/Unicode-nya
        if code < 32 or code > 126:  # Di luar rentang karakter tercetak
            u_hex = f"U+{code:04X}"  # Format kode Unicode, misal U+1F600
            return False, f"Karakter '{ch}' ({u_hex}) tidak didukung. Hanya ASCII 7 bit (kode 32-126)."
    return True, ""                # Semua karakter aman

def get_char_analysis(ch: str):
    """
    Mengonversi 1 karakter menjadi informasi bit:
    Kode Desimal, Hexadecimal, Biner 7 bit (MSB dulu), Parity Even, dan End bit (1).
    Membuat susunan frame 10 bit: S (0) + 7 bit Data + Parity (P) + End (1).
    """
    code = ord(ch)                 # Kode desimal, contoh 'A' -> 65
    hex_str = f"{code:02X}"        # Format hexadecimal huruf besar, minimal 2 digit -> '41'
    bin_7bit = f"{code:07b}"       # Format biner 7 digit (MSB dulu) -> '1000001'
    ones_count = bin_7bit.count('1')  # Hitung jumlah bit '1' di data
    parity_even = 1 if (ones_count % 2 != 0) else 0  # Parity 1 kalau jumlah '1' ganjil -> total jadi genap

    frame_bits = f"0{bin_7bit}{parity_even}1"  # Susun frame: Start(0) + Data(7) + Parity + End(1)

    # Kembalikan semua info dalam bentuk dictionary
    return {
        "char": ch,                # Karakter asli
        "ascii_code": code,        # Kode desimal
        "hex": hex_str,            # Kode hex
        "bin_7bit": bin_7bit,      # Biner 7 bit
        "parity_even": parity_even,  # Bit parity
        "end": 1,                  # End bit (selalu 1)
        "frame_bits": frame_bits   # Frame lengkap 10 bit
    }

# =============================================================================
# 3. GENERATOR GELOMBANG SINYAL NRZ-I (SVG HTML)
# =============================================================================
def generate_nrzi_svg(text: str, initial_level: str = "LOW") -> str:
    """
    Menghasilkan kode SVG gelombang digital NRZ-I dengan aturan:
    - Bit 1: Membalik level sinyal (Invert/Toggle).
    - Bit 0: Mempertahankan level sinyal sebelumnya.
    - Menggambar header karakter, pembagi frame, kurung penyangga bit (S, Data, P, E).
    """
    if not text:  # Kalau teks kosong, nggak ada yang digambar
        return "<p>Tidak ada pesan untuk ditampilkan.</p>"

    # Ubah tiap karakter jadi frame 10 bit (list of dictionary)
    frames = [get_char_analysis(ch) for ch in text]

    # --- Pengaturan dimensi gambar SVG (satuan piksel) ---
    bit_width = 24        # Lebar 1 bit di gambar
    wave_top = 70         # Posisi y garis gelombang untuk level HIGH
    wave_bottom = 150     # Posisi y garis gelombang untuk level LOW
    bottom_text_y = 180   # Posisi y angka bit (0/1) di bawah gelombang
    bracket_y = 205       # Posisi y kurung label S / Data / P / E
    height = 250          # Tinggi total gambar

    total_bits = len(frames) * 10                  # Tiap karakter = 10 bit
    width = max(800, total_bits * bit_width + 40)  # Lebar menyesuaikan jumlah bit, minimal 800

    # Level awal sinyal: LOW = 0, HIGH = 1
    current_level = 0 if initial_level == "LOW" else 1

    svg_parts = []  # Wadah potongan-potongan kode SVG, nanti digabung di akhir
    # Tag pembuka SVG (latar putih, font monospace)
    svg_parts.append(f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg" style="background-color:#ffffff; font-family: monospace;">')

    def draw_bracket(x1, x2, y, text_label):
        """Fungsi pembantu membuat kurung siku dan label bagian bawah frame."""
        mid = (x1 + x2) / 2  # Titik tengah kurung, tempat label ditulis
        # Path membentuk kurung: turun, mendatar, naik lagi. Lalu teks label di bawahnya
        return f'''
            <path d="M {x1+2} {y} L {x1+2} {y+6} L {x2-2} {y+6} L {x2-2} {y}" stroke="#444" stroke-width="1.5" fill="none"/>
            <text x="{mid}" y="{y+20}" font-size="11" text-anchor="middle" fill="#333">{text_label}</text>
        '''

    global_bit_idx = 0  # Penghitung bit keseluruhan (lintas semua karakter)
    wave_path = ""      # String path gelombang, dibangun bertahap

    # --- LOOP 1: tiap karakter/frame ---
    for f_idx, frame in enumerate(frames):
        frame_start_x = global_bit_idx * bit_width + 20  # Posisi x awal frame (offset 20 untuk margin)
        frame_end_x = frame_start_x + 10 * bit_width     # Posisi x akhir frame (10 bit)

        # Judul "Huruf X" di atas frame (di-escape biar karakter seperti < > & aman)
        escaped_char = html.escape(frame["char"])
        svg_parts.append(f'<text x="{(frame_start_x + frame_end_x)/2}" y="25" font-size="14" font-weight="bold" text-anchor="middle" fill="#111">Huruf {escaped_char}</text>')

        # Garis tebal vertikal sebagai batas kiri frame
        svg_parts.append(f'<line x1="{frame_start_x}" y1="35" x2="{frame_start_x}" y2="{wave_bottom+10}" stroke="#000" stroke-width="2"/>')

        # --- LOOP 2: tiap bit di dalam frame ---
        for b_idx, bit_char in enumerate(frame["frame_bits"]):
            x1 = (global_bit_idx) * bit_width + 20  # x awal bit ini
            x2 = x1 + bit_width                      # x akhir bit ini

            # Garis putus-putus pemisah kolom bit (dilewati untuk bit pertama karena sudah ada garis tebal)
            if b_idx > 0:
                svg_parts.append(f'<line x1="{x1}" y1="55" x2="{x1}" y2="{wave_bottom+5}" stroke="#e0e0e0" stroke-width="1" stroke-dasharray="3,3"/>')

            # ===== INTI LOGIKA NRZ-I =====
            bit_val = int(bit_char)  # Ubah karakter '0'/'1' jadi angka
            if bit_val == 1:
                current_level = 1 - current_level  # Bit 1 -> balik level (0 jadi 1, 1 jadi 0)
            # Bit 0 -> nggak ngapa-ngapain, level tetap

            # Ubah level jadi posisi y di gambar: HIGH di atas, LOW di bawah
            y_val = wave_top if current_level == 1 else wave_bottom

            # Bangun path gelombang. M = pindah titik awal, L = tarik garis
            if global_bit_idx == 0:
                wave_path += f"M {x1} {y_val} L {x2} {y_val} "  # Bit pertama: mulai dari sini
            else:
                # L x1 y_val -> garis vertikal (transisi) dari level lama ke level baru
                # L x2 y_val -> garis datar selama 1 bit
                wave_path += f"L {x1} {y_val} L {x2} {y_val} "

            # Tulis angka bit (0/1) di bawah gelombang
            svg_parts.append(f'<text x="{(x1+x2)/2}" y="{bottom_text_y}" font-size="13" font-weight="bold" text-anchor="middle" fill="#222">{bit_char}</text>')

            global_bit_idx += 1  # Lanjut ke bit berikutnya (index global terus bertambah)

        # Kurung label struktur frame: S (1 bit), Data (7 bit), P (1 bit), E (1 bit)
        svg_parts.append(draw_bracket(frame_start_x, frame_start_x + bit_width, bracket_y, "S"))
        svg_parts.append(draw_bracket(frame_start_x + bit_width, frame_start_x + 8*bit_width, bracket_y, f'Data "{escaped_char}"'))
        svg_parts.append(draw_bracket(frame_start_x + 8*bit_width, frame_start_x + 9*bit_width, bracket_y, "P"))
        svg_parts.append(draw_bracket(frame_start_x + 9*bit_width, frame_end_x, bracket_y, "E"))

    # Garis tebal batas kanan setelah frame terakhir
    last_x = global_bit_idx * bit_width + 20
    svg_parts.append(f'<line x1="{last_x}" y1="35" x2="{last_x}" y2="{wave_bottom+10}" stroke="#000" stroke-width="2"/>')

    # Gambar gelombang hijau dari path yang sudah dibangun (digambar terakhir biar di atas elemen lain)
    svg_parts.append(f'<path d="{wave_path}" stroke="#1D9E75" stroke-width="3.5" fill="none" stroke-linejoin="miter"/>')
    svg_parts.append('</svg>')  # Tutup tag SVG

    return "".join(svg_parts)  # Gabungkan semua potongan jadi satu string SVG

# =============================================================================
# 4. MODUL QUERY DATABASE & POLLING REALTIME PESAN
# =============================================================================
def fetch_contacts(user_id: str):
    """Mengambil daftar ID kontak yang terhubung dengan pengguna saat ini."""
    # Ambil kolom contact_id dari baris yang user_id-nya = user yang login
    res = supabase.table("contacts").select("contact_id").eq("user_id", user_id).execute()
    return [item["contact_id"] for item in res.data]  # Ubah jadi list ID saja

def add_contact(user_id: str, contact_id: str):
    """Menambahkan hubungan kontak dua arah (timbal balik) di database."""
    if user_id == contact_id:  # Cegah menambah diri sendiri
        return False, "Tidak dapat menambahkan diri sendiri."

    # Pastikan ID yang dicari memang ada di tabel users
    u_check = supabase.table("users").select("user_id").eq("user_id", contact_id).execute()
    if not u_check.data:
        return False, "ID Pengguna tidak ditemukan."

    try:
        # Simpan A -> B
        supabase.table("contacts").insert({"user_id": user_id, "contact_id": contact_id}).execute()
        # Simpan B -> A (upsert = insert, atau update kalau sudah ada) supaya dua arah
        supabase.table("contacts").upsert({"user_id": contact_id, "contact_id": user_id}).execute()
        return True, "Kontak berhasil ditambahkan."
    except Exception as e:
        # Biasanya error karena pasangan kontak sudah ada (duplikat)
        return False, "Kontak sudah ada dalam daftar."

def fetch_messages(user_id: str, contact_id: str):
    """Mengambil riwayat percakapan antara dua pengguna dari tabel 'messages'."""
    # Ambil pesan yang (A kirim ke B) ATAU (B kirim ke A), jadi dua arah
    res = supabase.table("messages").select("*").or_(
        f"and(sender_id.eq.{user_id},receiver_id.eq.{contact_id}),and(sender_id.eq.{contact_id},receiver_id.eq.{user_id})"
    ).order("created_at", desc=False).execute()  # Urut dari yang terlama ke terbaru
    return res.data

def send_message(sender_id: str, receiver_id: str, text: str):
    """Validasi ASCII dan pengiriman pesan baru ke database Supabase."""
    valid, err_msg = validate_ascii(text)  # Cek dulu semua karakternya ASCII 32-126
    if not valid:
        return False, err_msg              # Tolak kalau ada karakter terlarang

    try:
        # Simpan pesan ke tabel 'messages'
        supabase.table("messages").insert({
            "sender_id": sender_id,
            "receiver_id": receiver_id,
            "text": text
        }).execute()
        return True, ""
    except Exception as e:
        return False, f"Gagal mengirim pesan: {e}"

@st.fragment(run_every=2)  # Fungsi ini otomatis dijalankan ulang tiap 2 detik (tanpa rerun seluruh halaman)
def render_realtime_chat_box(current_user_id: str, target_user_id: str):
    """
    Fragment Realtime Streamlit:
    Melakukan polling ke database setiap 2 detik untuk menyegarkan percakapan,
    tabel analisis bit (st.dataframe), dan visualisasi gelombang NRZ-I.
    """
    messages = fetch_messages(current_user_id, target_user_id)  # Ambil pesan terbaru dari database

    chat_container = st.container(height=400)  # Kotak chat dengan tinggi tetap + bisa di-scroll
    with chat_container:
        if not messages:
            st.info("Belum ada pesan. Mulai percakapan!")
        for msg in messages:
            is_me = (msg["sender_id"] == current_user_id)     # Pesan dari kita atau dari lawan?
            align_cls = "flex-end" if is_me else "flex-start"  # Pesan kita di kanan, lawan di kiri
            bg_color = "#dcf8c6" if is_me else "#ffffff"       # Hijau muda untuk kita, putih untuk lawan

            # Gelembung pesan (HTML kustom). html.escape mencegah teks user disisipi kode HTML/script
            st.markdown(f'''
                <div style="display:flex; justify-content:{align_cls}; margin-bottom:8px;">
                    <div style="background-color:{bg_color}; padding:8px 12px; border-radius:8px; max-width:70%; box-shadow:0 1px 2px rgba(0,0,0,0.15);">
                        <div style="font-size:14px; color:#111; word-wrap:break-word;">{html.escape(msg["text"])}</div>
                    </div>
                </div>
            ''', unsafe_allow_html=True)

            # Expander (kotak lipat) berisi analisis bit & sinyal untuk pesan ini
            with st.expander(f"📊 Sinyal & Bit: '{msg['text']}'"):
                rows = [get_char_analysis(ch) for ch in msg["text"]]  # Analisis tiap karakter

                # Susun data untuk tabel: 1 baris = 1 karakter
                data_table = []
                for r in rows:
                    data_table.append({
                        "Karakter": r['char'],
                        "Kode": r['ascii_code'],
                        "Hex": r['hex'],
                        "Biner 7 bit (MSB)": r['bin_7bit'],
                        "Parity Even": r['parity_even'],
                        "End": r['end']
                    })
                st.dataframe(data_table, use_container_width=True, hide_index=True)  # Tampilkan tabel

                # Gambar gelombang NRZ-I untuk pesan ini
                st.caption("Visual Sinyal NRZ-I (Level Awal: LOW)")
                svg_code = generate_nrzi_svg(msg["text"], initial_level="LOW")
                # components.html dipakai karena st.markdown kurang cocok untuk SVG besar
                components.html(
                    f'<div style="overflow-x:auto; background:white; padding:10px; border-radius:5px;">{svg_code}</div>',
                    height=270,       # Tinggi area tampilan
                    scrolling=True    # Bisa di-scroll kalau gambar lebih lebar dari kotak
                )

# =============================================================================
# 5. HALAMAN UTAMA APLIKASI
# =============================================================================
def render_main_view():
    """Tampilan utama setelah pengguna berhasil masuk/login."""
    user = st.session_state.user  # Ambil data user yang sedang login

    # Bilah atas: sapaan di kiri, tombol Keluar di kanan (rasio lebar 4:1)
    c_head1, c_head2 = st.columns([4, 1])
    with c_head1:
        st.subheader(f"👋 Selamat Datang, {user['user_id']}")
    with c_head2:
        if st.button("Keluar", type="secondary"):
            st.session_state.user = None            # Hapus status login
            st.session_state.active_contact = None  # Reset kontak aktif
            st.rerun()                              # Muat ulang -> kembali ke halaman login

    st.caption("Encoding: ASCII 7 bit. ANSI, UTF-8, dan UTF-16 tidak didukung sebagai encoding aplikasi.")

    # Panel mandiri untuk ngetes karakter apa saja yang didukung (tanpa kirim pesan)
    with st.expander("🧪 Panel Uji Karakter (Validator ASCII)"):
        test_input = st.text_input("Ketik kalimat/teks bebas untuk verifikasi:", "IBNU")  # Default teks "IBNU"
        if test_input:
            res_list = []  # Wadah baris hasil (dalam bentuk <li>)
            for ch in test_input:
                code = ord(ch)
                if 32 <= code <= 126:
                    # Karakter valid -> tampil dengan tanda centang
                    res_list.append(f"<li><b>'{html.escape(ch)}'</b> (ASCII {code}): Didukung ✅</li>")
                else:
                    # Karakter tidak valid -> tampil merah dengan tanda silang
                    res_list.append(f"<li style='color:red;'><b>'{html.escape(ch)}'</b> (Kode {code} / U+{code:04X}): <b>Tidak didukung (kode > 127 / non-printable)</b> ❌</li>")
            st.markdown(f"<ul>{''.join(res_list)}</ul>", unsafe_allow_html=True)  # Gabung semua jadi satu daftar

    st.divider()  # Garis pemisah

    # Layout utama: kolom kiri (kontak) lebih sempit dari kolom kanan (obrolan), rasio 1:2
    col_left, col_right = st.columns([1, 2])

    # ---------- KOLOM KIRI: DAFTAR KONTAK ----------
    with col_left:
        st.subheader("📋 Daftar Kontak")

        # Form tambah kontak. clear_on_submit=True -> input dikosongkan setelah submit
        with st.form("add_contact_form", clear_on_submit=True):
            new_c_id = st.text_input("Cari ID Pengguna")
            submitted = st.form_submit_button("Tambah Kontak")
            if submitted and new_c_id:  # Hanya proses kalau tombol ditekan dan input terisi
                ok, msg = add_contact(user["user_id"], new_c_id)
                if ok:
                    st.success(msg)
                    st.rerun()   # Refresh supaya kontak baru langsung muncul di daftar
                else:
                    st.error(msg)

        # Ambil dan tampilkan daftar kontak milik user
        contacts = fetch_contacts(user["user_id"])
        if not contacts:
            st.info("Belum ada kontak. Tambahkan kontak berdasarkan ID.")
        else:
            for c_id in contacts:
                # Kontak yang sedang aktif tombolnya berwarna primary (menyala)
                btn_type = "primary" if st.session_state.active_contact == c_id else "secondary"
                # key unik per kontak, kalau nggak Streamlit error karena tombol kembar
                if st.button(f"👤 {c_id}", key=f"btn_{c_id}", use_container_width=True, type=btn_type):
                    st.session_state.active_contact = c_id  # Set kontak aktif
                    st.rerun()                              # Refresh untuk membuka obrolan

    # ---------- KOLOM KANAN: OBROLAN ----------
    with col_right:
        active_contact = st.session_state.active_contact
        if not active_contact:
            # Belum ada kontak yang dipilih
            st.info("👈 Pilih kontak di sebelah kiri untuk memulai obrolan.")
        else:
            st.subheader(f"💬 Percakapan dengan: {active_contact}")

            # Kotak chat realtime (polling tiap 2 detik, lihat fungsi di bagian 4)
            render_realtime_chat_box(user["user_id"], active_contact)

            # Form kirim pesan baru
            with st.form("send_msg_form", clear_on_submit=True):
                txt_input = st.text_input("Ketik pesan ASCII (Kode 32-126):", key="chat_input")
                btn_send = st.form_submit_button("Kirim Pesan", type="primary")

                if btn_send and txt_input:  # Proses hanya kalau tombol ditekan dan pesan tidak kosong
                    ok, err = send_message(user["user_id"], active_contact, txt_input)
                    if not ok:
                        st.error(err)  # Tampilkan error (misal ada emoji)
                    else:
                        st.rerun()     # Refresh supaya pesan baru langsung tampil

# =============================================================================
# RUNNER UTAMA
# =============================================================================
# Titik masuk aplikasi: belum login -> tampil halaman login/daftar, sudah login -> halaman chat
if st.session_state.user is None:
    render_auth_view()
else:
    render_main_view()