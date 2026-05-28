import streamlit as st
from streamlit_autorefresh import st_autorefresh
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

# ==========================
# Configurações iniciais
# ==========================
st.set_page_config(
    page_title="Tyello",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1rem;
        padding-bottom: 1rem;
    }

    header[data-testid="stHeader"] {
        background: rgba(255, 255, 255, 0);
        height: 0rem;
    }

    h1 {
        font-size: 1.8rem !important;
        margin-top: 0rem !important;
        margin-bottom: 0.2rem !important;
        padding-top: 0rem !important;
    }

    div[data-testid="stMetric"] {
        padding-top: 0.1rem;
        padding-bottom: 0.1rem;
    }

    div[data-testid="stMetricLabel"] p {
    font-size: 0.80rem !important;
    }

    div[data-testid="stMetricValue"] {
        font-size: 0.95rem !important;
    }

    div[data-testid="stMetricDelta"] {
        font-size: 0.75rem !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Painel de Controle")

with st.sidebar:
    st.page_link("main.py", label="Painel", icon="📊")
    st.page_link("pages/1_Carteira.py", label="Carteira", icon="📂")

st_autorefresh(interval=5 * 60 * 1000, key="datarefresh")


# ==========================
# Leitura do Excel de configuração
# ==========================
def find_default_excel():
    root = Path(".")
    preferred_names = [
        root / "mlucadata.xlsx",
        root / "mlucadata.xls",
    ]

    for file_path in preferred_names:
        if file_path.exists() and file_path.is_file():
            return file_path

    pattern_matches = sorted(root.glob("mlucadata*.xlsx")) + sorted(root.glob("mlucadata*.xls"))
    for file_path in pattern_matches:
        if file_path.exists() and file_path.is_file():
            return file_path

    return None


def load_asset_list():
    excel_path = find_default_excel()
    if excel_path is None:
        st.error("Arquivo mlucadata não encontrado na raiz do repositório.")
        st.stop()

    try:
        df_lista = pd.read_excel(excel_path, sheet_name="Lista")
    except Exception as e:
        st.error(f"Erro ao ler a aba 'Lista' do Excel: {e}")
        st.stop()

    expected_cols = ["Grupo", "Ativo", "Ticker Yahoo"]
    missing = [c for c in expected_cols if c not in df_lista.columns]
    if missing:
        st.error(f"Colunas faltando na aba 'Lista': {missing}")
        st.stop()

    df_lista = df_lista[expected_cols].copy()
    df_lista["Grupo"] = df_lista["Grupo"].astype(str).str.strip()
    df_lista["Ativo"] = df_lista["Ativo"].astype(str).str.strip()
    df_lista["Ticker Yahoo"] = df_lista["Ticker Yahoo"].astype(str).str.strip()

    df_lista = df_lista[
        (df_lista["Grupo"] != "") &
        (df_lista["Ativo"] != "") &
        (df_lista["Ticker Yahoo"] != "")
    ].drop_duplicates(subset=["Ativo"], keep="first")

    return df_lista


# ==========================
# Funções auxiliares
# ==========================
def get_quote_data(yf_ticker: str):
    try:
        hist_52 = yf.download(
            yf_ticker,
            period="400d",
            interval="1d",
            auto_adjust=False,
            progress=False,
            multi_level_index=False,
        )
    except Exception:
        hist_52 = None

    if hist_52 is None or hist_52.empty:
        return None

    end = datetime.today()
    hist_52w = hist_52[hist_52.index >= (end - timedelta(days=365))]

    if hist_52w.empty:
        high_52w = hist_52["High"].max()
        low_52w = hist_52["Low"].min()
    else:
        high_52w = hist_52w["High"].max()
        low_52w = hist_52w["Low"].min()

    try:
        daily_2d = yf.download(
            yf_ticker,
            period="2d",
            interval="1d",
            auto_adjust=False,
            progress=False,
            multi_level_index=False,
        )
    except Exception:
        daily_2d = None

    if daily_2d is None or daily_2d.empty:
        return None

    if len(daily_2d["Close"]) == 1:
        prev_close = daily_2d["Close"].iloc[0]
        current_daily = prev_close
    else:
        prev_close = daily_2d["Close"].iloc[-2]
        current_daily = daily_2d["Close"].iloc[-1]

    try:
        intraday = yf.download(
            yf_ticker,
            period="1d",
            interval="5m",
            auto_adjust=False,
            progress=False,
            multi_level_index=False,
        )
    except Exception:
        intraday = None

    if intraday is not None and not intraday.empty:
        last_ts = intraday.index[-1]
        last_close = intraday["Close"].iloc[-1]
    else:
        last_ts = daily_2d.index[-1]
        last_close = current_daily

    if isinstance(last_ts, pd.Timestamp) and last_ts.tzinfo is not None:
        last_ts_local = last_ts.tz_convert("America/Sao_Paulo")
    else:
        last_ts_local = last_ts

    return {
        "current_price": float(last_close),
        "prev_close": float(prev_close) if prev_close is not None else None,
        "high_52w": float(high_52w),
        "low_52w": float(low_52w),
        "last_datetime": last_ts_local,
    }


def build_table(df_selected):
    rows = []

    for _, row in df_selected.iterrows():
        grupo = row["Grupo"]
        ativo = row["Ativo"]
        yf_ticker = row["Ticker Yahoo"]

        data = get_quote_data(yf_ticker)

        if data is None:
            rows.append({
                "Grupo": grupo,
                "Ativo": ativo,
                "Anterior": None,
                "Preço": None,
                "Variação %": None,
                "Max 52s": None,
                "Min 52s": None,
                "% max 52s": None,
                "Data/Hora (Yahoo)": None,
                "Ticker Yahoo": yf_ticker,
                "Status": "Erro",
            })
            continue

        current_price = data["current_price"]
        prev_close = data["prev_close"]
        high_52w = data["high_52w"]
        low_52w = data["low_52w"]
        last_dt = data.get("last_datetime")

        if prev_close:
            pct_change = (current_price / prev_close - 1) * 100
        else:
            pct_change = None

        if high_52w:
            pct_of_high = (current_price / high_52w) * 100
        else:
            pct_of_high = None

        if isinstance(last_dt, (pd.Timestamp, datetime)):
            last_dt_str = last_dt.strftime("%Y-%m-%d %H:%M")
        else:
            last_dt_str = str(last_dt) if last_dt is not None else None

        rows.append({
            "Grupo": grupo,
            "Ativo": ativo,
            "Anterior": round(prev_close, 2) if prev_close else None,
            "Preço": round(current_price, 2),
            "Variação %": round(pct_change, 2) if pct_change is not None else None,
            "Max 52s": round(high_52w, 2),
            "Min 52s": round(low_52w, 2),
            "% max 52s": round(pct_of_high, 2) if pct_of_high is not None else None,
            "Data/Hora (Yahoo)": last_dt_str,
            "Ticker Yahoo": yf_ticker,
            "Status": "OK",
        })

    return pd.DataFrame(rows)


def color_pct(val):
    if pd.isna(val):
        return ""
    color = "green" if val > 0 else "red" if val < 0 else "black"
    return f"color: {color};"


def fmt_metric_value(x):
    if x is None or pd.isna(x):
        return "-"
    return f"{x:,.2f}"


def fmt_metric_delta(x):
    if x is None or pd.isna(x):
        return None
    return f"{x:+.2f}%"


def render_outros_kpis(df_lista):
    df_outros = df_lista[df_lista["Grupo"].str.lower() == "outros"].copy()

    if df_outros.empty:
        return

    cols = st.columns(len(df_outros))

    for i, (_, row) in enumerate(df_outros.iterrows()):
        ativo = row["Ativo"]
        yf_ticker = row["Ticker Yahoo"]
        data = get_quote_data(yf_ticker)

        if data is None:
            cols[i].metric(f"**{ativo}**", "-", delta=None)
            continue

        current_price = data["current_price"]
        prev_close = data["prev_close"]

        if prev_close:
            delta_pct = (current_price / prev_close - 1) * 100
        else:
            delta_pct = None

        cols[i].metric(
            f"**{ativo}**",
            fmt_metric_value(current_price),
            delta=fmt_metric_delta(delta_pct),
        )


# ==========================
# Carrega lista e renderiza KPIs
# ==========================
df_lista = load_asset_list()
render_outros_kpis(df_lista)

# ==========================
# UI – filtros e exibição
# ==========================
st.sidebar.header("Filtros")

grupos_disponiveis = sorted(df_lista["Grupo"].dropna().unique())
grupos_selecionados = st.sidebar.multiselect(
    "Selecione os grupos",
    options=grupos_disponiveis,
    default=grupos_disponiveis,
)

df_filtrado = df_lista[df_lista["Grupo"].isin(grupos_selecionados)].copy()

ativos_default = df_filtrado["Ativo"].tolist()
ativos_selecionados = st.sidebar.multiselect(
    "Selecione os ativos para exibir",
    options=df_lista["Ativo"].tolist(),
    default=ativos_default,
)

df_filtrado = df_filtrado[df_filtrado["Ativo"].isin(ativos_selecionados)].copy()

if df_filtrado.empty:
    st.warning("Selecione pelo menos um ativo na barra lateral.")
else:
    df = build_table(df_filtrado)
    df = df.sort_values(by="Variação %", ascending=False, na_position="last")

    styled = (
        df.style
        .map(color_pct, subset=["Variação %"])
        .format({
            "Anterior": "{:,.2f}",
            "Preço": "{:,.2f}",
            "Variação %": "{:+.2f}%",
            "Max 52s": "{:,.2f}",
            "Min 52s": "{:,.2f}",
            "% max 52s": "{:,.2f}%",
        })
    )

    st.dataframe(
        styled,
        use_container_width=True,
        hide_index=True,
        height="content",
        row_height=24,
    )

    st.caption(
        "Obs.: valores com delay ~20min, via yfinance. Atualizado a cada 5 min. Painel v1.0"
    )
