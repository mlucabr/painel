import streamlit as st
from streamlit_autorefresh import st_autorefresh
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

# ==========================
# Configurações iniciais
# ==========================
st.set_page_config(page_title="Painel de Cotações", layout="wide")

st.title("Painel de Cotações – Ações, ETFs e Índices")

st.markdown(
    """
    Fonte de dados: Yahoo Finance (cotações atrasadas, não em tempo real).  
    A página se atualiza automaticamente a cada 5 minutos.
    """
)

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

    # Índices e câmbio
    "IBOV": "^BVSP",
    "USDBRL": "USDBRL=X",
    "EURBRL": "EURBRL=X",
}

# ==========================
# Funções auxiliares
# ==========================

def get_quote_data(yf_ticker: str):
    """
    Busca dados de cotação via yfinance:
    - Fechamento anterior
    - Preço atual (último close)
    - Máxima / mínima de 52 semanas
    - Timestamp do último dado (horário do Yahoo, convertido para America/Sao_Paulo se possível)
    Retorna dict ou None em caso de falha.
    """
    end = datetime.today()
    start = end - timedelta(days=400)

    try:
        # multi_level_index=False evita multiindex nas colunas,
        # o que simplifica hist["Close"].iloc[-1]
        hist = yf.download(
            yf_ticker,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            auto_adjust=False,
            progress=False,
            multi_level_index=False,
        )
    except Exception:
        hist = None

    if hist is None or hist.empty:
        return None

    # Timestamp do último ponto
    try:
        last_ts = hist.index[-1]
    except Exception:
        return None

    # Converter para horário de São Paulo se tiver timezone
    if isinstance(last_ts, pd.Timestamp) and last_ts.tzinfo is not None:
        last_ts_local = last_ts.tz_convert("America/Sao_Paulo")
    else:
        last_ts_local = last_ts

    # Preço atual = último fechamento disponível (scalar)
    try:
        last_close = hist["Close"].iloc[-1]
    except Exception:
        return None

    # Fechamento anterior = penúltimo fechamento, se existir
    if len(hist["Close"]) > 1:
        prev_close = hist["Close"].iloc[-2]
    else:
        prev_close = None

    # 52 semanas ~ últimos 365 dias
    hist_52w = hist[hist.index >= (end - timedelta(days=365))]
    if hist_52w.empty:
        high_52w = hist["High"].max()
        low_52w = hist["Low"].min()
    else:
        high_52w = hist_52w["High"].max()
        low_52w = hist_52w["Low"].min()

    return {
        "current_price": float(last_close),
        "prev_close": float(prev_close) if prev_close is not None else None,
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
                "Ativo": label,
                "Fechamento anterior": None,
                "Preço atual": None,
                "Variação %": None,
                "Máx 52s": None,
                "Mín 52s": None,
                "% do atual vs máx 52s": None,
                "Data/Hora (Yahoo)": None,
                "Ticker Yahoo": yf_ticker,
                "Status": "Erro ao baixar dados",
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
            "Ativo": label,
            "Fechamento anterior": round(prev_close, 4) if prev_close else None,
            "Preço atual": round(current_price, 4),
            "Variação %": round(pct_change, 2) if pct_change is not None else None,
            "Máx 52s": round(high_52w, 4),
            "Mín 52s": round(low_52w, 4),
            "% do atual vs máx 52s": round(pct_of_high, 2) if pct_of_high is not None else None,
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
    "CXSE3", "VALE3", "PRIO3", "GOAU4",
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
    st.subheader("Tabela de cotações")
    
    df = df.sort_values(by="Variação %", ascending=False)
    styled = (
        df.style
        .map(color_pct, subset=["Variação %"])
        .format({
            "Fechamento anterior": "{:,.4f}",
            "Preço atual": "{:,.4f}",
            "Variação %": "{:+.2f}%",
            "Máx 52s": "{:,.4f}",
            "Mín 52s": "{:,.4f}",
            "% do atual vs máx 52s": "{:,.2f}%",
        })
    )

    st.dataframe(styled, use_container_width=True)

    st.caption(
        "Obs.: valores em tempo atrasado, baseados em dados históricos baixados do Yahoo Finance via yfinance."
    )
