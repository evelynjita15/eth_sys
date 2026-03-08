import streamlit as st
import biosteam as bst
import thermosteam as tmo
import pandas as pd
import google.generativeai as genai
import os
from PIL import Image

# =================================================================
# 1. CONFIGURACIÓN DE IA (GEMINI)
# =================================================================
def configurar_gemini(prompt_data):
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        contexto_tutor = f"""
        Actúa como un profesor experto en Ingeniería Química. 
        Analiza los siguientes datos de una simulación de BioSTEAM y explica 
        los fenómenos termodinámicos, la eficiencia energética y sugiere mejoras 
        como si estuvieras en una asesoría académica. No repitas las tablas, 
        enfócate en el 'por qué' de los resultados.
        
        DATOS DE SIMULACIÓN:
        {prompt_data}
        """
        response = model.generate_content(contexto_tutor)
        return response.text
    except Exception as e:
        return f"No se pudo conectar con el tutor IA. Verifica la API Key. Error: {e}"

# =================================================================
# 2. LÓGICA DE SIMULACIÓN ENCAPSULADA
# =================================================================
def ejecutar_simulacion(f_agua, f_etanol, t_entrada, p_flash):
    # LIMPIEZA CRÍTICA: Evita el error "Duplicate ID" al mover sliders
    bst.main_flowsheet.clear()
    bst.settings.set_thermo(tmo.Chemicals(["Water", "Ethanol"]))

    # Corrientes
    mosto = bst.Stream("1-MOSTO", Water=f_agua, Ethanol=f_etanol, units="kg/hr", 
                       T=t_entrada, P=101325)
    
    vinazas_retorno = bst.Stream("Vinazas-Retorno", Water=200, Ethanol=0, units="kg/hr", 
                                 T=95+273.15, P=300000)

    # Equipos
    P100 = bst.Pump("P100", ins=mosto, P=4*101325)
    
    W210 = bst.HXprocess("W210", ins=(P100-0, vinazas_retorno), 
                         outs=("3-Mosto-Pre", "Drenaje"), phase0="l", phase1="l")
    W210.outs[0].T = 85 + 273.15 # Especificación de diseño

    W220 = bst.HXutility("W220", ins=W210-0, outs="Mezcla", T=92+273.15)
    
    V100 = bst.IsenthalpicValve("V100", ins=W220-0, outs="Mezcla-Bifasica", P=p_flash)
    
    # Manejo correcto de Presión en el Flash
    V1 = bst.Flash("V1", ins=V100-0, outs=("Vapor_caliente", "Vinazas"), P=p_flash, Q=0)

    W310 = bst.HXutility("W310", ins=V1-0, outs="Producto_Final", T=25+273.15)
    
    P200 = bst.Pump("P200", ins=V1-1, outs=vinazas_retorno, P=3*101325)

    # Sistema
    sys = bst.System("planta_etanol", path=(P100, W210, W220, V100, V1, W310, P200))
    sys.simulate()
    
    return sys

# =================================================================
# 3. EXTRACCIÓN DE DATOS (REPORTE)
# =================================================================
def obtener_reportes(sistema):
    # Materia
    datos_mat = []
    for s in sistema.streams:
        if s.F_mass > 0:
            datos_mat.append({
                "Corriente": s.ID,
                "Temp (°C)": round(s.T - 273.15, 2),
                "Flujo (kg/h)": round(s.F_mass, 2),
                "% Etanol": f"{(s.imass['Ethanol']/s.F_mass)*100:.2f}%" if s.F_mass > 0 else "0%"
            })
    df_mat = pd.DataFrame(datos_mat)

    # Energía (Evitando error .duty en tanques)
    datos_en = []
    for u in sistema.units:
        duty_kw = 0.0
        # Sumar calor de todas las utilidades de calor del equipo
        if hasattr(u, 'heat_utilities'):
            duty_kw = sum([hu.duty for hu in u.heat_utilities]) / 3600
        
        if abs(duty_kw) > 0.001 or (hasattr(u, 'power_utility') and u.power_utility.rate > 0):
            datos_en.append({
                "Equipo": u.ID,
                "Calor (kW)": round(duty_kw, 2),
                "Potencia (kW)": round(u.power_utility.rate, 2) if u.power_utility else 0
            })
    df_en = pd.DataFrame(datos_en)
    
    return df_mat, df_en

# =================================================================
# 4. INTERFAZ DE USUARIO (STREAMLIT)
# =================================================================
st.set_page_config(page_title="BioSTEAM Interactive App", layout="wide")

st.sidebar.header("⚙️ Parámetros de Simulación")
f_w = st.sidebar.slider("Flujo Agua (kg/h)", 500, 1500, 900)
f_e = st.sidebar.slider("Flujo Etanol (kg/h)", 50, 500, 100)
t_in_c = st.sidebar.slider("Temperatura Entrada (°C)", 10, 50, 25)
p_f = st.sidebar.slider("Presión Flash (bar)", 0.5, 2.0, 1.0) * 100000

st.title("🏭 Simulador Interactivo de Separación de Etanol")
st.markdown("---")

if st.button("🚀 Ejecutar Simulación"):
    with st.spinner("Simulando proceso y consultando al tutor..."):
        # Ejecución
        sistema = ejecutar_simulacion(f_w, f_e, t_in_c + 273.15, p_f)
        df_m, df_e_table = obtener_reportes(sistema)

        # Columnas para Tablas
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("📋 Balance de Materia")
            st.dataframe(df_m, use_container_width=True)
        
        with col2:
            st.subheader("⚡ Balance de Energía")
            st.dataframe(df_e_table, use_container_width=True)

        # Diagrama (DFP)
        st.subheader("🖼️ Diagrama de Flujo del Proceso")
        try:
            sistema.diagram(file="diagrama", format="png")
            st.image("diagrama.png")
        except:
            st.info("Nota: Para ver el diagrama en la web, asegúrate de que el servidor tenga instalado Graphviz.")

        # Tutor IA
        st.markdown("---")
        st.subheader("🎓 Asesoría del Tutor IA (Gemini)")
        data_string = f"Materia: {df_m.to_dict()} \nEnergía: {df_e_table.to_dict()}"
        consejo = configurar_gemini(data_string)
        st.info(consejo)
