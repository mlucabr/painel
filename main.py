import streamlit as st
from streamlit_autorefresh import st_autorefresh
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

# ==========================
# Configurações iniciais
# ==========================
st.set_page_config(page_title="Tyello", layout="wide")
st.title("Painel de Controle")

import streamlit as st

# ... seus imports e st.set_page_config existentes ...

with st.sidebar:
    st.page_link("main.py", label="Painel", icon="📊")
    st.page_link("pages/1_Carteira.py", label="Carteira", icon="📂")
# Autorefresh a cada 5 minutos (300.000 ms)
st_autorefresh(interval=5 * 60 * 1000, key="datarefresh")

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

# ==========================
# Funções auxiliares
# ==========================

def get_quote_data(yf_ticker: str):
    """
    Busca dados de cotação via yfinance:
    - Fechamento anterior (Previous Close do Yahoo)
    - Preço “atual” (último intraday, 5m atrasado aprox.)
    - Máxima / mínima de 52 semanas (diário, ~últimos 400 dias)
    - Timestamp do último dado (intraday ou diário)
    Retorna dict ou None em caso de falha.
    """
    # ---------- Histórico longo para 52 semanas ----------
    try:
        hist_52 = yf.download(
            yf_ticker,
            period="400d",        # ~últimos 400 dias
            interval="1d",
            auto_adjust=False,
            progress=False,
            multi_level_index=False,
        )
    except Exception:
        hist_52 = None

    if hist_52 is None or hist_52.empty:
        return None

    # 52 semanas ~ últimos 365 dias
    end = datetime.today()
    hist_52w = hist_52[hist_52.index >= (end - timedelta(days=365))]
    if hist_52w.empty:
        high_52w = hist_52["High"].max()
        low_52w = hist_52["Low"].min()
    else:
        high_52w = hist_52w["High"].max()
        low_52w = hist_52w["Low"].min()

    # ---------- 2 dias diários para Previous Close ----------
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

    # Se só tiver 1 linha (ativo muito novo, primeiro dia), usa o mesmo valor
    if len(daily_2d["Close"]) == 1:
        prev_close = daily_2d["Close"].iloc[0]
        current_daily = prev_close
    else:
        # iloc[-2] = dia anterior (Previous Close), iloc[-1] = dia atual (parcial ou fechado)
        prev_close = daily_2d["Close"].iloc[-2]
        current_daily = daily_2d["Close"].iloc[-1]

    # ---------- Intraday para Preço atual ----------
    try:
        intraday = yf.download(
            yf_ticker,
            period="1d",          # só o pregão de hoje
            interval="5m",        # candles de 5 minutos (com atraso do Yahoo)
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
        # fallback: usa o diário do dia atual
        last_ts = daily_2d.index[-1]
        last_close = current_daily

    # Converter timestamp para horário de São Paulo se tiver timezone
    if isinstance(last_ts, pd.Timestamp) and last_ts.tzinfo is not None:
        last_ts_local = last_ts.tz_convert("America/Sao_Paulo")
    else:
        last_ts_local = last_ts

    return {
        "current_price": float(last_close),                          # Preço
        "prev_close": float(prev_close) if prev_close is not None else None,  # Anterior (Previous Close)
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
    return df


def color_pct(val):
    """Função de cor para a coluna de variação percentual."""
    if pd.isna(val):
        return ""
    color = "green" if val > 0 else "red" if val < 0 else "black"
    # Styler.map espera uma string CSS
    return f"color: {color};"


# ==========================
# UI – filtros e exibição
# ==========================

st.sidebar.header("Filtros")

df_lista = load_asset_list()

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

    # (Opcional) já começar ordenado pela maior variação
    # df = df.sort_values(by="Variação %", ascending=False)

    # Formatação da tabela
    df = df.sort_values(by="Variação %", ascending=False)
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
    height="content",  # ajuste esse valor até ficar confortável
    row_height=24, # ajustar até valor que gostar
    )

    st.caption(
        "Obs.: valores com delay ~20min, via yfinance. Atualizado a cada 5 min. Painel v1.0"
    )
