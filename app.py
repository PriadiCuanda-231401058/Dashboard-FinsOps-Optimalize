import math
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

# ==============================================================================
# KONFIGURASI HALAMAN & STYLING
# ==============================================================================
st.set_page_config(
    page_title="FinOps & Green Computing Dashboard — Portal Akademik KRS",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
        .block-container {padding-top: 1.5rem; padding-bottom: 2rem;}
        div[data-testid="stMetric"] {
            background-color: #f8fafc;
            border: 1px solid #e2e8f0;
            padding: 14px 16px;
            border-radius: 10px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.04);
        }
        div[data-testid="stMetric"] label {
            font-weight: 600;
            color: #475569;
        }
        .insight-box {
            background-color: #f0fdf4;
            border-left: 4px solid #16a34a;
            padding: 12px 16px;
            border-radius: 6px;
            margin-bottom: 12px;
            color: #14532d;
        }
        .warning-box {
            background-color: #fffbeb;
            border-left: 4px solid #d97706;
            padding: 12px 16px;
            border-radius: 6px;
            margin-bottom: 12px;
            color: #78350f;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# ==============================================================================
# FUNGSI HELPER FORMAT INDONESIA
# ==============================================================================
def fmt_id(val: float, decimals: int = 0) -> str:
    """Format angka ke standar Indonesia (titik ribuan, koma desimal)."""
    formatted = f"{val:,.{decimals}f}"
    return formatted.replace(",", "_").replace(".", ",").replace("_", ".")


# ==============================================================================
# ENGINE PERHITUNGAN FINOPS & GREEN COMPUTING (LANGKAH 1 - 14)
# ==============================================================================
def daya_server(utilisasi: float, p_idle: float = 140.0, p_full: float = 350.0) -> float:
    return p_idle + (p_full - p_idle) * utilisasi


def hitung_finops(params: dict) -> dict:
    # Unpack parameter
    mahasiswa = params["mahasiswa"]
    hari_krs = params["hari_krs"]
    hari_normal = 365 - hari_krs
    hari_buffer = min(params["hari_buffer"], hari_normal)

    jam_total = 365 * 24
    jam_krs = hari_krs * 24
    jam_normal = hari_normal * 24
    jam_buffer = hari_buffer * 24

    n_app_init = 4
    n_db_init = 2
    n_srv_init = n_app_init + n_db_init

    u_app_norm = params["u_app_norm"] / 100.0
    u_app_krs = params["u_app_krs"] / 100.0
    u_db_norm = params["u_db_norm"] / 100.0
    u_db_krs = params["u_db_krs"] / 100.0

    p_idle = params["p_idle"]
    p_full = params["p_full"]
    total_tb = params["total_tb"]
    cold_pct = params["cold_pct"] / 100.0
    w_fast_tb = 10.0
    w_cold_tb = 1.0
    p_net = 150.0

    pue_init = params["pue_init"]
    overhead_fixed_ratio = 0.40
    overhead_var_share = 0.60
    cooling_share_of_overhead = 0.80

    virt_overhead = params["virt_overhead"] / 100.0
    target_util = params["target_util"] / 100.0
    cooling_save = params["cooling_save"] / 100.0

    tarif = params["tarif"]
    faktor_emisi = params["faktor_emisi"]

    # Biaya perangkat tahunan (umur 5 tahun, pemeliharaan 8%/tahun)
    harga_srv = params["harga_srv"]  # juta
    umur = 5.0
    maint_rate = 0.08
    depr_srv_unit = harga_srv / umur
    maint_srv_unit = harga_srv * maint_rate
    cost_srv_unit = depr_srv_unit + maint_srv_unit  # Rp 33,6 jt

    cost_fast_tb = (12.0 / umur) + (12.0 * maint_rate)  # Rp 3,36 jt
    cost_cold_tb = (2.0 / umur) + (2.0 * maint_rate)    # Rp 0,56 jt

    # ------------------------------------------------------------------
    # BAGIAN 6.1: BASELINE (LANGKAH 1 - 7)
    # ------------------------------------------------------------------
    p_app_n = daya_server(u_app_norm, p_idle, p_full)
    p_app_k = daya_server(u_app_krs, p_idle, p_full)
    p_db_n = daya_server(u_db_norm, p_idle, p_full)
    p_db_k = daya_server(u_db_krs, p_idle, p_full)

    p_srv_norm_base = n_app_init * p_app_n + n_db_init * p_db_n
    p_srv_krs_base = n_app_init * p_app_k + n_db_init * p_db_k

    e_srv_norm_base = (p_srv_norm_base * jam_normal) / 1000.0
    e_srv_krs_base = (p_srv_krs_base * jam_krs) / 1000.0
    e_srv_base = e_srv_norm_base + e_srv_krs_base

    e_stor_base = (total_tb * w_fast_tb * jam_total) / 1000.0
    e_net_base = (p_net * jam_total) / 1000.0
    e_it_base = e_srv_base + e_stor_base + e_net_base

    e_fac_base = e_it_base * pue_init
    overhead_base = e_fac_base - e_it_base
    overhead_fixed = overhead_fixed_ratio * overhead_base
    overhead_var_base = overhead_var_share * overhead_base
    overhead_var_per_it = overhead_var_base / e_it_base  # 0.48 pada PUE 1.8

    cost_elec_base = (e_fac_base * tarif) / 1e6
    cost_srv_base = n_srv_init * cost_srv_unit
    cost_stor_base = total_tb * cost_fast_tb
    cost_total_base = cost_elec_base + cost_srv_base + cost_stor_base
    co2_base = (e_fac_base * faktor_emisi) / 1000.0  # ton

    util_app_weighted = (u_app_norm * hari_normal + u_app_krs * hari_krs) / 365.0

    # ------------------------------------------------------------------
    # HITUNG BEBAN SETARA SERVER & VIRTUALISASI (LANGKAH 8)
    # ------------------------------------------------------------------
    load_norm = n_app_init * u_app_norm + n_db_init * u_db_norm      # 0.88
    load_krs = n_app_init * u_app_krs + n_db_init * u_db_krs         # 3.20
    load_norm_virt = load_norm * (1.0 + virt_overhead)               # 0.968
    load_krs_virt = load_krs * (1.0 + virt_overhead)                 # 3.52

    # Pembulatan jumlah server puncak sesuai dokumen (3.52 / 0.70 = 5.03 -> 5)
    n_srv_opt1 = max(1, int(round(load_krs_virt / target_util)))
    if load_krs_virt / n_srv_opt1 > 1.0:
        n_srv_opt1 = math.ceil(load_krs_virt)
    n_srv_opt1 = min(n_srv_init, n_srv_opt1)

    u_norm_opt1 = load_norm_virt / n_srv_opt1
    u_krs_opt1 = load_krs_virt / n_srv_opt1
    p_norm_opt1 = n_srv_opt1 * daya_server(u_norm_opt1, p_idle, p_full)
    p_krs_opt1 = n_srv_opt1 * daya_server(u_krs_opt1, p_idle, p_full)
    e_srv_opt1 = (p_norm_opt1 * jam_normal + p_krs_opt1 * jam_krs) / 1000.0
    e_it_opt1 = e_srv_opt1 + e_stor_base + e_net_base

    # Langkah 9: Perapihan pendingin
    overhead_opt1_pre = overhead_fixed + overhead_var_per_it * e_it_opt1
    cooling_mult = 1.0 - (cooling_share_of_overhead * cooling_save)  # 0.84 saat 20%
    overhead_opt1 = overhead_opt1_pre * cooling_mult
    e_fac_opt1 = e_it_opt1 + overhead_opt1
    pue_opt1 = e_fac_opt1 / e_it_opt1

    # Pemisahan hemat energi rightsizing vs pendingin pada Optimasi 1
    e_fac_rightsizing_only = e_it_opt1 + overhead_opt1_pre
    save_e_rightsizing = e_fac_base - e_fac_rightsizing_only
    save_e_cooling = overhead_opt1_pre - overhead_opt1

    save_e_opt1 = e_fac_base - e_fac_opt1
    save_elec_opt1 = (save_e_opt1 * tarif) / 1e6
    save_srv_opt1 = (n_srv_init - n_srv_opt1) * cost_srv_unit
    save_cost_opt1 = save_elec_opt1 + save_srv_opt1
    save_co2_opt1 = (save_e_opt1 * faktor_emisi) / 1000.0

    # ------------------------------------------------------------------
    # BAGIAN 6.3: OPTIMASI 2 — AUTOSCALING TERJADWAL (LANGKAH 10)
    # ------------------------------------------------------------------
    n_srv_base_auto = max(1, min(n_srv_opt1, math.ceil(load_norm_virt / target_util)))
    u_base_auto = load_norm_virt / n_srv_base_auto
    p_base_auto = n_srv_base_auto * daya_server(u_base_auto, p_idle, p_full)
    jam_two_srv = jam_normal - jam_buffer

    e_srv_opt2 = (
        (p_base_auto * jam_two_srv)
        + (p_norm_opt1 * jam_buffer)
        + (p_krs_opt1 * jam_krs)
    ) / 1000.0
    e_it_opt2 = e_srv_opt2 + e_stor_base + e_net_base
    overhead_opt2 = cooling_mult * (overhead_fixed + overhead_var_per_it * e_it_opt2)
    e_fac_opt2 = e_it_opt2 + overhead_opt2
    pue_opt2 = e_fac_opt2 / e_it_opt2

    save_e_opt2 = e_fac_opt1 - e_fac_opt2
    save_cost_opt2 = (save_e_opt2 * tarif) / 1e6
    save_co2_opt2 = (save_e_opt2 * faktor_emisi) / 1000.0

    # ------------------------------------------------------------------
    # BAGIAN 6.4: OPTIMASI 3 — COLD STORAGE & TAGGING (LANGKAH 11)
    # ------------------------------------------------------------------
    tb_cold = total_tb * cold_pct
    tb_fast = total_tb - tb_cold
    p_stor_opt3 = tb_fast * w_fast_tb + tb_cold * w_cold_tb
    e_stor_opt3 = (p_stor_opt3 * jam_total) / 1000.0

    e_it_opt3 = e_srv_opt2 + e_stor_opt3 + e_net_base
    overhead_opt3 = cooling_mult * (overhead_fixed + overhead_var_per_it * e_it_opt3)
    e_fac_opt3 = e_it_opt3 + overhead_opt3
    pue_opt3 = e_fac_opt3 / e_it_opt3

    cost_stor_opt3 = tb_fast * cost_fast_tb + tb_cold * cost_cold_tb
    save_stor_cost = cost_stor_base - cost_stor_opt3

    save_e_opt3 = e_fac_opt2 - e_fac_opt3
    save_elec_opt3 = (save_e_opt3 * tarif) / 1e6
    save_cost_opt3 = save_stor_cost + save_elec_opt3
    save_co2_opt3 = (save_e_opt3 * faktor_emisi) / 1000.0

    # ------------------------------------------------------------------
    # SKENARIO AKTIF (SESUAI TOGGLE CHECKBOX DI SIDEBAR)
    # ------------------------------------------------------------------
    use_opt1 = params["use_opt1"]
    use_opt2 = params["use_opt2"]
    use_opt3 = params["use_opt3"]

    active_n_srv_peak = n_srv_opt1 if use_opt1 else n_srv_init
    active_cooling_mult = cooling_mult if use_opt1 else 1.0
    active_e_stor = e_stor_opt3 if use_opt3 else e_stor_base
    active_cost_stor = cost_stor_opt3 if use_opt3 else cost_stor_base

    if use_opt2:
        if use_opt1:
            active_e_srv = e_srv_opt2
            active_n_srv_normal = n_srv_base_auto
        else:
            # Autoscaling tanpa rightsizing (virtualisasi pada 6 server puncak)
            u_n_6 = load_norm_virt / n_srv_init
            u_k_6 = load_krs_virt / n_srv_init
            p_n_6 = n_srv_init * daya_server(u_n_6, p_idle, p_full)
            p_k_6 = n_srv_init * daya_server(u_k_6, p_idle, p_full)
            n_base_6 = max(1, min(n_srv_init, math.ceil(load_norm_virt / target_util)))
            p_b_6 = n_base_6 * daya_server(load_norm_virt / n_base_6, p_idle, p_full)
            active_e_srv = (p_b_6 * jam_two_srv + p_n_6 * jam_buffer + p_k_6 * jam_krs) / 1000.0
            active_n_srv_normal = n_base_6
    else:
        if use_opt1:
            active_e_srv = e_srv_opt1
            active_n_srv_normal = n_srv_opt1
        else:
            active_e_srv = e_srv_base
            active_n_srv_normal = n_srv_init

    active_e_it = active_e_srv + active_e_stor + e_net_base
    active_overhead = active_cooling_mult * (overhead_fixed + overhead_var_per_it * active_e_it)
    active_e_fac = active_e_it + active_overhead
    active_pue = active_e_fac / active_e_it

    active_cost_elec = (active_e_fac * tarif) / 1e6
    active_cost_srv = active_n_srv_peak * cost_srv_unit
    active_cost_total = active_cost_elec + active_cost_srv + active_cost_stor
    active_co2 = (active_e_fac * faktor_emisi) / 1000.0

    # Hemat Tunai vs Hemat Setara (Tabel 4)
    srv_freed = n_srv_init - active_n_srv_peak
    cash_save_elec = cost_elec_base - active_cost_elec
    cash_save_maint = srv_freed * maint_srv_unit
    total_cash_save = cash_save_elec + cash_save_maint

    equiv_save_depr = srv_freed * depr_srv_unit
    equiv_save_stor = cost_stor_base - active_cost_stor
    total_equiv_save = equiv_save_depr + equiv_save_stor
    total_cost_save = cost_total_base - active_cost_total

    # Unit Economics (Langkah 13)
    ue_cost_base = (cost_total_base * 1e6) / mahasiswa / 12.0
    ue_cost_active = (active_cost_total * 1e6) / mahasiswa / 12.0
    ue_elec_base = e_fac_base / mahasiswa
    ue_elec_active = active_e_fac / mahasiswa
    ue_co2_base_g = (co2_base * 1e6) / mahasiswa
    ue_co2_active_g = (active_co2 * 1e6) / mahasiswa

    # Titik impas hemat pendingin agar PUE kembali ke PUE awal
    overhead_target_for_init_pue = active_e_it * (pue_init - 1.0)
    overhead_no_cool = overhead_fixed + overhead_var_per_it * active_e_it
    req_overhead_drop = max(0.0, 1.0 - (overhead_target_for_init_pue / overhead_no_cool))
    breakeven_cooling_pct = (req_overhead_drop / cooling_share_of_overhead) * 100.0

    # Biaya perapihan ruang server (Bagian 3: Rp 5 jt bahan + 24 jam * Rp 50 rb)
    biaya_perapihan_juta = (5_000_000 + 24 * 50_000) / 1e6 if use_opt1 else 0.0

    return {
        # Jam & Beban
        "jam_krs": jam_krs,
        "jam_normal": jam_normal,
        "jam_buffer": jam_buffer,
        "jam_two_srv": jam_two_srv,
        "util_app_weighted": util_app_weighted * 100.0,
        "load_norm": load_norm,
        "load_krs": load_krs,
        "load_norm_virt": load_norm_virt,
        "load_krs_virt": load_krs_virt,
        # Baseline
        "p_app_n": p_app_n, "p_app_k": p_app_k, "p_db_n": p_db_n, "p_db_k": p_db_k,
        "p_srv_norm_base": p_srv_norm_base, "p_srv_krs_base": p_srv_krs_base,
        "e_srv_base": e_srv_base, "e_stor_base": e_stor_base, "e_net_base": e_net_base,
        "e_it_base": e_it_base, "e_fac_base": e_fac_base, "overhead_base": overhead_base,
        "overhead_fixed": overhead_fixed, "overhead_var_per_it": overhead_var_per_it,
        "pue_base": pue_init,
        "cost_elec_base": cost_elec_base, "cost_srv_base": cost_srv_base,
        "cost_stor_base": cost_stor_base, "cost_total_base": cost_total_base,
        "co2_base": co2_base,
        # Tahapan berurutan (untuk Waterfall & Tabel 3)
        "n_srv_opt1": n_srv_opt1, "u_norm_opt1": u_norm_opt1 * 100.0, "u_krs_opt1": u_krs_opt1 * 100.0,
        "p_norm_opt1": p_norm_opt1, "p_krs_opt1": p_krs_opt1,
        "e_srv_opt1": e_srv_opt1, "e_it_opt1": e_it_opt1, "overhead_opt1": overhead_opt1,
        "e_fac_opt1": e_fac_opt1, "pue_opt1": pue_opt1,
        "save_e_rightsizing": save_e_rightsizing, "save_e_cooling": save_e_cooling,
        "save_e_opt1": save_e_opt1, "save_cost_opt1": save_cost_opt1, "save_co2_opt1": save_co2_opt1,
        "n_srv_base_auto": n_srv_base_auto, "u_base_auto": u_base_auto * 100.0,
        "p_base_auto": p_base_auto,
        "e_srv_opt2": e_srv_opt2, "e_it_opt2": e_it_opt2, "overhead_opt2": overhead_opt2,
        "e_fac_opt2": e_fac_opt2, "pue_opt2": pue_opt2,
        "save_e_opt2": save_e_opt2, "save_cost_opt2": save_cost_opt2, "save_co2_opt2": save_co2_opt2,
        "tb_fast": tb_fast, "tb_cold": tb_cold, "p_stor_opt3": p_stor_opt3,
        "e_stor_opt3": e_stor_opt3, "e_it_opt3": e_it_opt3, "overhead_opt3": overhead_opt3,
        "e_fac_opt3": e_fac_opt3, "pue_opt3": pue_opt3,
        "cost_stor_opt3": cost_stor_opt3,
        "save_e_opt3": save_e_opt3, "save_cost_opt3": save_cost_opt3, "save_co2_opt3": save_co2_opt3,
        # Skenario Aktif
        "active_n_srv_peak": active_n_srv_peak,
        "active_n_srv_normal": active_n_srv_normal,
        "active_e_srv": active_e_srv,
        "active_e_stor": active_e_stor,
        "active_e_it": active_e_it,
        "active_overhead": active_overhead,
        "active_e_fac": active_e_fac,
        "active_pue": active_pue,
        "active_cost_elec": active_cost_elec,
        "active_cost_srv": active_cost_srv,
        "active_cost_stor": active_cost_stor,
        "active_cost_total": active_cost_total,
        "active_co2": active_co2,
        # Penghematan Tunai vs Setara
        "cash_save_elec": cash_save_elec,
        "cash_save_maint": cash_save_maint,
        "total_cash_save": total_cash_save,
        "equiv_save_depr": equiv_save_depr,
        "equiv_save_stor": equiv_save_stor,
        "total_equiv_save": total_equiv_save,
        "total_cost_save": total_cost_save,
        "total_e_save": e_fac_base - active_e_fac,
        "total_co2_save": co2_base - active_co2,
        # Unit Economics
        "ue_cost_base": ue_cost_base, "ue_cost_active": ue_cost_active,
        "ue_elec_base": ue_elec_base, "ue_elec_active": ue_elec_active,
        "ue_co2_base_g": ue_co2_base_g, "ue_co2_active_g": ue_co2_active_g,
        # Sensitivitas & Payback
        "cooling_mult": cooling_mult,
        "breakeven_cooling_pct": breakeven_cooling_pct,
        "biaya_perapihan_juta": biaya_perapihan_juta,
    }


# ==============================================================================
# SIDEBAR: KONTROL SKENARIO & ASUMSI AUDIT
# ==============================================================================
DEFAULTS = {
    "use_opt1": True,
    "use_opt2": True,
    "use_opt3": True,
    "mahasiswa": 30000,
    "hari_krs": 42,
    "hari_buffer": 6,
    "u_app_norm": 12.0,
    "u_app_krs": 60.0,
    "u_db_norm": 20.0,
    "u_db_krs": 40.0,
    "p_idle": 140.0,
    "p_full": 350.0,
    "total_tb": 20.0,
    "cold_pct": 70.0,
    "pue_init": 1.80,
    "virt_overhead": 10.0,
    "target_util": 70.0,
    "cooling_save": 20.0,
    "tarif": 1500.0,
    "faktor_emisi": 0.80,
    "harga_srv": 120.0,
}

for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v


def reset_defaults():
    for k, v in DEFAULTS.items():
        st.session_state[k] = v


with st.sidebar:
    st.title("⚙️ Kontrol FinOps")
    st.caption("Simulasikan strategi optimasi & uji asumsi audit secara langsung.")

    st.subheader("1. Aktivasi Strategi Optimasi")
    use_opt1 = st.checkbox("Optimasi 1: Rightsizing & Perapihan AC", key="use_opt1")
    use_opt2 = st.checkbox("Optimasi 2: Autoscaling Terjadwal", key="use_opt2")
    use_opt3 = st.checkbox("Optimasi 3: Cold Storage & Tagging", key="use_opt3")

    st.divider()
    st.subheader("2. Parameter Utama")
    mahasiswa = st.number_input("Mahasiswa Aktif", min_value=5000, max_value=100000, step=1000, key="mahasiswa")
    hari_krs = st.slider("Durasi Masa KRS (hari/tahun)", 14, 90, key="hari_krs")
    hari_buffer = st.slider("Hari Penyangga Autoscaling (hari)", 0, 20, key="hari_buffer")
    cooling_save = st.slider("Hemat Pendingin Ruang Server (%)", 0.0, 40.0, step=1.0, key="cooling_save")
    cold_pct = st.slider("Data Lama ke Cold Storage (%)", 0.0, 90.0, step=5.0, key="cold_pct")

    with st.expander("🔧 Parameter Teknis & Finansial Lanjutan"):
        tarif = st.number_input("Tarif Listrik (Rp/kWh)", min_value=500.0, max_value=3000.0, step=50.0, key="tarif")
        faktor_emisi = st.number_input("Faktor Emisi (kg CO2e/kWh)", min_value=0.1, max_value=1.5, step=0.05, key="faktor_emisi")
        pue_init = st.slider("PUE Awal Ruang Server", 1.2, 2.5, step=0.05, key="pue_init")
        target_util = st.slider("Target Utilisasi Puncak (%)", 50.0, 85.0, step=5.0, key="target_util")
        virt_overhead = st.slider("Beban Virtualisasi (%)", 0.0, 20.0, step=1.0, key="virt_overhead")
        harga_srv = st.number_input("Harga 1 Server (Rp Juta)", min_value=50.0, max_value=300.0, step=10.0, key="harga_srv")
        total_tb = st.number_input("Total Penyimpanan (TB)", min_value=5.0, max_value=100.0, step=5.0, key="total_tb")

    st.button("🔄 Reset ke Angka Audit PDF", on_click=reset_defaults, use_container_width=True)

# Kumpulkan parameter & jalankan perhitungan
params = {k: st.session_state[k] for k in DEFAULTS}
res = hitung_finops(params)

# ==============================================================================
# HEADER & KPI CARDS UTAMA
# ==============================================================================
st.title("📊 Dashboard FinOps & Cost Optimization — Portal Akademik (KRS Online)")
st.markdown(
    f"Audit efisiensi biaya, konsumsi listrik, dan jejak karbon layanan on-premise untuk "
    f"**{fmt_id(params['mahasiswa'])} mahasiswa aktif** | "
    f"Masa KRS **{params['hari_krs']} hari/tahun ({params['hari_krs']/365*100:.1f}%)** vs "
    f"Normal **{365 - params['hari_krs']} hari/tahun ({(365-params['hari_krs'])/365*100:.1f}%)**."
)

pct_cost = -((res["total_cost_save"] / res["cost_total_base"]) * 100) if res["cost_total_base"] else 0
pct_e = -((res["total_e_save"] / res["e_fac_base"]) * 100) if res["e_fac_base"] else 0
pct_co2 = -((res["total_co2_save"] / res["co2_base"]) * 100) if res["co2_base"] else 0
delta_pue = res["active_pue"] - res["pue_base"]

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric(
    "Biaya Layanan / Tahun",
    f"Rp {fmt_id(res['active_cost_total'], 1)} Jt",
    f"{pct_cost:.1f}% (Hemat Rp {fmt_id(res['total_cost_save'], 1)} Jt)",
    delta_color="inverse",
)
c2.metric(
    "Listrik Fasilitas / Tahun",
    f"{fmt_id(res['active_e_fac'], 0)} kWh",
    f"{pct_e:.1f}% (-{fmt_id(res['total_e_save'], 0)} kWh)",
    delta_color="inverse",
)
c3.metric(
    "Emisi Karbon / Tahun",
    f"{fmt_id(res['active_co2'], 2)} ton",
    f"{pct_co2:.1f}% (-{fmt_id(res['total_co2_save'], 2)} ton)",
    delta_color="inverse",
)
c4.metric(
    "Biaya / Mahasiswa / Bln",
    f"Rp {fmt_id(res['ue_cost_active'], 0)}",
    f"Sebelumnya Rp {fmt_id(res['ue_cost_base'], 0)}",
    delta_color="off",
)
c5.metric(
    "PUE Fasilitas",
    f"{fmt_id(res['active_pue'], 2)}",
    f"{delta_pue:+.2f} vs awal ({fmt_id(res['pue_base'], 2)})",
    delta_color="inverse",
    help="PUE naik tipis saat beban IT turun drastis karena 40% beban pendingin & UPS bersifat tetap, namun total listrik dan emisi tetap turun 40%.",
)

st.divider()

# ==============================================================================
# NAVIGASI TABS (SIKLUS FINOPS: INFORM -> OPTIMIZE -> OPERATE)
# ==============================================================================
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📈 1. Ringkasan & Dampak (INFORM)",
    "💰 2. Finansial & Tunai vs Setara (OPTIMIZE)",
    "🌿 3. Energi, Beban & Sensitivitas PUE",
    "🏷️ 4. Simulasi Showback Prodi (OPERATE)",
    "🧾 5. Audit Trail (Langkah 1–14)",
])

# ------------------------------------------------------------------------------
# TAB 1: RINGKASAN & DAMPAK OPTIMASI (INFORM)
# ------------------------------------------------------------------------------
with tab1:
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Waterfall Penurunan Biaya Tahunan (Rp Juta)")
        wf_cost = go.Figure(go.Waterfall(
            name="Biaya",
            orientation="v",
            measure=["absolute", "relative", "relative", "relative", "total"],
            x=[
                "Baseline<br>(Awal)",
                "Opt 1:<br>Rightsizing & AC",
                "Opt 2:<br>Autoscaling",
                "Opt 3:<br>Cold Storage",
                "Total<br>Sesudah",
            ],
            y=[
                res["cost_total_base"],
                -res["save_cost_opt1"],
                -res["save_cost_opt2"],
                -res["save_cost_opt3"],
                0,
            ],
            text=[
                f"Rp {fmt_id(res['cost_total_base'], 1)} Jt",
                f"-Rp {fmt_id(res['save_cost_opt1'], 2)} Jt",
                f"-Rp {fmt_id(res['save_cost_opt2'], 2)} Jt",
                f"-Rp {fmt_id(res['save_cost_opt3'], 2)} Jt",
                f"Rp {fmt_id(res['cost_total_base'] - res['save_cost_opt1'] - res['save_cost_opt2'] - res['save_cost_opt3'], 1)} Jt",
            ],
            textposition="outside",
            decreasing={"marker": {"color": "#16a34a"}},
            totals={"marker": {"color": "#0284c7"}},
            connector={"line": {"color": "#94a3b8"}},
        ))
        wf_cost.update_layout(
            height=400,
            yaxis_title="Rp Juta / Tahun",
            margin=dict(t=30, b=20, l=20, r=20),
            yaxis=dict(range=[0, res["cost_total_base"] * 1.18]),
        )
        st.plotly_chart(wf_cost, use_container_width=True)

    with col_right:
        st.subheader("Waterfall Penurunan Listrik Fasilitas (kWh/Tahun)")
        wf_energy = go.Figure(go.Waterfall(
            name="Energi",
            orientation="v",
            measure=["absolute", "relative", "relative", "relative", "total"],
            x=[
                "Baseline<br>(Awal)",
                "Opt 1:<br>Rightsizing & AC",
                "Opt 2:<br>Autoscaling",
                "Opt 3:<br>Cold Storage",
                "Total<br>Sesudah",
            ],
            y=[
                res["e_fac_base"],
                -res["save_e_opt1"],
                -res["save_e_opt2"],
                -res["save_e_opt3"],
                0,
            ],
            text=[
                f"{fmt_id(res['e_fac_base'], 0)}",
                f"-{fmt_id(res['save_e_opt1'], 0)}",
                f"-{fmt_id(res['save_e_opt2'], 0)}",
                f"-{fmt_id(res['save_e_opt3'], 0)}",
                f"{fmt_id(res['e_fac_opt3'], 0)} kWh",
            ],
            textposition="outside",
            decreasing={"marker": {"color": "#0d9488"}},
            totals={"marker": {"color": "#2563eb"}},
            connector={"line": {"color": "#94a3b8"}},
        ))
        wf_energy.update_layout(
            height=400,
            yaxis_title="kWh / Tahun",
            margin=dict(t=30, b=20, l=20, r=20),
            yaxis=dict(range=[0, res["e_fac_base"] * 1.18]),
        )
        st.plotly_chart(wf_energy, use_container_width=True)

    st.subheader("Perbandingan Dampak per Strategi Optimasi (Trade-off Rupiah vs Energi)")
    col_t1, col_t2 = st.columns([1.3, 1])

    df_opt = pd.DataFrame({
        "Optimasi": [
            "1. Rightsizing & Perapihan AC",
            "2. Autoscaling Terjadwal",
            "3. Cold Storage & Tagging",
        ],
        "Hemat Energi (kWh)": [res["save_e_opt1"], res["save_e_opt2"], res["save_e_opt3"]],
        "Hemat Biaya (Rp Juta)": [res["save_cost_opt1"], res["save_cost_opt2"], res["save_cost_opt3"]],
        "Hemat Karbon (ton CO2e)": [res["save_co2_opt1"], res["save_co2_opt2"], res["save_co2_opt3"]],
    })

    with col_t1:
        fig_trade = go.Figure()
        fig_trade.add_trace(go.Bar(
            name="Hemat Biaya (Rp Juta)",
            x=df_opt["Optimasi"],
            y=df_opt["Hemat Biaya (Rp Juta)"],
            marker_color="#2563eb",
            text=[f"Rp {fmt_id(v, 2)} Jt" for v in df_opt["Hemat Biaya (Rp Juta)"]],
            textposition="auto",
        ))
        fig_trade.add_trace(go.Bar(
            name="Hemat Energi (ribu kWh)",
            x=df_opt["Optimasi"],
            y=df_opt["Hemat Energi (kWh)"] / 1000.0,
            marker_color="#10b981",
            text=[f"{fmt_id(v, 0)} kWh" for v in df_opt["Hemat Energi (kWh)"]],
            textposition="auto",
        ))
        fig_trade.update_layout(
            barmode="group",
            height=340,
            yaxis_title="Rp Juta / Ribu kWh",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(t=40, b=20),
        )
        st.plotly_chart(fig_trade, use_container_width=True)

    with col_t2:
        st.markdown(
            """
            <div class="insight-box">
                <strong>Insight Kunci Trade-off:</strong><br>
                • <b>Optimasi 2 (Autoscaling)</b> menyumbang penghematan <b>energi & karbon terbesar</b> (4.484 kWh / 3,59 ton), tetapi hemat rupiahnya paling kecil karena server fisik tetap dimiliki kampus.<br><br>
                • <b>Optimasi 3 (Cold Storage)</b> menyumbang penghematan <b>biaya terbesar</b> (Rp 41,52 juta) berkat pembebasan kapasitas disk cepat, meski hemat energinya paling kecil (1.549 kWh).<br><br>
                • <b>Optimasi 1 (Rightsizing & AC)</b> memberikan keseimbangan tinggi di biaya (Rp 38,14 juta) maupun energi (3.029 kWh).
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.dataframe(
            df_opt.style.format({
                "Hemat Energi (kWh)": lambda x: fmt_id(x, 0),
                "Hemat Biaya (Rp Juta)": lambda x: fmt_id(x, 2),
                "Hemat Karbon (ton CO2e)": lambda x: fmt_id(x, 2),
            }),
            use_container_width=True,
            hide_index=True,
        )

# ------------------------------------------------------------------------------
# TAB 2: ANALISIS FINANSIAL, HEMAT TUNAI VS SETARA & UNIT ECONOMICS
# ------------------------------------------------------------------------------
with tab2:
    col_f1, col_f2 = st.columns(2)

    with col_f1:
        st.subheader("Komposisi Biaya Tahunan: Sebelum vs Sesudah")
        df_comp = pd.DataFrame({
            "Komponen": ["Listrik", "Server (Susut & Rawat)", "Penyimpanan"],
            "Sebelum (Rp Jt)": [res["cost_elec_base"], res["cost_srv_base"], res["cost_stor_base"]],
            "Sesudah (Rp Jt)": [res["active_cost_elec"], res["active_cost_srv"], res["active_cost_stor"]],
        })
        df_comp["Selisih (Rp Jt)"] = df_comp["Sebelum (Rp Jt)"] - df_comp["Sesudah (Rp Jt)"]

        fig_comp = go.Figure()
        fig_comp.add_trace(go.Bar(
            name="Sebelum Optimasi",
            x=df_comp["Komponen"],
            y=df_comp["Sebelum (Rp Jt)"],
            marker_color="#94a3b8",
            text=[f"Rp {fmt_id(v, 1)} Jt" for v in df_comp["Sebelum (Rp Jt)"]],
            textposition="outside",
        ))
        fig_comp.add_trace(go.Bar(
            name="Sesudah Optimasi (Skenario Aktif)",
            x=df_comp["Komponen"],
            y=df_comp["Sesudah (Rp Jt)"],
            marker_color="#0ea5e9",
            text=[f"Rp {fmt_id(v, 1)} Jt" for v in df_comp["Sesudah (Rp Jt)"]],
            textposition="outside",
        ))
        fig_comp.update_layout(
            barmode="group",
            height=380,
            yaxis_title="Rp Juta / Tahun",
            yaxis=dict(range=[0, max(df_comp["Sebelum (Rp Jt)"]) * 1.18]),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig_comp, use_container_width=True)

    with col_f2:
        st.subheader("Hemat Tunai (Cash) vs Hemat Setara (Non-Cash)")
        if res["total_cost_save"] > 0:
            fig_cash = go.Figure(data=[go.Pie(
                labels=[
                    f"Hemat Tunai: Listrik (Rp {fmt_id(res['cash_save_elec'], 1)} Jt)",
                    f"Hemat Tunai: Pemeliharaan Server (Rp {fmt_id(res['cash_save_maint'], 1)} Jt)",
                    f"Hemat Setara: Penyusutan Server (Rp {fmt_id(res['equiv_save_depr'], 1)} Jt)",
                    f"Hemat Setara: Kapasitas Storage (Rp {fmt_id(res['equiv_save_stor'], 1)} Jt)",
                ],
                values=[
                    max(0, res["cash_save_elec"]),
                    max(0, res["cash_save_maint"]),
                    max(0, res["equiv_save_depr"]),
                    max(0, res["equiv_save_stor"]),
                ],
                hole=0.45,
                marker_colors=["#15803d", "#22c55e", "#0284c7", "#38bdf8"],
            )])
            fig_cash.update_layout(
                height=380,
                legend=dict(orientation="h", y=-0.15),
                annotations=[dict(
                    text=f"Total<br><b>Rp {fmt_id(res['total_cost_save'], 1)} Jt</b>",
                    x=0.5, y=0.5, font_size=15, showarrow=False
                )],
            )
            st.plotly_chart(fig_cash, use_container_width=True)
        else:
            st.info("Aktifkan minimal satu strategi optimasi di sidebar untuk melihat rincian penghematan.")

    st.markdown(
        f"""
        <div class="warning-box">
            <strong>Catatan Penting Tata Kelola On-Premise:</strong><br>
            Dari total penghematan <b>Rp {fmt_id(res['total_cost_save'], 1)} juta/tahun</b>, sebesar
            <b>Rp {fmt_id(res['total_cash_save'], 1)} juta ({(res['total_cash_save']/res['total_cost_save']*100) if res['total_cost_save'] else 0:.1f}%)</b>
            merupakan <b>hemat tunai</b> (uang yang benar-benar tidak keluar untuk tagihan PLN & kontrak pemeliharaan), sedangkan
            <b>Rp {fmt_id(res['total_equiv_save'], 1)} juta</b> merupakan <b>hemat setara</b> (kapasitas server & disk yang dibebaskan).
            Hemat setara akan menjadi manfaat riil jika perangkat dipakai ulang untuk layanan kampus lain atau menunda belanja peremajaan.
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Unit Economics & Payback
    st.subheader("Unit Economics per Mahasiswa & Analisis Investasi Perapihan")
    ue1, ue2, ue3, ue4 = st.columns(4)
    ue1.metric(
        "Biaya / Mahasiswa / Bulan",
        f"Rp {fmt_id(res['ue_cost_active'], 0)}",
        f"-Rp {fmt_id(res['ue_cost_base'] - res['ue_cost_active'], 0)} (-{(1 - res['ue_cost_active']/res['ue_cost_base'])*100:.1f}%)",
        delta_color="inverse",
    )
    ue2.metric(
        "Listrik / Mahasiswa / Tahun",
        f"{fmt_id(res['ue_elec_active'], 2)} kWh",
        f"-{fmt_id(res['ue_elec_base'] - res['ue_elec_active'], 2)} kWh",
        delta_color="inverse",
    )
    ue3.metric(
        "Karbon / Mahasiswa / Tahun",
        f"{fmt_id(res['ue_co2_active_g'], 0)} gram",
        f"-{fmt_id(res['ue_co2_base_g'] - res['ue_co2_active_g'], 0)} gram",
        delta_color="inverse",
    )
    if res["biaya_perapihan_juta"] > 0 and res["total_cash_save"] > 0:
        payback_bulan = (res["biaya_perapihan_juta"] / res["total_cash_save"]) * 12.0
        ue4.metric(
            "Payback Perapihan Ruang Server",
            f"{fmt_id(payback_bulan, 1)} bulan",
            f"Biaya awal Rp {fmt_id(res['biaya_perapihan_juta'], 1)} Jt",
            delta_color="off",
        )
    else:
        ue4.metric("Biaya Awal Perapihan", "Rp 0", "Optimasi 1 tidak aktif")

# ------------------------------------------------------------------------------
# TAB 3: PROFIL BEBAN, ENERGI & UJI SENSITIVITAS PUE
# ------------------------------------------------------------------------------
with tab3:
    col_g1, col_g2 = st.columns(2)

    with col_g1:
        st.subheader("Profil Daya & Masalah Idle (Normal vs KRS)")
        df_power = pd.DataFrame({
            "Periode": ["Masa Normal (323 hari)", "Masa KRS (42 hari)"],
            "Baseline (6 Server)": [res["p_srv_norm_base"], res["p_srv_krs_base"]],
            "Setelah Rightsizing (5 Server)": [res["p_norm_opt1"], res["p_krs_opt1"]],
            "Setelah Autoscaling (2 Base / 5 Puncak)": [res["p_base_auto"], res["p_krs_opt1"]],
        })
        fig_pwr = px.bar(
            df_power.melt(id_vars="Periode", var_name="Konfigurasi", value_name="Daya (Watt)"),
            x="Periode",
            y="Daya (Watt)",
            color="Konfigurasi",
            barmode="group",
            color_discrete_sequence=["#ef4444", "#f59e0b", "#10b981"],
            text_auto=".0f",
        )
        fig_pwr.update_layout(
            height=370,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig_pwr, use_container_width=True)

        st.caption(
            f"Pada kondisi awal, selama {365 - params['hari_krs']} hari di luar KRS, 6 server hanya menanggung beban setara "
            f"**{fmt_id(res['load_norm'], 2)} server** (rata-rata utilisasi aplikasi setahun hanya **{fmt_id(res['util_app_weighted'], 1)}%**), "
            f"namun tiap server tetap menyedot minimal {fmt_id(params['p_idle'], 0)} W saat idle."
        )

    with col_g2:
        st.subheader("Uji Sensitivitas Hemat Pendingin terhadap PUE & Energi (Langkah 14)")
        cool_range = np.arange(0, 36, 2)
        sens_rows = []
        for cs in cool_range:
            mult = 1.0 - (0.80 * (cs / 100.0))
            ovh = mult * (res["overhead_fixed"] + res["overhead_var_per_it"] * res["active_e_it"])
            efac = res["active_e_it"] + ovh
            pue_val = efac / res["active_e_it"]
            co2_val = (efac * params["faktor_emisi"]) / 1000.0
            sens_rows.append({
                "Hemat Pendingin (%)": cs,
                "Pengali Overhead": mult,
                "Energi Fasilitas (kWh)": efac,
                "PUE Akhir": pue_val,
                "Emisi Akhir (ton CO2e)": co2_val,
            })
        df_sens = pd.DataFrame(sens_rows)

        fig_sens = go.Figure()
        fig_sens.add_trace(go.Scatter(
            x=df_sens["Hemat Pendingin (%)"],
            y=df_sens["PUE Akhir"],
            name="PUE Akhir",
            mode="lines+markers",
            line=dict(color="#2563eb", width=3),
            yaxis="y1",
        ))
        fig_sens.add_trace(go.Scatter(
            x=df_sens["Hemat Pendingin (%)"],
            y=df_sens["Energi Fasilitas (kWh)"],
            name="Energi Fasilitas (kWh)",
            mode="lines",
            line=dict(color="#10b981", width=2, dash="dash"),
            yaxis="y2",
        ))
        fig_sens.add_hline(
            y=params["pue_init"],
            line_dash="dot",
            line_color="#dc2626",
            annotation_text=f"PUE Awal ({fmt_id(params['pue_init'], 2)})",
            annotation_position="top right",
        )
        fig_sens.add_vline(
            x=params["cooling_save"],
            line_dash="dot",
            line_color="#0f172a",
            annotation_text=f"Asumsi Aktif ({fmt_id(params['cooling_save'], 0)}%)",
        )
        fig_sens.update_layout(
            height=370,
            xaxis_title="Persentase Hemat Pendingin (%)",
            yaxis=dict(title="PUE Akhir", side="left"),
            yaxis2=dict(title="Energi Fasilitas (kWh)", overlaying="y", side="right", showgrid=False),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig_sens, use_container_width=True)

        st.markdown(
            f"""
            <div class="warning-box">
                <strong>Mengapa PUE Naik Tipis ({fmt_id(res['pue_base'], 2)} → {fmt_id(res['active_pue'], 2)})?</strong><br>
                Karena <b>40% beban overhead ({fmt_id(res['overhead_fixed'], 0)} kWh)</b> adalah beban tetap (UPS, lampu, sebagian AC).
                Saat energi IT berhasil ditekan tajam, pembagi pada rumus PUE (Energi Fasilitas ÷ Energi IT) mengecil lebih cepat.
                Agar PUE kembali ke <b>{fmt_id(params['pue_init'], 2)}</b>, diperlukan penghematan pendingin sekitar
                <b>{fmt_id(res['breakeven_cooling_pct'], 1)}%</b>.
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Tabel Skenario Kunci (0%, 20%, 30%) sesuai Langkah 14 PDF
    st.subheader("Tabel Uji Sensitivitas (Skenario 0%, 20%, dan 30%)")
    key_sens = []
    for label, cs in [("0% (Tanpa Perapihan)", 0), ("20% (Asumsi Utama)", 20), ("30% (Skenario Optimistis)", 30)]:
        mult = 1.0 - (0.80 * (cs / 100.0))
        ovh = mult * (res["overhead_fixed"] + res["overhead_var_per_it"] * res["active_e_it"])
        efac = res["active_e_it"] + ovh
        key_sens.append({
            "Skenario Hemat Pendingin": label,
            "Pengali Beban Tambahan": fmt_id(mult, 2),
            "Energi Fasilitas Akhir (kWh)": fmt_id(efac, 0),
            "PUE Akhir": fmt_id(efac / res["active_e_it"], 2),
            "Emisi Akhir (ton CO2e)": fmt_id((efac * params["faktor_emisi"]) / 1000.0, 2),
        })
    st.table(pd.DataFrame(key_sens))

# ------------------------------------------------------------------------------
# TAB 4: SIMULASI SHOWBACK & TAGGING PER PRODI (OPERATE)
# ------------------------------------------------------------------------------
with tab4:
    st.subheader("Simulasi Tagging & Showback Biaya per Fakultas / Unit (Fase OPERATE)")
    st.info(
        "Pada kondisi awal audit, belum tersedia tagging dan laporan biaya per prodi/fakultas. "
        "Tabel di bawah adalah **simulasi Showback interaktif** yang mengalokasikan total biaya layanan aktual hasil optimasi "
        f"(**Rp {fmt_id(res['active_cost_total'], 1)} juta/tahun**) berdasarkan proporsi mahasiswa dan pemakaian arsip data. "
        "Anda dapat mengedit angka pada tabel untuk mensimulasikan pembagian biaya."
    )

    default_prodi = pd.DataFrame({
        "Tag Pemilik (Unit/Fakultas)": [
            "FASILKOM-TI", "Fakultas Teknik", "Fakultas Ekonomi & Bisnis",
            "Fakultas Kedokteran", "Fakultas Hukum", "Fakultas Lainnya (Gabungan)"
        ],
        "Porsi Mahasiswa (%)": [12.0, 18.0, 20.0, 10.0, 12.0, 28.0],
        "Porsi Storage (%)": [18.0, 17.0, 15.0, 15.0, 10.0, 25.0],
    })

    edited_prodi = st.data_editor(
        default_prodi,
        use_container_width=True,
        num_rows="dynamic",
        hide_index=True,
    )

    sum_mhs = edited_prodi["Porsi Mahasiswa (%)"].sum()
    sum_stor = edited_prodi["Porsi Storage (%)"].sum()

    if sum_mhs > 0 and sum_stor > 0:
        df_show = edited_prodi.copy()
        w_mhs = df_show["Porsi Mahasiswa (%)"] / sum_mhs
        w_stor = df_show["Porsi Storage (%)"] / sum_stor

        # Alokasi: Komputasi & Listrik ikut porsi trafik mahasiswa, Storage ikut porsi storage
        compute_elec_cost = res["active_cost_srv"] + res["active_cost_elec"]
        df_show["Alokasi Compute & Listrik (Rp Jt)"] = w_mhs * compute_elec_cost
        df_show["Alokasi Storage (Rp Jt)"] = w_stor * res["active_cost_stor"]
        df_show["Total Showback (Rp Jt/Thn)"] = (
            df_show["Alokasi Compute & Listrik (Rp Jt)"] + df_show["Alokasi Storage (Rp Jt)"]
        )
        df_show["Estimasi Emisi (ton CO2e)"] = w_mhs * res["active_co2"]

        c_sb1, c_sb2 = st.columns([1.2, 1])
        with c_sb1:
            fig_sb = px.bar(
                df_show,
                x="Tag Pemilik (Unit/Fakultas)",
                y=["Alokasi Compute & Listrik (Rp Jt)", "Alokasi Storage (Rp Jt)"],
                title="Alokasi Showback Tahunan per Pemilik Biaya (Rp Juta)",
                barmode="stack",
                color_discrete_sequence=["#0284c7", "#38bdf8"],
            )
            fig_sb.update_layout(height=360, yaxis_title="Rp Juta / Tahun", legend_title="Komponen")
            st.plotly_chart(fig_sb, use_container_width=True)

        with c_sb2:
            st.dataframe(
                df_show[[
                    "Tag Pemilik (Unit/Fakultas)",
                    "Total Showback (Rp Jt/Thn)",
                    "Estimasi Emisi (ton CO2e)",
                ]].style.format({
                    "Total Showback (Rp Jt/Thn)": lambda x: f"Rp {fmt_id(x, 2)} Jt",
                    "Estimasi Emisi (ton CO2e)": lambda x: f"{fmt_id(x, 2)} ton",
                }),
                use_container_width=True,
                hide_index=True,
            )

# ------------------------------------------------------------------------------
# TAB 5: AUDIT TRAIL PERHITUNGAN LENGKAP (LANGKAH 1 - 14)
# ------------------------------------------------------------------------------
with tab5:
    st.subheader("Audit Trail Perhitungan Bertahap (Langkah 1 sampai 14)")
    audit_data = [
        ("Langkah 1", "Jam Operasi Setahun", f"KRS: {fmt_id(res['jam_krs'])} jam | Normal: {fmt_id(res['jam_normal'])} jam | Penyangga: {fmt_id(res['jam_buffer'])} jam"),
        ("Langkah 2", "Daya per Server (Baseline)", f"App: {fmt_id(res['p_app_n'],1)} W (N) / {fmt_id(res['p_app_k'],1)} W (KRS) | DB: {fmt_id(res['p_db_n'],1)} W (N) / {fmt_id(res['p_db_k'],1)} W (KRS)"),
        ("Langkah 3", "Daya Total 6 Server", f"Normal: {fmt_id(res['p_srv_norm_base'],1)} W | Saat KRS: {fmt_id(res['p_srv_krs_base'],1)} W"),
        ("Langkah 4", "Energi Server (Baseline)", f"{fmt_id(res['e_srv_base'], 1)} kWh/tahun"),
        ("Langkah 5", "Energi IT (Baseline)", f"Server {fmt_id(res['e_srv_base'],0)} + Storage {fmt_id(res['e_stor_base'],0)} + Jaringan {fmt_id(res['e_net_base'],0)} = {fmt_id(res['e_it_base'],0)} kWh"),
        ("Langkah 6", "Energi Fasilitas & Overhead (Baseline)", f"Fasilitas: {fmt_id(res['e_fac_base'],0)} kWh (PUE {fmt_id(res['pue_base'],2)}) | Tetap: {fmt_id(res['overhead_fixed'],0)} kWh | Rasio Var: {fmt_id(res['overhead_var_per_it'],2)}"),
        ("Langkah 7", "Biaya & Karbon Baseline", f"Biaya: Rp {fmt_id(res['cost_total_base'],1)} Jt (Listrik {fmt_id(res['cost_elec_base'],1)} + Server {fmt_id(res['cost_srv_base'],1)} + Storage {fmt_id(res['cost_stor_base'],1)}) | Karbon: {fmt_id(res['co2_base'],2)} ton"),
        ("Langkah 8", "Opt 1 — Rightsizing", f"Beban KRS+Virt: {fmt_id(res['load_krs_virt'],2)} srv → {res['n_srv_opt1']} server (Utilisasi {fmt_id(res['u_norm_opt1'],2)}% N / {fmt_id(res['u_krs_opt1'],1)}% KRS) | Energi IT: {fmt_id(res['e_it_opt1'],0)} kWh"),
        ("Langkah 9", "Opt 1 — Perapihan Pendingin", f"Pengali Overhead: {fmt_id(res['cooling_mult'],2)} | Fasilitas: {fmt_id(res['e_fac_opt1'],0)} kWh (PUE {fmt_id(res['pue_opt1'],2)}) | Hemat: {fmt_id(res['save_e_opt1'],0)} kWh, Rp {fmt_id(res['save_cost_opt1'],2)} Jt"),
        ("Langkah 10", "Opt 2 — Autoscaling Terjadwal", f"{res['n_srv_base_auto']} server dasar ({fmt_id(res['u_base_auto'],1)}%) selama {fmt_id(res['jam_two_srv'])} jam | Fasilitas: {fmt_id(res['e_fac_opt2'],0)} kWh | Hemat: {fmt_id(res['save_e_opt2'],0)} kWh, Rp {fmt_id(res['save_cost_opt2'],2)} Jt"),
        ("Langkah 11", "Opt 3 — Cold Storage", f"{fmt_id(res['tb_fast'],0)} TB cepat + {fmt_id(res['tb_cold'],0)} TB dingin ({fmt_id(res['p_stor_opt3'],0)} W) | Fasilitas: {fmt_id(res['e_fac_opt3'],0)} kWh | Hemat: {fmt_id(res['save_e_opt3'],0)} kWh, Rp {fmt_id(res['save_cost_opt3'],2)} Jt"),
        ("Langkah 12", "Hasil Skenario Aktif", f"Biaya: Rp {fmt_id(res['active_cost_total'],1)} Jt | Listrik: {fmt_id(res['active_e_fac'],0)} kWh | Karbon: {fmt_id(res['active_co2'],2)} ton | PUE: {fmt_id(res['active_pue'],2)}"),
        ("Langkah 13", "Unit Economics per Mahasiswa", f"Rp {fmt_id(res['ue_cost_base'],0)} → Rp {fmt_id(res['ue_cost_active'],0)}/bln | {fmt_id(res['ue_elec_base'],2)} → {fmt_id(res['ue_elec_active'],2)} kWh/thn | {fmt_id(res['ue_co2_base_g'],0)} → {fmt_id(res['ue_co2_active_g'],0)} g CO2e"),
        ("Langkah 14", "Sensitivitas Pendingin", f"Titik impas PUE={fmt_id(params['pue_init'],2)} membutuhkan hemat pendingin {fmt_id(res['breakeven_cooling_pct'],1)}%"),
    ]
    df_audit = pd.DataFrame(audit_data, columns=["Tahap", "Indikator", "Hasil Perhitungan"])
    st.dataframe(df_audit, use_container_width=True, hide_index=True)

    csv_export = df_audit.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="⬇️ Unduh Ringkasan Audit (CSV)",
        data=csv_export,
        file_name="audit_finops_portal_krs.csv",
        mime="text/csv",
    )