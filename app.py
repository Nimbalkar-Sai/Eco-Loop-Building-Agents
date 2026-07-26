"""
app.py — EcoLoop AI Entry Point
Run with: streamlit run app.py
"""

import importlib
import streamlit as st

st.set_page_config(
    page_title="EcoLoop AI — Honeywell Hackathon",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded",
)

with open("style.css") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# ── Page registry ──────────────────────────────────────────────────────────────
PAGES = [
    ("🏠", "Dashboard",    "page_modules.home"),
    ("⚡", "Simulation",   "page_modules.baseline"),
    ("🤖", "AI Analysis",  "page_modules.ai_analysis"),
    ("🎯", "Optimization", "page_modules.optimization"),
    ("📊", "Comparison",   "page_modules.energy_comparison"),
    ("📄", "Reports",      "page_modules.reports"),
]
PAGE_LABELS = [f"{icon} {label}" for icon, label, _ in PAGES]

if "active_page" not in st.session_state:
    st.session_state.active_page = PAGE_LABELS[0]

# ── Global CSS (animations + sidebar shell) ────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
section[data-testid="stSidebar"] {
    background: #0d1117 !important;
    border-right: 1px solid rgba(229,57,53,0.18) !important;
}
section[data-testid="stSidebar"] > div:first-child { padding: 0 !important; }
section[data-testid="stSidebar"] * { font-family: 'Inter', sans-serif !important; }
@keyframes pulse-dot {
    0%,100% { opacity:1; transform:scale(1); }
    50%      { opacity:.55; transform:scale(1.35); }
}
@keyframes fadeIn { from { opacity:0; transform:translateY(4px); } to { opacity:1; transform:translateY(0); } }
.sb-pulse { animation: pulse-dot 2.4s ease-in-out infinite; }
.sb-fadein { animation: fadeIn .4s ease forwards; }
/* Hide only the ligature text, keep arrow SVG and button fully visible */
div[data-testid="stSidebarCollapseButton"] span { font-size: 0 !important; }
div[data-testid="stSidebarCollapseButton"] svg { display: block !important; visibility: visible !important; }
div[data-testid="stSidebarCollapseButton"] button { display: block !important; visibility: visible !important; opacity: 1 !important; }

/* Hide nav trigger buttons visually but keep them clickable */
section[data-testid="stSidebar"] .stButton { margin-top: -40px !important; height: 40px !important; opacity: 0 !important; position: relative !important; z-index: 10 !important; }
section[data-testid="stSidebar"] .stButton > button { width:100% !important; height:40px !important; background:transparent !important; border:none !important; cursor:pointer !important; }
</style>
""", unsafe_allow_html=True)

# ── Live data ──────────────────────────────────────────────────────────────────
@st.cache_data(ttl=10)
def _get_status():
    try:
        import backend as bk
        return bk.get_system_status()
    except Exception:
        return {}

@st.cache_data(ttl=30)
def _get_session_metrics():
    try:
        import backend as bk
        summary = bk.get_history_summary()
        df      = bk.get_history_df()
        latest  = bk.get_latest_metrics()
        cycle   = int(summary.get("total_cycles", 0))
        savings = float(summary.get("avg_savings_pct", 0.0))
        pmv     = round(float(latest.pmv), 2) if latest and latest.pmv is not None else "—"
        co2     = round(float(latest.carbon_intensity), 3) if latest and latest.carbon_intensity else "—"
        runtime = f"{df['TotalTimeSec'].max():.0f}s" if not df.empty and "TotalTimeSec" in df.columns else "—"
        return cycle, savings, pmv, co2, runtime
    except Exception:
        return 0, 0.0, "—", "—", "—"

raw_status = _get_status()

SERVICES = [
    ("EnergyPlus",       raw_status.get("EnergyPlus", "offline")),
    ("Ollama",           raw_status.get("Ollama", "offline")),
    ("MCP Server",       "online"),
    ("History DB",       raw_status.get("History DB", "offline")),
    ("Simulation",       raw_status.get("Simulation", "offline")),
    ("Llama 3.2",        raw_status.get("LLM Model", "offline")),
]

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:

    # ── HEADER ────────────────────────────────────────────────────────────────
    st.markdown("""
    <div style="padding:20px 16px 0;font-family:'Inter',sans-serif;">
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:10px;">
            <div style="width:46px;height:46px;border-radius:12px;
                        background:linear-gradient(135deg,#0d9488,#0f766e);
                        display:flex;align-items:center;justify-content:center;
                        font-size:22px;flex-shrink:0;
                        box-shadow:0 4px 16px rgba(13,148,136,0.45);">🏢</div>
            <div>
                <div style="font-size:17px;font-weight:800;color:#f9fafb;
                            letter-spacing:-0.3px;line-height:1.2;">EcoLoop AI</div>
                <div style="font-size:10.5px;color:#6b7280;margin-top:2px;">
                    Autonomous Building Intelligence</div>
            </div>
        </div>
        <div style="height:1px;background:linear-gradient(90deg,transparent,rgba(229,57,53,0.5),transparent);
                    margin-bottom:14px;"></div>
    </div>
    """, unsafe_allow_html=True)

    # ── NAVIGATION ────────────────────────────────────────────────────────────
    st.markdown("""
    <div style="padding:0 16px 6px;font-family:'Inter',sans-serif;">
        <div style="font-size:9px;font-weight:700;letter-spacing:1.2px;
                    text-transform:uppercase;color:#4b5563;margin-bottom:8px;">Navigation</div>
    </div>
    """, unsafe_allow_html=True)

    for icon, label, _ in PAGES:
        full_label = f"{icon} {label}"
        is_active  = st.session_state.active_page == full_label

        if is_active:
            bg     = "linear-gradient(135deg,#0d9488,#0f766e)"
            border = "rgba(13,148,136,0.5)"
            shadow = "0 4px 14px rgba(13,148,136,0.3)"
            color  = "#ffffff"
            bar    = "<div style='position:absolute;left:0;top:0;bottom:0;width:3px;background:#fff;border-radius:0 3px 3px 0;'></div>"
        else:
            bg     = "rgba(255,255,255,0.03)"
            border = "rgba(255,255,255,0.06)"
            shadow = "none"
            color  = "#9ca3af"
            bar    = ""

        html = (
            "<div style='padding:0 10px 4px;font-family:Inter,sans-serif;'>"
            "<div style='display:flex;align-items:center;gap:10px;padding:10px 12px;"
            f"border-radius:10px;cursor:pointer;font-size:13px;font-weight:500;"
            f"position:relative;overflow:hidden;background:{bg};"
            f"border:1px solid {border};box-shadow:{shadow};'>"
            + bar +
            f"<span style='font-size:15px;min-width:20px;text-align:center;'>{icon}</span>"
            f"<span style='color:{color};font-weight:{'600' if is_active else '500'};'>{label}</span>"
            "</div></div>"
        )
        st.markdown(html, unsafe_allow_html=True)

        if st.button("", key=f"nav_{label}", use_container_width=True):
            st.session_state.active_page = full_label
            st.rerun()

    # ── SYSTEM HEALTH ─────────────────────────────────────────────────────────
    st.markdown("""
    <div style="padding:0 16px;font-family:'Inter',sans-serif;margin-top:4px;">
        <div style="height:1px;background:linear-gradient(90deg,transparent,rgba(229,57,53,0.4),transparent);
                    margin:12px 0;"></div>
        <div style="font-size:9px;font-weight:700;letter-spacing:1.2px;
                    text-transform:uppercase;color:#4b5563;margin-bottom:8px;">System Health</div>
    </div>
    """, unsafe_allow_html=True)

    for svc_name, svc_state in SERVICES:
        is_online   = svc_state == "online"
        dot_color   = "#22c55e" if is_online else "#ef4444"
        dot_shadow  = "rgba(34,197,94,0.6)" if is_online else "rgba(239,68,68,0.6)"
        badge_bg    = "rgba(34,197,94,0.12)" if is_online else "rgba(239,68,68,0.12)"
        badge_color = "#4ade80" if is_online else "#f87171"
        badge_text  = "ONLINE" if is_online else "OFFLINE"
        pulse_cls   = "sb-pulse" if is_online else ""

        st.markdown(f"""
        <div style="padding:0 16px 5px;font-family:'Inter',sans-serif;">
            <div style="display:flex;align-items:center;gap:9px;
                        padding:8px 11px;border-radius:8px;
                        background:rgba(255,255,255,0.03);
                        border:1px solid rgba(255,255,255,0.07);">
                <div class="{pulse_cls}" style="width:8px;height:8px;border-radius:50%;flex-shrink:0;
                             background:{dot_color};box-shadow:0 0 6px {dot_shadow};"></div>
                <span style="font-size:12px;font-weight:500;color:#d1d5db;flex:1;">{svc_name}</span>
                <span style="font-size:9px;font-weight:700;letter-spacing:.6px;
                             padding:2px 6px;border-radius:4px;
                             background:{badge_bg};color:{badge_color};">{badge_text}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # ── FOOTER ────────────────────────────────────────────────────────────────
    st.markdown("""
    <div style="padding:0 16px 16px;font-family:'Inter',sans-serif;">
        <div style="height:1px;background:linear-gradient(90deg,transparent,rgba(229,57,53,0.4),transparent);
                    margin:14px 0 10px;"></div>
        <div style="text-align:center;">
            <div style="font-size:11px;font-weight:600;color:#6b7280;">EcoLoop AI v1.0</div>
            <div style="font-size:10px;color:#4b5563;margin-top:3px;">
                Powered by EnergyPlus · Llama 3.2 · FastMCP</div>
            
        
    </div>
    """, unsafe_allow_html=True)

# ── Route to active page ───────────────────────────────────────────────────────
active_module = next(mod for icon, label, mod in PAGES if f"{icon} {label}" == st.session_state.active_page)
mod = importlib.import_module(active_module)
importlib.reload(mod)
mod.render()
