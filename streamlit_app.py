import streamlit as st
from streamlit_autorefresh import st_autorefresh
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

# ==========================
# Configurações iniciais
# ==========================
st.set_page_config(page_title="Painel de Cotações", layout="wide")
st.title("Painel de Controle")

import streamlit as st

# ... seus imports e st.set_page_config existentes ...

with st.sidebar:
    st.page_link("streamlit_app.py", label="Painel", icon="📊")
    st.page_link("pages/1_Carteira.py", label="Carteira", icon="📂")
# Autorefresh a cada 5 minutos (300.000 ms)
st_autorefresh(interval=5 * 60 * 1000, key="datarefresh")

# ==========================
# Mapeamento de tickers
# ==========================

# Dicionário: nome amigável -> ticker no Yahoo Finance
TICKERS = {
    # Exterior (UCITS / EUA)
    "IWDA": "IWDA.L",   # iShares Core MSCI World UCITS
    "IWQU": "IWQU.L",    # iShares Edge MSCI World Quality UCITS
    "WSML": "WSML.L",    # iShares MSCI World Small Cap UCITS
    "EMVL": "EMVL.L",    # iShares EM Value Factor UCITS
    "IWVL": "IWVL.L",    # iShares World Value Factor UCITS
    "IFSW": "IFSW.L",    # iShares STOXX World Equity Multifactor UCITS
    "BITW": "BITW",      # Bitwise 10 Crypto Index Fund

    # ETFs B3
    "HASH11": "HASH11.SA",
    "JURO11": "JURO11.SA",
    "SMAC11": "SMAC11.SA",
    "IRIM11": "IRIM11.SA",
    "DIVO11": "DIVO11.SA",
    "LVOL11": "LVOL11.SA",
    "BMMT11": "BMMT11.SA",
    "BOVV11": "BOVV11.SA",
    "SPXR11": "SPXR11.SA",
    "LFTS11": "LFTS11.SA",
    "B5P211": "B5P211.SA",
    "IB5M11": "IB5M11.SA",

    # Ações B3
    "SUZB3": "SUZB3.SA",
    "CSAN3": "CSAN3.SA",
    "KLBN11": "KLBN11.SA",
    "BEEF3": "BEEF3.SA",
    "LREN3": "LREN3.SA",
    "BBAS3": "BBAS3.SA",
    "VVEO3": "VVEO3.SA",
    "BBDC4": "BBDC4.SA",
    "CMIG4": "CMIG4.SA",
    "EGIE3": "EGIE3.SA",
    "WIZC3": "WIZC3.SA",
    "UNIP6": "UNIP6.SA",
    "ITSA4": "ITSA4.SA",
    "ALOS3": "ALOS3.SA",
    "CXSE3": "CXSE3.SA",
    "VALE3": "VALE3.SA",
    "PRIO3": "PRIO3.SA",
    "GOAU4": "GOAU4.SA",
    "PSSA3": "PSSA3.SA",
    "PETR4": "PETR4.SA",
    

    # Índices e câmbio
    "IBOV": "^BVSP",
    "USDBRL": "USDBRL=X",
    "EURBRL": "EURBRL=X",
}

# Agrupando as listas conforme você descreveu
externos = ["IWDA", "IWQU", "WSML", "EMVL", "IWVL", "IFSW", "BITW"]
b3_etfs = [
    "HASH11", "JURO11", "SMAC11", "IRIM11", "DIVO11", "LVOL11",
    "BMMT11", "BOVV11", "SPXR11", "LFTS11", "B5P211", "IB5M11",
]
b3_acoes = [
    "SUZB3", "CSAN3", "KLBN11", "BEEF3", "LREN3", "BBAS3", "VVEO3",
    "BBDC4", "CMIG4", "EGIE3", "WIZC3", "UNIP6", "ITSA4", "ALOS3",
    "CXSE3", "VALE3", "PRIO3", "GOAU4", "PETR4", "PSSA3",
]
indices = ["IBOV", "USDBRL", "EURBRL"]

# Mapa Ativo -> Grupo
GROUPS = {}
for t in externos:
    GROUPS[t] = "IBKR"
for t in b3_etfs:
    GROUPS[t] = "ETFs_BR"
for t in b3_acoes:
    GROUPS[t] = "Clube"
for t in indices:
    GROUPS[t] = "Outros"

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


def build_table(selected_symbols):
    rows = []
    for label in selected_symbols:
        yf_ticker = TICKERS.get(label)
        if yf_ticker is None:
            continue

        data = get_quote_data(yf_ticker)
        if data is None:
            rows.append({
                "Grupo": GROUPS.get(label, ""),
                "Ativo": label,
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
            "Grupo": GROUPS.get(label, ""),
            "Ativo": label,
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

    df = pd.DataFrame(rows)
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

# Agrupando as listas conforme você descreveu
externos = ["IWDA", "IWQU", "WSML", "EMVL", "IWVL", "IFSW", "BITW"]
b3_etfs = [
    "HASH11", "JURO11", "SMAC11", "IRIM11", "DIVO11", "LVOL11",
    "BMMT11", "BOVV11", "SPXR11", "LFTS11", "B5P211", "IB5M11",
]
b3_acoes = [
    "SUZB3", "CSAN3", "KLBN11", "BEEF3", "LREN3", "BBAS3", "VVEO3",
    "BBDC4", "CMIG4", "EGIE3", "WIZC3", "UNIP6", "ITSA4", "ALOS3",
    "CXSE3", "VALE3", "PRIO3", "GOAU4", "PETR4", "PSSA3"
]
indices = ["IBOV", "USDBRL", "EURBRL"]

st.sidebar.markdown("### Grupos de ativos")
show_externos = st.sidebar.checkbox("Exterior", True)
show_b3_etfs = st.sidebar.checkbox("ETFs Brasil", True)
show_b3_acoes = st.sidebar.checkbox("Ações Brasil", True)
show_indices = st.sidebar.checkbox("Índices e câmbio", True)

symbols = []
if show_externos:
    symbols += externos
if show_b3_etfs:
    symbols += b3_etfs
if show_b3_acoes:
    symbols += b3_acoes
if show_indices:
    symbols += indices

# Permitir que o usuário remova/adicione especificamente
symbols = st.sidebar.multiselect(
    "Selecione os ativos para exibir",
    options=list(TICKERS.keys()),
    default=symbols,
)

if not symbols:
    st.warning("Selecione pelo menos um ativo na barra lateral.")
else:
    df = build_table(symbols)

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
