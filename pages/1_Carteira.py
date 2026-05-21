import io
import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh
from pathlib import Path

# Atualiza automaticamente a cada 5 minutos
st_autorefresh(interval=5 * 60 * 1000, key="carteira_refresh")


# ==========================
# Funções auxiliares gerais
# ==========================

def fmt_num(x, dec=2, signed=False, pct=False):
    if pd.isna(x):
        return ""
    fmt = f"{{:{'+' if signed else ''},.{dec}f}}"
    s = fmt.format(x)
    # troca ponto e vírgula para padrão brasileiro
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    if pct:
        s += "%"
    return s


def fmt_int(x):
    if pd.isna(x):
        return ""
    s = f"{x:,.0f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return s


def fmt_pct(x):
    return fmt_num(x, dec=2, signed=True, pct=True)


def get_usdbrl_rate():
    try:
        data = yf.download(
            "USDBRL=X",
            period="2d",
            interval="1d",
            auto_adjust=False,
            progress=False,
            multi_level_index=False,
        )
    except Exception:
        return None

    if data is None or data.empty:
        return None
    return float(data["Close"].iloc[-1])

def find_default_excel():
    """
    Procura na raiz do repo um arquivo Excel cujo nome comece com 'mlucadata'.
    Prioridade:
    1) mlucadata.xlsx
    2) mlucadata.xls
    3) mlucadata*.xlsx
    4) mlucadata*.xls
    Retorna um Path ou None.
    """
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

def read_excel_updated_at(file_obj):
    """
    Lê a data de atualização da aba Controle, célula B1.
    Retorna string formatada ou None.
    """
    try:
        if isinstance(file_obj, (bytes, bytearray)):
            excel_source = io.BytesIO(file_obj)
        else:
            excel_source = file_obj

        value = pd.read_excel(
            excel_source,
            sheet_name="Controle",
            header=None,
            usecols="B",
            nrows=1,
        ).iloc[0, 0]

        if pd.isna(value):
            return None

        ts = pd.to_datetime(value, errors="coerce")
        if pd.notna(ts):
            if ts.hour == 0 and ts.minute == 0 and ts.second == 0:
                return ts.strftime("%d/%m/%Y")
            return ts.strftime("%d/%m/%Y %H:%M")

        return str(value)

    except Exception:
        return None

# ==========================
# Layout topo: voltar, título, upload
# ==========================

col_title, col_upload = st.columns([3, 1])

with col_title:
    # Botão para voltar ao Painel
    st.page_link("streamlit_app.py", label="← Voltar para Painel", icon="🏠")
    st.title("Carteira de Investimentos")

# Inicializa storage do arquivo na sessão
if "carteira_file_bytes" not in st.session_state:
    st.session_state["carteira_file_bytes"] = None

if "carteira_file_name" not in st.session_state:
    st.session_state["carteira_file_name"] = None

# Tenta localizar arquivo padrão na raiz do repo
default_excel_path = find_default_excel()

with col_upload:
    uploaded_file = st.file_uploader(
        "Upload do arquivo Excel",
        type=["xlsx", "xls"]
    )

    # Se o usuário subir um arquivo, ele tem prioridade sobre o default da raiz
    if uploaded_file is not None:
        st.session_state["carteira_file_bytes"] = uploaded_file.getvalue()
        st.session_state["carteira_file_name"] = uploaded_file.name

# Se ainda não houver arquivo na sessão, tenta carregar o arquivo padrão da raiz
if st.session_state["carteira_file_bytes"] is None and default_excel_path is not None:
    try:
        st.session_state["carteira_file_bytes"] = default_excel_path.read_bytes()
        st.session_state["carteira_file_name"] = default_excel_path.name
    except Exception as e:
        st.error(f"Erro ao ler o arquivo padrão '{default_excel_path.name}': {e}")
        st.stop()

# Se não temos nem upload nem arquivo padrão, fica aguardando upload
if st.session_state["carteira_file_bytes"] is None:
    st.info("Envie um arquivo .xlsx/.xls para ver a carteira.")
    st.stop()

# Lê o Excel a partir dos bytes armazenados
try:
    file_bytes = st.session_state["carteira_file_bytes"]

    # Lê metadado da aba Controle
    excel_updated_at = read_excel_updated_at(file_bytes)

    # Lê a planilha principal da carteira
    df_raw = pd.read_excel(io.BytesIO(file_bytes), sheet_name="upload_data")
except Exception as e:
    st.error(f"Erro ao ler o Excel: {e}")
    st.stop()
    
# Exibe origem do arquivo carregado
if st.session_state["carteira_file_name"]:
    file_name = st.session_state["carteira_file_name"]

    if excel_updated_at:
        st.caption(f"Arquivo carregado: {file_name} | Atualizado: {excel_updated_at}")
    else:
        st.caption(f"Arquivo carregado: {file_name}")
        
# Conferir colunas esperadas
expected_cols = [
    "Ativo",
    "Carteira",
    "Posição",
    "Preço médio",
    "PM Ajustado",
    "Escopo",
]
missing = [c for c in expected_cols if c not in df_raw.columns]
if missing:
    st.error(f"Colunas faltando no Excel: {missing}")
    st.stop()

# Mantém apenas as colunas relevantes e garante tipos numéricos
df_port = df_raw[expected_cols].copy()
df_port["Posição"] = pd.to_numeric(df_port["Posição"], errors="coerce").fillna(0.0)
df_port["Preço médio"] = pd.to_numeric(df_port["Preço médio"], errors="coerce").fillna(0.0)
df_port["PM Ajustado"] = pd.to_numeric(df_port["PM Ajustado"], errors="coerce").fillna(0.0)

# ==========================
# Mapeamento para Yahoo Finance e Moeda
# ==========================

YF_SPECIAL = {
    # Exterior (ajuste conforme seus ativos reais)
    "IWDA": "IWDA.L",
    "IWQU": "IWQU.L",
    "WSML": "WSML.L",
    "EMVL": "EMVL.L",
    "IWVL": "IWVL.L",
    "IFSW": "IFSW.L",
    "BITW": "BITW",

    # Índices / câmbio
    "IBOV": "^BVSP",
    "USDBRL": "USDBRL=X",
    "EURBRL": "EURBRL=X",
}


def map_to_yahoo(ativo: str) -> str:
    """
    Converte o nome do ativo (coluna 'Ativo' da planilha)
    para o ticker do Yahoo Finance.
    Regra:
      - Se estiver em YF_SPECIAL, usa o mapeamento.
      - Se já terminar com '.SA', usa como está.
      - Caso contrário, assume B3 e adiciona '.SA'.
    """
    if ativo in YF_SPECIAL:
        return YF_SPECIAL[ativo]
    if ativo.endswith(".SA"):
        return ativo
    return f"{ativo}.SA"


df_port["Ticker Yahoo"] = df_port["Ativo"].astype(str).apply(map_to_yahoo)

# Mapa de moeda por carteira (ajuste conforme nomes reais da planilha)
CURRENCY_BY_CARTEIRA = {
    "Exterior": "USD",
    "ETF.BR": "BRL",
    "Clube": "BRL",
}
df_port["Moeda"] = df_port["Carteira"].map(CURRENCY_BY_CARTEIRA).fillna("BRL")

# ==========================
# Função de cotações (similar ao painel)
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

    if len(daily_2d["Close"]) == 1:
        prev_close = daily_2d["Close"].iloc[0]
        current_daily = prev_close
    else:
        prev_close = daily_2d["Close"].iloc[-2]
        current_daily = daily_2d["Close"].iloc[-1]

    # ---------- Intraday para preço atual ----------
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


# ==========================
# Filtro por carteira (abaixo do título, meia largura)
# ==========================

col_filtro, _ = st.columns([1, 1])

with col_filtro:
    carteiras_disponiveis = sorted(df_port["Carteira"].dropna().unique())
    selecionadas = st.multiselect(
        "Filtrar por carteira",
        options=carteiras_disponiveis,
        default=carteiras_disponiveis,
        label_visibility="visible",
    )

df_port_filtered = df_port[df_port["Carteira"].isin(selecionadas)]

if df_port_filtered.empty:
    st.warning("Nenhum ativo para as carteiras selecionadas.")
    st.stop()

# ==========================
# Taxa de câmbio USDBRL
# ==========================

usdbrl = get_usdbrl_rate()
if usdbrl is None:
    st.error("Não foi possível obter a cotação USDBRL. Não dá para consolidar em BRL.")
    st.stop()

# ==========================
# Buscar cotações para cada ativo
# ==========================

unique_tickers = (
    df_port_filtered[["Ativo", "Ticker Yahoo"]]
    .drop_duplicates()
    .reset_index(drop=True)
)

quote_rows = []
for _, row in unique_tickers.iterrows():
    ativo = row["Ativo"]
    yf_ticker = row["Ticker Yahoo"]
    data = get_quote_data(yf_ticker)
    if data is None:
        quote_rows.append({
            "Ativo": ativo,
            "Anterior": None,
            "Preço": None,
            "% Atual": None,
            "Ticker Yahoo": yf_ticker,
            "Data/Hora (Yahoo)": None,
        })
        continue

    current_price = data["current_price"]
    prev_close = data["prev_close"]
    last_dt = data["last_datetime"]

    if prev_close:
        pct_change = (current_price / prev_close - 1) * 100
    else:
        pct_change = None

    if isinstance(last_dt, (pd.Timestamp, datetime)):
        ts_str = last_dt.strftime("%d/%m/%Y %H:%M")
    else:
        ts_str = str(last_dt) if last_dt is not None else None

    quote_rows.append({
        "Ativo": ativo,
        "Anterior": prev_close,
        "Preço": current_price,
        "% Atual": pct_change,
        "Ticker Yahoo": yf_ticker,
        "Data/Hora (Yahoo)": ts_str,
    })

df_quotes = pd.DataFrame(quote_rows)

# ==========================
# Juntar carteira + cotações
# ==========================

df = df_port_filtered.merge(df_quotes, on=["Ativo", "Ticker Yahoo"], how="left")

# ==========================
# Cálculos de colunas derivadas (local e BRL)
# ==========================

df["Valor Anterior"] = df["Posição"] * df["Anterior"]
df["Valor de Mercado"] = df["Posição"] * df["Preço"]

df["Valor Anterior BRL"] = df.apply(
    lambda row: row["Valor Anterior"] * usdbrl if row["Moeda"] == "USD" else row["Valor Anterior"],
    axis=1,
)
df["Valor de Mercado BRL"] = df.apply(
    lambda row: row["Valor de Mercado"] * usdbrl if row["Moeda"] == "USD" else row["Valor de Mercado"],
    axis=1,
)

df["Total investido"] = df["Posição"] * df["Preço médio"]
df["Total ajustado"] = df["Posição"] * df["PM Ajustado"]

df["Total investido BRL"] = df.apply(
    lambda row: row["Total investido"] * usdbrl if row["Moeda"] == "USD" else row["Total investido"],
    axis=1,
)
df["Total ajustado BRL"] = df.apply(
    lambda row: row["Total ajustado"] * usdbrl if row["Moeda"] == "USD" else row["Total ajustado"],
    axis=1,
)

# P&L do dia por ativo (local e BRL)
df["P&L dia"] = df["Valor de Mercado"] - df["Valor Anterior"]
df["P&L dia BRL"] = df.apply(
    lambda row: row["P&L dia"] * usdbrl if row["Moeda"] == "USD" else row["P&L dia"],
    axis=1,
)

# Retornos percentuais (não dependem de moeda)
df["Total return"] = (
    (df["Valor de Mercado"] / df["Total investido"] - 1) * 100
).where(df["Total investido"] > 0)

df["TR PMA"] = (
    (df["Valor de Mercado"] / df["Total ajustado"] - 1) * 100
).where(df["Total ajustado"] > 0)

# ==========================
# Linha totalizadora (em BRL)
# ==========================

tot_valor_anterior_brl = df["Valor Anterior BRL"].sum()
tot_valor_mercado_brl = df["Valor de Mercado BRL"].sum()
tot_investido_brl = df["Total investido BRL"].sum()
tot_ajustado_brl = df["Total ajustado BRL"].sum()
tot_pl_dia_brl = df["P&L dia BRL"].sum()
tot_pl_dia = df["P&L dia"].sum()

if tot_valor_anterior_brl > 0:
    carteira_pct_dia = (tot_valor_mercado_brl / tot_valor_anterior_brl - 1) * 100
else:
    carteira_pct_dia = None

if tot_investido_brl > 0:
    carteira_total_return = (tot_valor_mercado_brl / tot_investido_brl - 1) * 100
else:
    carteira_total_return = None

if tot_ajustado_brl > 0:
    carteira_tr_pma = (tot_valor_mercado_brl / tot_ajustado_brl - 1) * 100
else:
    carteira_tr_pma = None

total_row = {
    "Carteira": "TOTAL",
    "Ativo": "",
    "Moeda": "",
    "Posição": float("nan"),
    "Preço médio": float("nan"),
    "PM Ajustado": float("nan"),
    "Escopo": "",
    "Anterior": float("nan"),
    "Valor Anterior": float("nan"),
    "Valor Anterior BRL": tot_valor_anterior_brl,
    "P&L dia": float("nan"),
    "P&L dia BRL": tot_pl_dia_brl,
    "Preço": float("nan"),
    "% Atual": carteira_pct_dia if carteira_pct_dia is not None else float("nan"),
    "Valor de Mercado": float("nan"),
    "Valor de Mercado BRL": tot_valor_mercado_brl,
    "Total investido": float("nan"),
    "Total investido BRL": tot_investido_brl,
    "Total ajustado": float("nan"),
    "Total ajustado BRL": tot_ajustado_brl,
    "Total return": carteira_total_return if carteira_total_return is not None else float("nan"),
    "TR PMA": carteira_tr_pma if carteira_tr_pma is not None else float("nan"),
    "Ticker Yahoo": "",
    "Data/Hora (Yahoo)": "",
}

df_detail = df.copy()
df_total = pd.DataFrame([total_row])

# ==========================
# KPIs da carteira (em BRL)
# ==========================

col1, col2, col3, col4, col5, col6 = st.columns(6)

with col1:
    st.metric(
        "Valor de Mercado (BRL)",
        fmt_num(tot_valor_mercado_brl),
        help="Somatório do Valor de Mercado (BRL) para as carteiras selecionadas."
    )

with col2:
    delta_dia = fmt_pct(carteira_pct_dia) if carteira_pct_dia is not None else "-"
    st.metric(
        "P&L Dia (original)",
        fmt_num(tot_pl_dia),
        delta=delta_dia,
        help="Variação da carteira hoje somando o P&L de cada ativo em sua moeda original, sem conversão para BRL."
    )

with col3:
        st.metric(
        "P&L Dia (BRL)",
        fmt_num(tot_pl_dia_brl),
        delta=delta_dia,
        help="Variação da carteira hoje em BRL em relação ao fechamento do dia anterior."
    )

with col4:
    st.metric(
        "Total Return",
        fmt_pct(carteira_total_return) if carteira_total_return is not None else "-",
        help="Retorno acumulado da carteira em relação ao total investido (BRL)."
    )

with col5:
    st.metric(
        "Total Return (PMA)",
        fmt_pct(carteira_tr_pma) if carteira_tr_pma is not None else "-",
        help="Retorno acumulado da carteira considerando o Preço Mádio Ajustado (BRL)."
    )

with col6:
    st.metric(
        "USD/BRL",
        fmt_num(usdbrl),
        help="Cotação BRL por 1 USD obtida via Yahoo Finance (USDBRL=X)."
    )

# ==========================
# Exibição
# ==========================

rename_cols = {
    "Carteira": "Carteira",
    "Ativo": "Ativo",
    "Moeda": "Moeda",
    "Posição": "Custódia",
    "Preço médio": "PM",
    "PM Ajustado": "PMA",
    "Escopo": "Escopo",
    "Anterior": "Fech Ant",
    "Valor Anterior": "Vlr Ant",
    "Valor Anterior BRL": "Vlr Ant(BRL)",
    "P&L dia": "P&L Dia",
    "P&L dia BRL": "P&L Dia(BRL)",
    "Preço": "Cotação",
    "% Atual": "% Dia",
    "Valor de Mercado": "Vlr Mercado",
    "Valor de Mercado BRL": "Vlr Mercado(BRL)",
    "Total investido": "Tot Investido",
    "Total investido BRL": "Tot Investido(BRL)",
    "Total ajustado": "Tot Ajust.Prov",
    "Total ajustado BRL": "Tot Ajust.Prov(BRL)",
    "Total return": "Tot Return",
    "TR PMA": "Tot Return PMA",
    "Data/Hora (Yahoo)": "Data/Hora",
    "Ticker Yahoo": "Ticker",
}

df_detail = df_detail.rename(columns=rename_cols)
df_total = df_total.rename(columns=rename_cols)

cols_order = [
    "Carteira",
    "Ativo",
    "Custódia",
    "PMA",
    "PM",
    "Moeda",
    "Cotação",
    "% Dia",
    "P&L Dia",
    "P&L Dia(BRL)",
    "Vlr Mercado",
    "Vlr Mercado(BRL)",
    "Fech Ant",
    "Vlr Ant",
    "Vlr Ant(BRL)",
    "Tot Investido",
    "Tot Investido(BRL)",
    "Tot Return",
    "Tot Ajust.Prov",
    "Tot Ajust.Prov(BRL)",
    "Tot Return PMA",
    "Escopo",
    "Data/Hora",
    "Ticker",
]

df_detail = df_detail[cols_order].replace({None: ""})
df_total = df_total[cols_order].replace({None: ""})

st.subheader("Tabela da carteira")

def color_pct(val):
    if pd.isna(val):
        return ""
    color = "green" if val > 0 else "red" if val < 0 else "black"
    return f"color: {color};"

styled_detail = (
    df_detail.style
    .map(
        color_pct,
        subset=["% Dia", "Tot Return", "Tot Return PMA", "P&L Dia", "P&L Dia(BRL)"]
    )
    .format({
        "Custódia": fmt_int,
        "PM": fmt_num,
        "PMA": fmt_num,
        "Fech Ant": fmt_num,
        "Vlr Ant": fmt_num,
        "Vlr Ant(BRL)": fmt_num,
        "P&L Dia": fmt_num,
        "P&L Dia(BRL)": fmt_num,
        "Cotação": fmt_num,
        "% Dia": fmt_pct,
        "Vlr Mercado": fmt_num,
        "Vlr Mercado(BRL)": fmt_num,
        "Tot Investido": fmt_num,
        "Tot Investido(BRL)": fmt_num,
        "Tot Ajust.Prov": fmt_num,
        "Tot Ajust.Prov(BRL)": fmt_num,
        "Tot Return": fmt_pct,
        "Tot Return PMA": fmt_pct,
    }, na_rep="")
)

visible_cols = [
    "Carteira",
    "Ativo",
    "Custódia",
    "PMA",
    "PM",
    "Cotação",
    "% Dia",
    "P&L Dia",
    "Vlr Mercado",
    "Tot Investido",
    "Tot Return",
    "Tot Return PMA",
    "Escopo",
    "Data/Hora",
]

st.dataframe(
    styled_detail,
    use_container_width=True,
    hide_index=True,
    height="content",
    row_height=24,
    column_order=visible_cols,
)

st.caption(
    "Dados de preços via Yahoo Finance / yfinance (com atraso), "
    "cálculos baseados no arquivo Excel enviado. Valores consolidados em BRL."
)

# ==========================
# Download da carteira detalhada
# ==========================

csv_export = pd.concat([df_detail, df_total], ignore_index=True)
csv_bytes = csv_export.to_csv(
    index=False,
    sep=";",
    decimal=","
).encode("utf-8-sig")

st.download_button(
    label="📥 Baixar carteira (CSV)",
    data=csv_bytes,
    file_name="carteira_detalhada.csv",
    mime="text/csv",
)
