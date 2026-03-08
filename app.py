import streamlit as st
import biosteam as bst  # <-- El módulo se importa en minúsculas
import thermosteam as tmo
import pandas as pd
import google.generativeai as genai
import os

# Configuración de página
st.set_page_config(page_title="BioSTEAM Hub", layout="wide")

# =================================================================
# FUNCIÓN DE SIMULACIÓN (CORREGIDA)
# =================================================================
def correr_simulacion(f_agua, f_etanol, p_flash):
    # 1. Limpiar el historial para evitar "Duplicate ID"
    bst.main_flowsheet.clear()
    
    # 2. Configuración termodinámica
    chemicals = tmo.Chemicals(["Water", "Ethanol"])
    bst.settings.set_thermo(chemicals)

    # 3. Creación de corrientes y equipos
    mosto = bst.Stream("mosto", Water=f_agua, Ethanol=f_etanol, units="kg/hr", T=298.15)
    
    # Definimos una unidad Flash para la separación
    # Usamos heat_utilities para evitar errores de .duty
    F1 = bst.Flash("F1", ins=mosto, outs=("vapor", "liquido"), P=p_flash, Q=0)
    
    # Simulación del sistema
    sys = bst.System("sys_etanol", path=(F1,))
    sys.simulate()
    
    return sys

# =================================================================
# INTERFAZ DE USUARIO
# =================================================================
st.title("🧪 Simulador BioSTEAM Online")

with st.sidebar:
    st.header("Parámetros")
    f_w = st.slider("Flujo Agua", 500, 1500, 900)
    f_e = st.slider("Flujo Etanol", 50, 500, 100)
    presion = st.slider("Presión Flash (Pa)", 50000, 150000, 101325)

if st.button("Ejecutar BioSTEAM"):
    try:
        resultado = correr_simulacion(f_w, f_e, presion)
        st.success("Simulación exitosa")
        
        # Mostrar resultados simples
        st.subheader("Resultados de Corrientes")
        st.write(resultado.table()) # Tabla automática de BioSTEAM
        
        # Generar Diagrama
        resultado.diagram(file="proceso", format="png")
        st.image("proceso.png")
        
    except Exception as e:
        st.error(f"Error en la simulación: {e}")
