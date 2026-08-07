"""
Valoración PROI — aplicación Streamlit.

Ejecutar con:  streamlit run app.py
"""
from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import streamlit as st

from engine import (
    COLUMNAS_ELEMENTOS,
    COMPLEJIDADES,
    ETAPAS,
    VARIACIONES,
    Parametros,
    calcular,
    resumen_agrupaciones,
    verificar_cuadre,
)

DATA_DIR = Path(__file__).parent / "data"

st.set_page_config(page_title="Valoración PROI", page_icon="🧮", layout="wide")


def init_state() -> None:
    if "params" not in st.session_state:
        st.session_state.params = Parametros.por_defecto(DATA_DIR)
    if "elementos" not in st.session_state:
        st.session_state.elementos = pd.read_csv(DATA_DIR / "elementos_ejemplo.csv")


init_state()
P: Parametros = st.session_state.params


with st.sidebar:
    st.header("⚙️ Parámetros globales")

    P.ajuste_manual = st.number_input(
        "Horas de ajuste manual", value=float(P.ajuste_manual), step=1.0, format="%.2f"
    )
    P.desc_ajuste_manual = st.text_input("Descripción del ajuste", value=P.desc_ajuste_manual)

    opciones_tamano = ["Automático"] + P.tamanos["Tamaño"].tolist()
    sel = st.selectbox(
        "Tamaño de proyecto",
        opciones_tamano,
        help="Determina qué bloque de la TABLA DE ETAPAS se aplica. "
        "En automático se deduce del total de horas base.",
    )
    P.tamano_forzado = None if sel == "Automático" else sel

    st.divider()
    st.caption("Los cambios en las tablas de parámetros se aplican al instante.")
    if st.button("💾 Guardar parámetros como valores por defecto", use_container_width=True):
        P.guardar(DATA_DIR)
        st.success("Parámetros guardados en /data")
    if st.button("↩️ Restaurar valores originales", use_container_width=True):
        st.session_state.params = Parametros.por_defecto(DATA_DIR)
        st.rerun()


res = calcular(st.session_state.elementos, P)

st.title("🧮 Valoración PROI")

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total proyecto (h)", f"{res.total_proyecto:,.2f}")
c2.metric("Total agrupaciones (h)", f"{res.total_etapas:,.2f}")
c3.metric("Ajuste complejidad (h)", f"{res.ajuste_complejidad:,.2f}", f"{res.factor_volumen:.0%}")
c4.metric("Ajuste manual (h)", f"{res.ajuste_manual:,.2f}")
c5.metric("Tamaño", res.tamano or "—")

for aviso in res.avisos:
    st.warning(aviso)

cuadre = verificar_cuadre(res)
if cuadre.ok:
    st.success(
        f"✅ Cuadre verificado: Resultado ({cuadre.total_resultado:,.2f} h) = "
        f"Etapas ({cuadre.total_etapas:,.2f} h)"
    )
else:
    st.error(
        f"⚠️ Descuadre entre Resultado ({cuadre.total_resultado:,.2f} h) y "
        f"Etapas ({cuadre.total_etapas:,.2f} h): diferencia de {cuadre.diferencia:,.2f} h"
    )

tab_datos, tab_res, tab_etapas, tab_param, tab_tetapas, tab_exp = st.tabs(
    [
        "📋 Datos de Entrada",
        "📊 Resultado",
        "🔩 Etapas",
        "⚖️ Parámetros",
        "📐 Tabla Etapas",
        "⬇️ Exportar",
    ]
)


with tab_datos:
    st.subheader("Elementos software")
    st.caption(
        "Añade filas con el botón **+** de la tabla. Marca con la casilla qué etapas "
        "aplican a cada elemento (Requisitos, Funcional, Técnico, Construcción, Pruebas, "
        "Implantación) — el resto de columnas de la derecha del editor."
    )

    editado = st.data_editor(
        st.session_state.elementos,
        num_rows="dynamic",
        use_container_width=True,
        height=420,
        column_config={
            "TipoElemento": st.column_config.SelectboxColumn(
                "Tipo de elemento", options=P.tipos_elemento, width="large", required=True
            ),
            "Complejidad": st.column_config.SelectboxColumn("Complejidad", options=COMPLEJIDADES),
            "Variación": st.column_config.SelectboxColumn("Variación", options=VARIACIONES),
            **{
                e: st.column_config.CheckboxColumn(e, default=False)
                for e in ETAPAS.values()
            },
            "Cantidad": st.column_config.NumberColumn("Cantidad", min_value=0, step=1, default=1),
        },
        key="editor_elementos",
    )
    st.session_state.elementos = editado

    st.divider()
    col_a, col_b = st.columns(2)
    with col_a:
        subido = st.file_uploader("Cargar elementos desde CSV / Excel", type=["csv", "xlsx", "xlsm"])
        if subido is not None:
            if subido.name.lower().endswith(".csv"):
                nuevos = pd.read_csv(subido)
            else:
                nuevos = pd.read_excel(subido)
            faltan = [c for c in COLUMNAS_ELEMENTOS if c not in nuevos.columns]
            if faltan:
                st.error("Faltan columnas: " + ", ".join(faltan))
            else:
                st.session_state.elementos = nuevos[COLUMNAS_ELEMENTOS]
                st.rerun()
    with col_b:
        st.download_button(
            "Descargar plantilla de elementos (CSV)",
            pd.DataFrame(columns=COLUMNAS_ELEMENTOS).to_csv(index=False).encode("utf-8-sig"),
            "plantilla_elementos.csv",
            "text/csv",
            use_container_width=True,
        )


with tab_res:
    st.caption(
        "Equivalente a la hoja RESULTADO del Excel: subtotal por grupo tecnológico, "
        "ajustes y detalle por elemento — calculado a partir de la misma tabla de "
        "detalle que la pestaña Etapas, así que ambas siempre cuadran."
    )
    izq, der = st.columns([1, 2])

    with izq:
        st.subheader("Resumen")
        resumen = pd.DataFrame(
            {
                "Concepto": [
                    "Subtotal agrupaciones",
                    "Ajuste complejidad",
                    "Ajuste manual",
                    "TOTAL PROYECTO",
                ],
                "Horas": [
                    res.total_etapas,
                    res.ajuste_complejidad,
                    res.ajuste_manual,
                    res.total_proyecto,
                ],
            }
        )
        st.dataframe(resumen, hide_index=True, use_container_width=True)

        st.subheader("Por grupo tecnológico")
        agr = resumen_agrupaciones(res)
        st.dataframe(agr, hide_index=True, use_container_width=True)
        if not agr.empty:
            st.bar_chart(agr.set_index("Grupo")["Horas"])

    with der:
        st.subheader("Detalle por elemento")
        cols = [
            "Nombre",
            "TipoElemento",
            "Grupo",
            "Complejidad",
            "Variación",
            "Etapas",
            "Cantidad",
            "HorasUnitarias",
            "HorasBase",
            "%Etapas",
            "Horas",
        ]
        if not res.detalle.empty:
            st.dataframe(
                res.detalle[cols].style.format(
                    {"%Etapas": "{:.0%}", "HorasBase": "{:.2f}", "Horas": "{:.2f}"}
                ),
                hide_index=True,
                use_container_width=True,
                height=520,
            )
        st.caption(
            f"Horas base totales: **{res.total_base:,.2f} h** → tamaño **{res.tamano}** "
            f"→ factor de ajuste por volumen **{res.factor_volumen:.0%}**"
        )


with tab_etapas:
    st.caption(
        "Equivalente a la hoja ETAPAS del Excel: reparto de las mismas horas de la "
        "pestaña Resultado, pero agrupadas por etapa en vez de por grupo tecnológico. "
        "El total de esta tabla siempre coincide con el de Resultado (ver aviso de cuadre arriba)."
    )
    st.subheader("Reparto de horas por etapa")
    if not res.por_etapa.empty:
        st.dataframe(res.por_etapa, hide_index=True, use_container_width=True)
        totales = res.por_etapa[list(ETAPAS.values())].sum().round(2)
        st.bar_chart(totales)

        total_check = round(float(res.por_etapa["Total"].sum()), 2)
        st.caption(
            f"Suma de todas las etapas y grupos: **{total_check:,.2f} h** "
            f"→ debe coincidir con el Subtotal agrupaciones de Resultado (**{res.total_etapas:,.2f} h**)."
        )
    else:
        st.info("Añade elementos en la pestaña Datos de Entrada para ver el reparto por etapa.")


with tab_param:
    st.caption(
        "Equivalente a la hoja PARÁMETROS del Excel: tabla de pesos (horas por unidad de "
        "elemento) y ajuste por volumen/complejidad."
    )

    st.subheader("Tabla de pesos (editable)")
    st.caption("Horas base por unidad de elemento, según variación y complejidad.")

    grupos = ["(todos)"] + P.grupos
    filtro = st.selectbox("Filtrar por grupo tecnológico", grupos)

    vista = P.pesos if filtro == "(todos)" else P.pesos[P.pesos["Grupo"] == filtro]
    editado_pesos = st.data_editor(
        vista,
        use_container_width=True,
        num_rows="dynamic",
        height=460,
        column_config={
            "Grupo": st.column_config.SelectboxColumn("Grupo", options=P.grupos),
            "TipoElemento": st.column_config.TextColumn("Tipo de elemento", width="large"),
        },
        key=f"editor_pesos_{filtro}",
    )
    if filtro == "(todos)":
        P.pesos = editado_pesos
    else:
        P.pesos = pd.concat([P.pesos[P.pesos["Grupo"] != filtro], editado_pesos], ignore_index=True)

    st.divider()
    st.subheader("Ajuste por volumen / complejidad")
    st.caption(
        "Búsqueda aproximada sobre el total de horas base. "
        "El factor se aplica sobre el subtotal de agrupaciones."
    )
    P.ajuste_volumen = st.data_editor(
        P.ajuste_volumen,
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "DesdeHoras": st.column_config.NumberColumn("Desde (h)", step=50),
            "Factor": st.column_config.NumberColumn("Factor", step=0.01, format="%.2f"),
        },
        key="editor_ajuste_vol",
    )
    st.info(
        f"Con {res.total_base:,.2f} h base se aplica un factor del "
        f"**{res.factor_volumen:.0%}** → {res.ajuste_complejidad:,.2f} h"
    )


with tab_tetapas:
    st.caption(
        "Equivalente a la hoja TABLA ETAPAS del Excel: porcentaje de esfuerzo de cada "
        "etapa, por tamaño de proyecto y grupo tecnológico. El tamaño (PEQUEÑO/MEDIANO/"
        "GRANDE) se elige automáticamente según las horas base totales — a diferencia "
        "del Excel original, donde ese bloque estaba fijado siempre a PEQUEÑO."
    )

    st.subheader("Porcentajes por etapa (editable)")
    st.caption("La suma de cada fila no tiene por qué ser 1 (en el modelo original es 0,93).")
    P.etapas = st.data_editor(
        P.etapas,
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            e: st.column_config.NumberColumn(e, min_value=0.0, max_value=1.0, step=0.01, format="%.2f")
            for e in ETAPAS.values()
        },
        key="editor_etapas",
    )
    sumas = P.etapas.copy()
    sumas["Suma"] = sumas[list(ETAPAS.values())].sum(axis=1).round(3)
    st.dataframe(sumas[["Tamaño", "Grupo", "Suma"]], hide_index=True, use_container_width=True)

    st.divider()
    st.subheader("Umbrales de tamaño de proyecto")
    st.caption(
        "Límite superior de horas base para cada tramo — determina qué bloque de la "
        "tabla de arriba se aplica al calcular."
    )
    P.tamanos = st.data_editor(
        P.tamanos,
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "LimiteSuperiorHoras": st.column_config.NumberColumn("Límite superior (h)", step=50)
        },
        key="editor_tamanos",
    )


with tab_exp:
    st.subheader("Exportar valoración")

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        st.session_state.elementos.to_excel(xw, sheet_name="DATOS ENTRADA", index=False)
        if not res.detalle.empty:
            res.detalle.to_excel(xw, sheet_name="RESULTADO", index=False)
            res.por_etapa.to_excel(xw, sheet_name="ETAPAS", index=False)
        pd.DataFrame(
            {
                "Concepto": [
                    "Total horas base",
                    "Tamaño proyecto",
                    "Subtotal agrupaciones",
                    "Factor volumen",
                    "Ajuste complejidad",
                    "Ajuste manual",
                    "TOTAL PROYECTO",
                ],
                "Valor": [
                    res.total_base,
                    res.tamano,
                    res.total_etapas,
                    res.factor_volumen,
                    res.ajuste_complejidad,
                    res.ajuste_manual,
                    res.total_proyecto,
                ],
            }
        ).to_excel(xw, sheet_name="RESUMEN", index=False)
        P.pesos.to_excel(xw, sheet_name="PARÁMETROS", index=False)
        P.etapas.to_excel(xw, sheet_name="TABLA ETAPAS", index=False)

    st.download_button(
        "⬇️ Descargar valoración en Excel",
        buf.getvalue(),
        "valoracion_proi.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    if not res.detalle.empty:
        st.download_button(
            "⬇️ Descargar detalle en CSV",
            res.detalle.to_csv(index=False).encode("utf-8-sig"),
            "detalle_valoracion.csv",
            "text/csv",
            use_container_width=True,
        )
