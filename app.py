# =============================================================================
# IMPORT LIBRARY
# =============================================================================
import streamlit as st                          # Framework utama untuk bikin web app dengan Python
import streamlit.components.v1 as components    # Untuk menampilkan HTML/SVG mentah (gambar sinyal)
from supabase import create_client, Client      # Library untuk konek ke database Supabase
import bcrypt                                   # Library hash (sekarang hanya dipakai untuk kunci buka pesan)
import html                                     # html.escape() supaya teks user tidak bisa menyisipkan kode HTML

# =============================================================================
# 0. KONFIGURASI HALAMAN & DATABASE
# =============================================================================
# Mengatur judul tab, ikon tab, dan layout lebar. Harus jadi perintah Streamlit pertama.
st.set_page_config(page_title="ASCII Chat & Signal Lab", page_icon="💬", layout="wide")

# Konstanta frame (sama seperti di versi JS)
FRAME_LEN = 10          # 1 frame = 1 start + 7 data + 1 parity + 1 end = 10 bit
MAX_FRAMES_MINI = 100   # maksimal frame yang digambar per pesan (biar gambar tidak terlalu lebar)

@st.cache_resource  # Cache koneksi supaya tidak bikin koneksi baru setiap halaman di-rerun
def get_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]   # Ambil URL project dari secrets.toml
    key = st.secrets["SUPABASE_KEY"]   # Ambil API key dari secrets.toml
    return create_client(url, key)     # Buat dan kembalikan objek koneksi

supabase = get_supabase()  # Objek koneksi, dipakai semua fungsi di bawah untuk query ke tabel

# Session state = "memori" Streamlit yang bertahan walau halaman di-rerun
if "user" not in st.session_state:
    st.session_state.user = None            # None = belum login, berisi data user kalau sudah login
if "active_contact" not in st.session_state:
    st.session_state.active_contact = None  # ID kontak yang sedang dibuka obrolannya
if "opened_msgs" not in st.session_state:
    st.session_state.opened_msgs = set()    # Kumpulan ID pesan yang sudah dibuka dengan kunci

# =============================================================================
# 1. AUTENTIKASI, PASSWORD & KUNCI BUKA PESAN
# =============================================================================
def hash_text(text: str) -> str:
    """Hash teks dengan bcrypt (sekarang hanya dipakai untuk kunci buka pesan)."""
    # encode -> ubah string jadi bytes (bcrypt butuh bytes)
    # gensalt() -> bikin salt acak, jadi teks yang sama bisa menghasilkan hash berbeda
    # decode -> ubah hasil bytes jadi string supaya bisa disimpan di database
    return bcrypt.hashpw(text.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def check_hash(text: str, hashed: str) -> bool:
    """Cocokkan teks biasa dengan hash yang tersimpan."""
    # checkpw membandingkan teks yang diketik dengan hash dari database
    return bcrypt.checkpw(text.encode("utf-8"), hashed.encode("utf-8"))

def register_user(user_id: str, email: str, password: str, access_key: str) -> bool:
    """Simpan akun baru. Password disimpan apa adanya (tanpa hash), kunci tetap di-hash."""
    try:
        # Insert 1 baris baru ke tabel 'users'
        supabase.table("users").insert({
            "user_id": user_id,
            "email": email,
            "password_hash": password,                # password disimpan polos, tidak di-hash
            "access_key_hash": hash_text(access_key)  # kunci tetap di-hash
        }).execute()
        return True   # Berhasil daftar
    except Exception as e:
        # Biasanya gagal karena user_id/email sudah dipakai (kolom unik)
        st.error(f"Gagal mendaftar: {e}")
        return False

def login_user(user_id: str, email: str, password: str):
    """Cek user_id + email, lalu bandingkan password langsung (tanpa bcrypt)."""
    # Cari user yang user_id DAN email-nya cocok
    res = supabase.table("users").select("*").eq("user_id", user_id).eq("email", email).execute()
    if res.data:                                    # Kalau user ditemukan
        user_data = res.data[0]                     # Ambil baris pertama
        if password == user_data["password_hash"]:  # Bandingkan password langsung
            return user_data                        # Login sukses, kembalikan data user
    return None                                     # User tidak ketemu atau password salah

def verify_key(owner_id: str, key: str):
    """
    Verifikasi kunci milik pemilik pesan (pengirim), sama seperti verify_key di JS.
    Return (berhasil, pesan_error).
    """
    # Ambil hash kunci milik pengirim dari tabel users
    res = supabase.table("users").select("access_key_hash").eq("user_id", owner_id).execute()
    # Kalau user tidak ada atau belum punya kunci (akun lama), tolak
    if not res.data or not res.data[0].get("access_key_hash"):
        return False, "Pemilik pesan ini belum punya kunci."
    # Cocokkan kunci yang diketik dengan hash tersimpan
    if check_hash(key, res.data[0]["access_key_hash"]):
        return True, ""
    return False, "Kunci salah, pesan tidak bisa dibuka."

def render_auth_view():
    """Menampilkan tab 'Masuk' dan 'Daftar' sebelum pengguna mengakses chat."""
    st.title("🔐 Akses Sistem Komunikasi Data")
    tab_masuk, tab_daftar = st.tabs(["Masuk", "Daftar"])  # Bikin 2 tab

    # --- TAB MASUK ---
    with tab_masuk:
        st.subheader("Login Pengguna")
        # key= wajib unik supaya Streamlit bisa membedakan input di tab Masuk vs Daftar
        u_id = st.text_input("ID Pengguna", key="l_id")
        u_email = st.text_input("Email", key="l_email")
        u_pass = st.text_input("Password", type="password", key="l_pass")  # type=password -> teks disamarkan

        if st.button("Masuk", type="primary"):
            if not (u_id and u_email and u_pass):   # Validasi: semua kolom harus terisi
                st.warning("Semua bidang input wajib diisi.")
            else:
                user = login_user(u_id, u_email, u_pass)
                if user:
                    st.session_state.user = user    # Simpan data user -> tandanya sudah login
                    st.rerun()                      # Muat ulang halaman, nanti masuk ke tampilan utama
                else:
                    st.error("Kombinasi ID Pengguna, Email, dan Password tidak cocok.")

    # --- TAB DAFTAR ---
    with tab_daftar:
        st.subheader("Pendaftaran Akun Baru")
        reg_id = st.text_input("ID Pengguna (Unik)", key="r_id")
        reg_email = st.text_input("Email (Unik)", key="r_email")
        reg_key = st.text_input("Kunci Buka Pesan (min. 4 karakter)", type="password", key="r_key")  # Kunci untuk buka pesan
        reg_pass = st.text_input("Password (min. 6 karakter)", type="password", key="r_pass")
        reg_pass_confirm = st.text_input("Konfirmasi Password", type="password", key="r_pass_confirm")

        if st.button("Daftar"):
            if not (reg_id and reg_email and reg_key and reg_pass and reg_pass_confirm):  # Semua wajib diisi
                st.warning("Semua bidang input wajib diisi.")
            elif len(reg_key) < 4:                  # Cek panjang minimal kunci
                st.warning("Kunci buka pesan minimal 4 karakter.")
            elif len(reg_pass) < 6:                 # Cek panjang minimal password
                st.warning("Password minimal 6 karakter.")
            elif reg_pass != reg_pass_confirm:      # Cek password dan konfirmasinya sama
                st.error("Konfirmasi password tidak cocok.")
            else:
                if register_user(reg_id, reg_email, reg_pass, reg_key):  # Simpan ke database
                    st.success("Pendaftaran berhasil! Silakan berpindah ke tab 'Masuk'.")

# =============================================================================
# 2. VALIDASI ASCII & FRAME
# =============================================================================
def validate_ascii(text: str):
    """Hanya izinkan ASCII tercetak (32-126)."""
    for ch in text:                 # Periksa karakter satu per satu
        code = ord(ch)              # ord() = ubah karakter jadi nomor ASCII/Unicode-nya
        if code < 32 or code > 126: # Di luar rentang karakter tercetak (emoji, huruf spesial, dll)
            return False, f"Karakter '{ch}' (U+{code:04X}) tidak didukung. Hanya ASCII 7 bit (kode 32-126)."
    return True, ""                 # Semua karakter aman

def get_char_analysis(ch: str):
    """Ubah 1 karakter jadi frame 10 bit: Start(0) + Data(7) + Parity Even + End(1)."""
    code = ord(ch)                                       # Kode desimal, contoh 'A' -> 65
    bin_7bit = f"{code:07b}"                             # Biner 7 digit (MSB dulu) -> '1000001'
    parity_even = 1 if (bin_7bit.count('1') % 2 != 0) else 0  # Parity 1 kalau jumlah '1' ganjil, supaya total jadi genap
    return {
        "char": ch,                                      # Karakter asli
        "ascii_code": code,                              # Kode desimal
        "bin_7bit": bin_7bit,                            # Biner 7 bit
        "parity_even": parity_even,                      # Bit parity
        "frame_bits": f"0{bin_7bit}{parity_even}1"       # Frame lengkap: Start(0) + Data + Parity + End(1)
    }

# =============================================================================
# 3. GAMBAR SINYAL NRZ-I (VERSI MINI UNTUK BUBBLE CHAT)
# =============================================================================
def generate_nrzi_mini_svg(text: str) -> str:
    """
    Gambar sinyal NRZ-I gaya osiloskop (latar gelap, garis hijau).
    Bit 1 = level berubah, bit 0 = level tetap. Level awal: HIGH (seperti di JS).
    Tanpa label S/DATA/P/E dan tanpa warna blok.
    """
    # Ubah tiap karakter jadi frame, batasi maksimal MAX_FRAMES_MINI frame
    frames = [get_char_analysis(ch) for ch in text][:MAX_FRAMES_MINI]
    bits = "".join(f["frame_bits"] for f in frames)   # Gabungkan semua bit jadi satu string panjang

    # Ukuran & posisi gambar (piksel)
    bit_w, left, right, h = 14, 10, 10, 100    # Lebar 1 bit, margin kiri, margin kanan, tinggi gambar
    y_high, y_low = 44, 86                     # Posisi y level tinggi dan rendah
    width = left + len(bits) * bit_w + right   # Lebar total gambar menyesuaikan jumlah bit
    x_end = left + len(bits) * bit_w           # Posisi x akhir gelombang

    # Tag pembuka SVG: latar gelap seperti layar osiloskop
    p = [f'<svg width="{width}" height="{h}" xmlns="http://www.w3.org/2000/svg" style="background:#0e131a;border-radius:10px;display:block;">']

    # Garis pemisah frame (tegas) dan pemisah bagian dalam frame (putus-putus)
    for fi in range(len(frames)):
        fx = left + fi * FRAME_LEN * bit_w     # Posisi x awal frame ke-fi
        for off in (1, 8, 9):                  # Batas bagian: setelah Start (1), setelah Data (8), setelah Parity (9)
            x = fx + off * bit_w
            p.append(f'<line x1="{x}" y1="0" x2="{x}" y2="{h}" stroke="rgba(255,255,255,0.14)" stroke-width="1" stroke-dasharray="2,3"/>')
        # Garis tegas di awal frame
        p.append(f'<line x1="{fx}" y1="0" x2="{fx}" y2="{h}" stroke="rgba(255,255,255,0.30)" stroke-width="1"/>')
    # Garis tegas penutup di akhir frame terakhir
    p.append(f'<line x1="{x_end}" y1="0" x2="{x_end}" y2="{h}" stroke="rgba(255,255,255,0.30)" stroke-width="1"/>')

    # Garis bantu horizontal untuk level tinggi & rendah
    for y in (y_high, y_low):
        p.append(f'<line x1="{left}" y1="{y}" x2="{x_end}" y2="{y}" stroke="rgba(255,255,255,0.12)" stroke-width="1" stroke-dasharray="4,4"/>')

    # ===== INTI LOGIKA NRZ-I: garis gelombang =====
    level = 1                                  # Level awal: tinggi (HIGH)
    cur_y = y_high                             # Posisi y saat ini
    x = left                                   # Posisi x saat ini
    path = f"M {left - 6} {y_high} L {left} {y_high}"   # Mulai dari sedikit di kiri, garis datar pendek
    for b in bits:
        if b == "1":
            level = 1 - level                  # Bit 1 -> balik level (1 jadi 0, 0 jadi 1)
        # Bit 0 -> level tetap, tidak ada perubahan
        ny = y_high if level == 1 else y_low   # Ubah level jadi posisi y
        if ny != cur_y:
            path += f" L {x} {ny}"             # Kalau level berubah, tarik garis vertikal (transisi)
            cur_y = ny
        x += bit_w
        path += f" L {x} {cur_y}"              # Garis datar sepanjang 1 bit
    # Gambar garis gelombang berwarna hijau
    p.append(f'<path d="{path}" stroke="#6bb08f" stroke-width="2.5" fill="none" stroke-linejoin="round"/>')
    p.append('</svg>')                         # Tutup tag SVG
    return "".join(p)                          # Gabungkan semua potongan jadi satu string SVG

# =============================================================================
# 4. QUERY DATABASE & CHAT REALTIME
# =============================================================================
def fetch_contacts(user_id: str):
    """Mengambil daftar ID kontak milik pengguna saat ini."""
    res = supabase.table("contacts").select("contact_id").eq("user_id", user_id).execute()
    return [item["contact_id"] for item in res.data]   # Ubah jadi list ID saja

def add_contact(user_id: str, contact_id: str):
    """Menambahkan kontak dua arah (timbal balik) di database."""
    if user_id == contact_id:                          # Cegah menambah diri sendiri
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
    except Exception:
        # Biasanya error karena pasangan kontak sudah ada (duplikat)
        return False, "Kontak sudah ada dalam daftar."

def fetch_messages(user_id: str, contact_id: str):
    """Mengambil riwayat percakapan antara dua pengguna."""
    # Ambil pesan yang (A kirim ke B) ATAU (B kirim ke A), jadi dua arah
    res = supabase.table("messages").select("*").or_(
        f"and(sender_id.eq.{user_id},receiver_id.eq.{contact_id}),and(sender_id.eq.{contact_id},receiver_id.eq.{user_id})"
    ).order("created_at", desc=False).execute()        # Urut dari yang terlama ke terbaru
    return res.data

def send_message(sender_id: str, receiver_id: str, text: str):
    """Validasi ASCII lalu simpan pesan baru ke database."""
    valid, err_msg = validate_ascii(text)              # Cek dulu semua karakter ASCII 32-126
    if not valid:
        return False, err_msg                          # Tolak kalau ada karakter terlarang
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

@st.fragment(run_every=2)  # Fungsi ini dijalankan ulang otomatis tiap 2 detik (tanpa rerun seluruh halaman)
def render_realtime_chat_box(current_user_id: str, target_user_id: str):
    """Polling database tiap 2 detik, lalu tampilkan pesan dalam bentuk sinyal terkunci."""
    messages = fetch_messages(current_user_id, target_user_id)   # Ambil pesan terbaru

    chat_container = st.container(height=480)   # Kotak chat tinggi tetap + bisa di-scroll
    with chat_container:
        if not messages:
            st.info("Belum ada pesan. Mulai percakapan!")

        for msg in messages:
            is_me = (msg["sender_id"] == current_user_id)     # Pesan dari kita atau lawan?
            align = "flex-end" if is_me else "flex-start"     # Pesan kita di kanan, lawan di kiri
            n_frames = len(msg["text"])                       # 1 karakter = 1 frame
            # Info tambahan kalau pesan terlalu panjang dan hanya sebagian yang digambar
            extra = f" · {MAX_FRAMES_MINI} frame pertama digambar" if n_frames > MAX_FRAMES_MINI else ""

            # ID unik pesan (pakai kolom id kalau ada, kalau tidak pakai gabungan data)
            msg_id = str(msg.get("id") or f"{msg['sender_id']}_{msg.get('created_at')}")

            # Header bubble terkunci: jumlah frame dan bit
            st.markdown(
                f'<div style="display:flex; justify-content:{align};">'
                f'<div style="font-size:13px; font-weight:600; color:#6b7a8c;">'
                f'🔒 Pesan ter-encode · {n_frames} frame · {n_frames * FRAME_LEN} bit{extra}</div></div>',
                unsafe_allow_html=True
            )

            # Gambar sinyal NRZ-I (isi pesan asli TIDAK ditampilkan)
            svg = generate_nrzi_mini_svg(msg["text"])
            components.html(
                f'<body style="margin:0"><div style="overflow-x:auto;">{svg}</div></body>',
                height=118, scrolling=False
            )

            # --- Bagian buka pesan pakai kunci ---
            if msg_id in st.session_state.opened_msgs:
                # Sudah dibuka: tampilkan teks aslinya (di-escape supaya aman dari injeksi HTML)
                st.markdown(
                    f'<div style="display:flex; justify-content:{align}; margin:4px 0 6px;">'
                    f'<div style="background:#e6f4fa; border:1px solid #b6dcec; padding:10px 14px; '
                    f'border-radius:12px; max-width:70%; color:#023e8a; font-size:16px; word-wrap:break-word;">'
                    f'{html.escape(msg["text"])}</div></div>',
                    unsafe_allow_html=True
                )
                # Tombol untuk mengunci ulang pesan
                if st.button("🔒 Kunci lagi", key=f"close_{msg_id}"):
                    st.session_state.opened_msgs.discard(msg_id)   # Hapus dari daftar pesan terbuka
                    st.rerun()
            else:
                # Belum dibuka: tampilkan form input kunci di dalam expander
                who = "kamu" if is_me else msg["sender_id"]
                with st.expander(f"🔑 Masukkan kunci {who} untuk melihat pesan"):
                    with st.form(key=f"form_{msg_id}", clear_on_submit=True):   # Form unik per pesan
                        key_in = st.text_input("Kunci", type="password", key=f"key_{msg_id}")
                        if st.form_submit_button("Buka Pesan"):
                            ok, err = verify_key(msg["sender_id"], key_in)      # Kunci yang dipakai = kunci PENGIRIM
                            if ok:
                                st.session_state.opened_msgs.add(msg_id)        # Tandai pesan ini sudah terbuka
                                st.rerun()
                            else:
                                st.error("❌ " + err)

            st.divider()   # Garis pemisah antar pesan

# =============================================================================
# 5. HALAMAN UTAMA
# =============================================================================
def render_main_view():
    """Tampilan utama setelah pengguna berhasil login."""
    user = st.session_state.user   # Ambil data user yang sedang login

    # Bilah atas: sapaan di kiri, tombol Keluar di kanan (rasio lebar 4:1)
    c_head1, c_head2 = st.columns([4, 1])
    with c_head1:
        st.subheader(f"👋 Selamat Datang, {user['user_id']}")
    with c_head2:
        if st.button("Keluar", type="secondary"):
            st.session_state.user = None             # Hapus status login
            st.session_state.active_contact = None   # Reset kontak aktif
            st.session_state.opened_msgs = set()     # Reset pesan yang terbuka
            st.rerun()                               # Muat ulang -> kembali ke halaman login

    st.caption("Encoding: ASCII 7 bit. Pesan ditampilkan sebagai sinyal NRZ-I dan hanya bisa dibuka dengan kunci pengirim.")

    # Panel mandiri untuk mengetes karakter apa saja yang didukung (tanpa kirim pesan)
    with st.expander("🧪 Panel Uji Karakter (Validator ASCII)"):
        test_input = st.text_input("Ketik kalimat/teks bebas untuk verifikasi:", "IBNU")   # Default teks "IBNU"
        if test_input:
            res_list = []   # Wadah baris hasil (dalam bentuk <li>)
            for ch in test_input:
                code = ord(ch)
                if 32 <= code <= 126:
                    # Karakter valid -> tampil dengan tanda centang
                    res_list.append(f"<li><b>'{html.escape(ch)}'</b> (ASCII {code}): Didukung ✅</li>")
                else:
                    # Karakter tidak valid -> tampil merah dengan tanda silang
                    res_list.append(f"<li style='color:red;'><b>'{html.escape(ch)}'</b> (Kode {code} / U+{code:04X}): <b>Tidak didukung</b> ❌</li>")
            st.markdown(f"<ul>{''.join(res_list)}</ul>", unsafe_allow_html=True)   # Gabung jadi satu daftar

    st.divider()   # Garis pemisah

    # Layout utama: kolom kiri (kontak) lebih sempit dari kolom kanan (obrolan), rasio 1:2
    col_left, col_right = st.columns([1, 2])

    # ---------- KOLOM KIRI: DAFTAR KONTAK ----------
    with col_left:
        st.subheader("📋 Daftar Kontak")

        # Form tambah kontak. clear_on_submit=True -> input dikosongkan setelah submit
        with st.form("add_contact_form", clear_on_submit=True):
            new_c_id = st.text_input("Cari ID Pengguna")
            submitted = st.form_submit_button("Tambah Kontak")
            if submitted and new_c_id:   # Hanya proses kalau tombol ditekan dan input terisi
                ok, msg = add_contact(user["user_id"], new_c_id)
                if ok:
                    st.success(msg)
                    st.rerun()           # Refresh supaya kontak baru langsung muncul
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
                # key unik per kontak, kalau tidak Streamlit error karena tombol kembar
                if st.button(f"👤 {c_id}", key=f"btn_{c_id}", use_container_width=True, type=btn_type):
                    st.session_state.active_contact = c_id   # Set kontak aktif
                    st.rerun()                               # Refresh untuk membuka obrolan

    # ---------- KOLOM KANAN: OBROLAN ----------
    with col_right:
        active_contact = st.session_state.active_contact
        if not active_contact:
            # Belum ada kontak yang dipilih
            st.info("👈 Pilih kontak di sebelah kiri untuk memulai obrolan.")
        else:
            st.subheader(f"💬 Percakapan dengan: {active_contact}")
            render_realtime_chat_box(user["user_id"], active_contact)   # Kotak chat realtime (polling 2 detik)

            # Form kirim pesan baru
            with st.form("send_msg_form", clear_on_submit=True):
                txt_input = st.text_input("Ketik pesan ASCII (Kode 32-126):", key="chat_input")
                btn_send = st.form_submit_button("Kirim Pesan", type="primary")
                if btn_send and txt_input:   # Proses hanya kalau tombol ditekan dan pesan tidak kosong
                    ok, err = send_message(user["user_id"], active_contact, txt_input)
                    if not ok:
                        st.error(err)        # Tampilkan error (misal ada emoji)
                    else:
                        st.rerun()           # Refresh supaya pesan baru langsung tampil

# =============================================================================
# RUNNER UTAMA
# =============================================================================
# Titik masuk aplikasi: belum login -> halaman login/daftar, sudah login -> halaman chat
if st.session_state.user is None:
    render_auth_view()
else:
    render_main_view()