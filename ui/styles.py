import streamlit as st

def apply_css():
    st.markdown('''<style>
    .stApp{background:#071426;color:#F5F8FC}.block-container{padding:1.5rem 2.2rem 3rem;max-width:1450px}
    [data-testid="stSidebar"]{background:#0B1B31;border-right:1px solid #1D385A}
    [data-testid="stSidebar"] *{color:#EAF2FB!important}
    h1,h2,h3{color:#FFFFFF!important}.muted{color:#A9BDD4;font-size:.9rem}
    .hero{background:linear-gradient(135deg,#102C4B,#0B1D34);border:1px solid #244B73;border-radius:18px;padding:24px 28px;margin-bottom:18px}
    .invoice-id{font-size:30px;font-weight:800;color:#fff;letter-spacing:.4px}.supplier{font-size:17px;color:#AFC6DD;margin-top:4px}
    .card{background:#0D223B;border:1px solid #24496F;border-radius:15px;padding:18px;margin:10px 0}.label{font-size:11px;text-transform:uppercase;color:#7FA7CC;font-weight:700;letter-spacing:.8px}.value{font-size:18px;font-weight:700;color:#F5F8FC}
    .tag{display:inline-block;background:#153A60;border:1px solid #2C628F;border-radius:999px;padding:5px 10px;margin:2px;color:#DDEEFF;font-weight:700;font-size:12px}
    .section{font-size:13px;font-weight:800;letter-spacing:1.1px;color:#8FC5F5;margin:20px 0 8px;text-transform:uppercase}
    .stButton>button{background:#1769AA;color:white;border:0;border-radius:9px;font-weight:700;padding:.55rem 1rem}.stButton>button:hover{background:#2180C9;color:#fff}
    [data-testid="stMetricValue"]{color:#fff}.dataframe{background:#0D223B}
    </style>''',unsafe_allow_html=True)

def card(label,value):
    st.markdown(f'<div class="card"><div class="label">{label}</div><div class="value">{value}</div></div>',unsafe_allow_html=True)
