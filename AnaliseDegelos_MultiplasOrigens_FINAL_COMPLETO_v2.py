import streamlit as st
import pandas as pd
import altair as alt
from datetime import timedelta
import os

# ─── Configuração da Página ──────────────────────────────────────────────────
st.set_page_config(
    page_title="Degelo sob demanda Muffato Max João Bettega",
    layout="wide"
)

# ─── Paleta Plotter Racks ────────────────────────────────────────────────────
COLOR_PREV = "#112D4E"
COLOR_REAL = "#3F72AF"
COLOR_ECON = "#FCA311"
COLOR_BG   = "#E8E8E8"

# ─── Verificar se os arquivos existem ────────────────────────────────────────
ARQUIVOS = {
    "Câmara de Congelados": r"C:\Users\elielton.polityto\Desktop\Python\GitHub\Estudo_Curitiba_1\CamaraCongelados\Dados Ambiente\18-06 a 02-07\Dados_CamCong.xlsm.xlsx",
    "Step-in Master":       r"C:\Users\elielton.polityto\Desktop\Python\GitHub\Estudo_Curitiba_1\StepinMaster\Dados Ambiente\18-06 a 02-07\Dados_StepinMaster.xlsm",
    "Step-in Slave":        r"C:\Users\elielton.polityto\Desktop\Python\GitHub\Estudo_Curitiba_1\StepinSlave\Dados Ambiente\18-06 a 02-07\Dados_StepinSlave.xlsm",
}

# Verificar quais arquivos existem
ARQUIVOS_EXISTENTES = {}
for nome, caminho in ARQUIVOS.items():
    if os.path.exists(caminho):
        ARQUIVOS_EXISTENTES[nome] = caminho
    else:
        st.warning(f"Arquivo não encontrado: {caminho}")

if not ARQUIVOS_EXISTENTES:
    st.error("Nenhum arquivo de dados encontrado. Verifique os caminhos dos arquivos.")
    st.stop()

POTENCIAS = {
    "Câmara de Congelados": 19.26,
    "Step-in Master":        4.08,
    "Step-in Slave":         4.08,
}

CYCLES_DAY  = 4
CYCLE_HOURS = 45 / 60
SETPOINT    = -20.0

@st.cache_data
def load_all(paths):
    dfs = []
    for nome, caminho in paths.items():
        try:
            df = pd.read_excel(caminho, engine="openpyxl")
            
            # Verificar se o DataFrame não está vazio
            if df.empty:
                st.warning(f"Arquivo vazio: {nome}")
                continue
                
            # Encontrar coluna de data/hora
            dtcol = None
            for c in df.columns:
                if "Data" in str(c) or "Hora" in str(c):
                    dtcol = c
                    break
            
            if dtcol is None:
                st.warning(f"Coluna de data/hora não encontrada em: {nome}")
                continue
                
            df = df.rename(columns={dtcol: "DataHora"})
            df["DataHora"] = pd.to_datetime(df["DataHora"], dayfirst=True, errors="coerce")
            
            # Remover linhas com data inválida
            df = df.dropna(subset=["DataHora"])
            
            if df.empty:
                st.warning(f"Nenhuma data válida encontrada em: {nome}")
                continue
                
            df["Origem"] = nome
            dfs.append(df)
            
        except Exception as e:
            st.error(f"Erro ao carregar {nome}: {str(e)}")
            continue
    
    if not dfs:
        st.error("Nenhum arquivo foi carregado com sucesso.")
        st.stop()
        
    return pd.concat(dfs).set_index("DataHora").sort_index()

df_all = load_all(ARQUIVOS_EXISTENTES)

# Verificar se há dados válidos
if df_all.empty:
    st.error("Nenhum dado válido encontrado.")
    st.stop()

st.sidebar.header("Seleção de Módulo")
options = ["Eficiência Energética"] + list(ARQUIVOS_EXISTENTES.keys())
selecionados = st.sidebar.multiselect("Modo:", options, default=list(ARQUIVOS_EXISTENTES.keys()))
if "Eficiência Energética" in selecionados:
    selecionados = ["Eficiência Energética"]

mind, maxd = df_all.index.min().date(), df_all.index.max().date()
start_date, end_date = st.sidebar.date_input("Período", [mind, maxd], min_value=mind, max_value=maxd)
delta = st.sidebar.number_input("Delta tolerância (K)", 0.0, 10.0, 2.0, 0.1)

def calc_metrics(df_sel, pot_kw):
    df = df_sel.copy()
    
    # Verificar se a coluna "Defrost Status ()" existe
    if "Defrost Status ()" not in df.columns:
        st.warning("Coluna 'Defrost Status ()' não encontrada nos dados.")
        return 0, 0, 0, 0, 0, 0
        
    df["DefrostStatus"] = pd.to_numeric(df["Defrost Status ()"], errors="coerce").fillna(0)
    df["Event"] = df["DefrostStatus"].diff() == 1
    eventos = int(df["Event"].sum())
    dias = (end_date - start_date).days + 1
    ciclos = CYCLES_DAY * dias
    cons_prev = pot_kw * CYCLE_HOURS * ciclos
    cons_real = pot_kw * CYCLE_HOURS * eventos
    econ_kwh = cons_prev - cons_real
    econ_pct = econ_kwh / cons_prev * 100 if cons_prev else 0
    return cons_prev, cons_real, econ_kwh, econ_pct, ciclos, eventos

def barras_prev_real(dfc):
    base = dfc.melt(id_vars="Sistema", value_vars=["Previsto","Real"],
                    var_name="Categoria", value_name="Valor")
    bars = alt.Chart(base).mark_bar(size=35).encode(
        x=alt.X("Sistema:N", title=None),
        y=alt.Y("Valor:Q", title="Energia (kWh)"),
        color=alt.Color("Categoria:N", scale=alt.Scale(
            domain=["Previsto","Real"], range=[COLOR_PREV, COLOR_REAL])),
        xOffset="Categoria:N"
    )
    labels = alt.Chart(base).mark_text(dy=-5, fontSize=12).encode(
        x="Sistema:N", y="Valor:Q", detail="Categoria:N",
        text=alt.Text("Valor:Q", format=".0f")
    )
    return bars + labels

if selecionados == ["Eficiência Energética"]:
    # Total
    tot_prev = tot_real = tot_ciclos = tot_ev = 0
    for amb, pot in POTENCIAS.items():
        df_sel = df_all[df_all["Origem"]==amb].loc[start_date:end_date]
        prev, real, _, _, ciclos, ev = calc_metrics(df_sel, pot)
        tot_prev += prev
        tot_real += real
        tot_ciclos += ciclos
        tot_ev += ev
    tot_pct = (tot_prev - tot_real) / tot_prev * 100 if tot_prev else 0

    st.subheader("Total - Eficiência Energética")
    c1, c2 = st.columns([3,1])
    with c1:
        df_tot = pd.DataFrame([{"Sistema":"Total","Previsto":tot_prev,"Real":tot_real}])
        st.altair_chart(barras_prev_real(df_tot).properties(height=300).configure_view(strokeOpacity=0),
                        use_container_width=True)
    with c2:
        st.metric("Economia (%)", f"{tot_pct:.1f}%",
                  delta=f"Prev: {tot_prev:.1f} kWh  Real: {tot_real:.1f} kWh")
        st.markdown(
            f"Degelos agendados: **{tot_ciclos}**  •  Degelos realizados: **{tot_ev}**"
        )
    st.markdown("---")

    # Por Ambiente
    for amb, pot in POTENCIAS.items():
        prev, real, _, pct, ciclos, ev = calc_metrics(df_all[df_all["Origem"]==amb].loc[start_date:end_date], pot)
        st.subheader(amb)
        col1, col2 = st.columns([3,1])
        with col1:
            dfc = pd.DataFrame([{"Sistema":amb,"Previsto":prev,"Real":real}])
            st.altair_chart(barras_prev_real(dfc).properties(height=250).configure_view(strokeOpacity=0),
                            use_container_width=True)
        with col2:
            st.metric("Economia (%)", f"{pct:.1f}%",
                      delta=f"Prev: {prev:.1f} kWh  Real: {real:.1f} kWh")
            st.markdown(
                f"Degelos agendados: **{ciclos}**  •  Degelos realizados: **{ev}**"
            )
        st.markdown("---")

    st.stop()

# ─── Modo Análise por Ambiente ────────────────────────────────────────────────
for origem in selecionados:
    pot = POTENCIAS[origem]
    df_sel = df_all[df_all["Origem"]==origem].loc[start_date:end_date]

    # Verificar se há dados para este ambiente
    if df_sel.empty:
        st.warning(f"Nenhum dado encontrado para {origem} no período selecionado.")
        continue

    st.header(f"Análise – {origem}")

    # Verificar se as colunas necessárias existem
    required_cols = ["Ambient Temperature (°C)", "Defrost Status ()"]
    missing_cols = [col for col in required_cols if col not in df_sel.columns]
    if missing_cols:
        st.error(f"Colunas necessárias não encontradas em {origem}: {missing_cols}")
        continue

    # Temperatura & Eventos de Degelo
    df_sel["Ambient Temperature (°C)"] = pd.to_numeric(
        df_sel["Ambient Temperature (°C)"], errors="coerce"
    ).fillna(method="ffill")
    df_sel["DefrostStatus"] = pd.to_numeric(
        df_sel["Defrost Status ()"], errors="coerce"
    ).fillna(0)
    df_sel["Event"] = df_sel["DefrostStatus"].diff() == 1
    events = df_sel.index[df_sel["Event"]]

    # Verificar se há dados válidos para o gráfico
    if df_sel["Ambient Temperature (°C)"].isna().all():
        st.warning(f"Nenhum dado de temperatura válido encontrado para {origem}")
    else:
        rects = pd.DataFrame({
            "start": events,
            "end":   events + pd.Timedelta(minutes=15),
            "y1":    df_sel["Ambient Temperature (°C)"].min(),
            "y2":    df_sel["Ambient Temperature (°C)"].max()
        })
        
        # Verificar se há eventos para mostrar
        if not events.empty:
            overlay = alt.Chart(rects).mark_rect(color=COLOR_ECON, opacity=0.3).encode(
                x="start:T", x2="end:T", y="y1:Q", y2="y2:Q"
            )
        else:
            overlay = None
            
        line = alt.Chart(df_sel.reset_index()).mark_line(interpolate="monotone").encode(
            x="DataHora:T",
            y=alt.Y("Ambient Temperature (°C):Q", title="Temperatura (°C)")
        )
        
        st.subheader("Temperatura e Eventos de Degelo")
        if overlay is not None:
            st.altair_chart((overlay + line).properties(height=350).interactive(),
                            use_container_width=True)
        else:
            st.altair_chart(line.properties(height=350).interactive(),
                            use_container_width=True)

    # Performance de Temperatura
    recovery = pd.Series(False, index=df_sel.index)
    for t0 in events:
        recovery |= (df_sel.index > t0 + timedelta(minutes=45)) & \
                    (df_sel.index <= t0 + timedelta(minutes=75))

    periods = {
        "Operação (08–21h)": ((df_sel.index.hour >= 8) & (df_sel.index.hour < 21) & (df_sel.index.weekday < 5)),
        "Fora (21–08h)":     (((df_sel.index.hour >= 21) | (df_sel.index.hour < 8)) & (df_sel.index.weekday < 5)),
        "Fim de Semana":     (df_sel.index.weekday >= 5)
    }
    perf_list = []
    for nome_p, mask in periods.items():
        valid = mask & (~recovery)
        s = df_sel.loc[valid, "Ambient Temperature (°C)"]
        
        # Verificar se há dados válidos para este período
        if s.empty or s.isna().all():
            perf_list.append({
                "Período": nome_p,
                "Média (°C)": "N/A",
                "Performance (%)": "N/A"
            })
        else:
            perf_pct = ((s - SETPOINT).abs() <= delta).mean() * 100
            perf_list.append({
                "Período": nome_p,
                "Média (°C)": round(s.mean(), 1),
                "Performance (%)": round(perf_pct, 1)
            })

    st.subheader("Performance de Temperatura da Câmara")
    st.table(pd.DataFrame(perf_list).set_index("Período"))
    st.markdown("---")


    # --- Consumo Real Medido da Câmara de Congelados ---

CAMINHO_MEDIDOR = r"C:\Users\elielton.polityto\Desktop\Relatorio_Muffato\AIDA\Relatorio_Muffato\ConsumoCamCong\Consumo_Cam_Cong.xlsx"

st.markdown("---")
st.header("Consumo Total Medido — Câmara de Congelados")

if os.path.exists(CAMINHO_MEDIDOR):
    try:
        df_med = pd.read_excel(CAMINHO_MEDIDOR)

        # Verificar se o arquivo não está vazio
        if df_med.empty:
            st.warning("Arquivo do medidor está vazio.")
        else:
            # Ajuste para datas e vírgula decimal, se necessário
            df_med.columns = [col.strip() for col in df_med.columns]
            if "Data" in df_med.columns:
                df_med["Data"] = pd.to_datetime(df_med["Data"], dayfirst=True, errors="coerce")
                # Remover linhas com data inválida
                df_med = df_med.dropna(subset=["Data"])
            else:
                st.error("Coluna de data não encontrada no arquivo do medidor.")
                df_med = None
                
            if df_med is not None and not df_med.empty:
                # Corrige vírgula decimal
                for col in df_med.columns:
                    if df_med[col].dtype == object:
                        df_med[col] = df_med[col].str.replace(",", ".").astype(float, errors="ignore")

                # Filtra intervalo de datas igual ao dashboard
                data_min = df_med["Data"].min().date()
                data_max = df_med["Data"].max().date()
                data_ini = max(data_min, start_date)
                data_fim = min(data_max, end_date)
                df_med_periodo = df_med[(df_med["Data"].dt.date >= data_ini) & (df_med["Data"].dt.date <= data_fim)].copy()

                if not df_med_periodo.empty:
                    # Verificar se a coluna de potência existe
                    if "Total System Active Power (kW)" in df_med_periodo.columns:
                        # Gráfico de linha da potência ativa (kW)
                        chart_med = alt.Chart(df_med_periodo).mark_line(
                            color=COLOR_PREV
                        ).encode(
                            x=alt.X("Data:T", title="Data/Hora"),
                            y=alt.Y("Total System Active Power (kW):Q", title="Potência Ativa (kW)")
                        ).properties(height=300)
                        st.altair_chart(chart_med, use_container_width=True)

                        # Cálculo do kWh total consumido no período
                        # Considere que cada linha é 1 minuto => energia = potência * (1/60) h
                        total_kwh = (df_med_periodo["Total System Active Power (kW)"].sum() * (1/60))

                        st.markdown(
                            f"**Total de energia consumida no período:** <span style='color:{COLOR_PREV}; font-size:1.3em'><b>{total_kwh:.1f} kWh</b></span>",
                            unsafe_allow_html=True
                        )
                    else:
                        st.warning("Coluna 'Total System Active Power (kW)' não encontrada no arquivo do medidor.")
                else:
                    st.warning("Nenhum dado encontrado no período selecionado para o medidor.")
    except Exception as e:
        st.error(f"Erro ao processar arquivo do medidor: {str(e)}")

else:
    st.warning(f"Arquivo do medidor não encontrado em: {CAMINHO_MEDIDOR}")