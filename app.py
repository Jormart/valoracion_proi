"""
Valoración PROI — aplicación Streamlit.

Ejecutar con:  streamlit run app.py
"""
from __future__ import annotations

import io
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from engine import (
    COLUMNAS_ELEMENTOS,
    COMPLEJIDADES,
    ETAPAS,
    VARIACIONES,
    Parametros,
    calcular,
    calcular_capacidad,
    construir_timeline,
    resumen_agrupaciones,
    resumen_por_clave,
    resumen_por_equipo,
    verificar_cuadre,
)

DATA_DIR = Path(__file__).parent / "data"

# Colores categóricos (orden fijo, paleta validada) para las 5 etapas del timeline.
COLOR_ETAPA = {
    "Funcional": "#2a78d6",
    "Técnico": "#eb6834",
    "Construcción": "#1baf7a",
    "Pruebas": "#eda100",
    "Implantación": "#e87ba4",
}
COLOR_HOLGURA = "#2a78d6"
COLOR_DESBORDAMIENTO = "#e34948"

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
    st.caption("📅 Capacidad y jornada (usadas en Timeline y Balanceo de carga)")
    P.horas_semana = st.number_input("Horas/semana por FTE", value=float(P.horas_semana), step=0.5)
    P.buffer_imprevistos = st.number_input(
        "Buffer imprevistos",
        value=float(P.buffer_imprevistos),
        step=0.05,
        min_value=0.0,
        max_value=0.9,
        format="%.2f",
        help="Fracción de la jornada reservada para incidencias/formación, no planificable.",
    )
    P.horas_dia = st.number_input("Horas/día", value=float(P.horas_dia), step=0.5)

    st.divider()
    st.caption("Los cambios en las tablas de parámetros se aplican al instante.")
    if st.button("💾 Guardar parámetros como valores por defecto", width="stretch"):
        P.guardar(DATA_DIR)
        st.success("Parámetros guardados en /data")
    if st.button("↩️ Restaurar valores originales", width="stretch"):
        st.session_state.params = Parametros.por_defecto(DATA_DIR)
        st.rerun()


# --- Cabecera (título, métricas, avisos) ---------------------------------------------
# Se reserva aquí (arriba del todo) pero se rellena MÁS ABAJO, después de procesar la
# pestaña "Datos de Entrada". Así cualquier edición en esa pestaña (incl. los checkboxes
# de etapa) se refleja en los totales en la MISMA interacción, sin tener que repetir el
# click: si calculásemos antes de leer la tabla editada, la cabecera y el resto de
# pestañas mostrarían siempre el estado anterior al último cambio.
cabecera = st.container()

tab_datos, tab_res, tab_etapas, tab_param, tab_tetapas, tab_timeline, tab_balanceo, tab_exp = st.tabs(
    [
        "📋 Datos de Entrada",
        "📊 Resultado",
        "🔩 Etapas",
        "⚖️ Parámetros",
        "📐 Tabla Etapas",
        "🗓️ Timeline",
        "⚖️ Balanceo de carga",
        "⬇️ Exportar",
    ]
)


with tab_datos:
    st.subheader("Historias de usuario (Jira)")
    st.caption(
        "Cada fila es una historia de usuario / ticket de Jira. Marca con la casilla qué "
        "etapas aplican (Funcional, Técnico, Construcción, Pruebas, Implantación) y asigna "
        "un Product Team. Para añadir tareas extra de testing (Análisis, Regresión, "
        "Incidencias, Defects) ligadas a una historia, crea una fila nueva con el mismo "
        "**ClaveAgrupación** que la historia principal — verás el total conjunto en la "
        "pestaña Resultado."
    )

    editado = st.data_editor(
        st.session_state.elementos,
        num_rows="dynamic",
        width="stretch",
        height=420,
        column_config={
            "TipoElemento": st.column_config.SelectboxColumn(
                "Tipo de elemento", options=P.tipos_elemento, width="large", required=True
            ),
            "Complejidad": st.column_config.SelectboxColumn("Complejidad", options=COMPLEJIDADES),
            "Variación": st.column_config.SelectboxColumn("Variación", options=VARIACIONES),
            "ProductTeam": st.column_config.SelectboxColumn("Product Team", options=P.equipos_lista),
            **{e: st.column_config.CheckboxColumn(e, default=False) for e in ETAPAS.values()},
            "Cantidad": st.column_config.NumberColumn("Cantidad", min_value=0, step=1, default=1),
        },
        key="editor_elementos",
    )
    st.session_state.elementos = editado

    st.divider()
    col_a, col_b = st.columns(2)
    with col_a:
        subido = st.file_uploader("Cargar historias desde CSV / Excel", type=["csv", "xlsx", "xlsm"])
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
            "Descargar plantilla de historias (CSV)",
            pd.DataFrame(columns=COLUMNAS_ELEMENTOS).to_csv(index=False).encode("utf-8-sig"),
            "plantilla_elementos.csv",
            "text/csv",
            width="stretch",
        )


# --- Ahora sí: calcular con los datos ya actualizados por la pestaña de arriba ---------
res = calcular(st.session_state.elementos, P)
cuadre = verificar_cuadre(res)

with cabecera:
    st.title("🧮 Valoración PROI")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total proyecto (h)", f"{res.total_proyecto:,.2f}")
    c2.metric("Total agrupaciones (h)", f"{res.total_etapas:,.2f}")
    c3.metric("Ajuste complejidad (h)", f"{res.ajuste_complejidad:,.2f}", f"{res.factor_volumen:.0%}")
    c4.metric("Ajuste manual (h)", f"{res.ajuste_manual:,.2f}")
    c5.metric("Tamaño", res.tamano or "—")

    for aviso in res.avisos:
        st.warning(aviso)

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


with tab_res:
    st.caption(
        "Subtotal por grupo tecnológico, por Product Team y por historia — calculado a "
        "partir de la misma tabla de detalle que la pestaña Etapas, así que ambas siempre cuadran."
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
        st.dataframe(resumen, hide_index=True, width="stretch")

        st.subheader("Por grupo tecnológico")
        agr = resumen_agrupaciones(res)
        st.dataframe(agr, hide_index=True, width="stretch")
        if not agr.empty:
            st.bar_chart(agr.set_index("Grupo")["Horas"])

        st.subheader("Por Product Team")
        por_equipo = resumen_por_equipo(res)
        if not por_equipo.empty:
            st.dataframe(por_equipo, hide_index=True, width="stretch")
        else:
            st.info("Asigna un Product Team a las historias para ver este desglose.")

        st.subheader("Por historia (ClaveAgrupación)")
        st.caption("Historias con tareas extra de testing asociadas — total conjunto.")
        por_clave = resumen_por_clave(res)
        if not por_clave.empty:
            st.dataframe(por_clave, hide_index=True, width="stretch")
        else:
            st.info("Ninguna historia tiene tareas extra ligadas por ClaveAgrupación todavía.")

    with der:
        st.subheader("Detalle por historia")
        cols = [
            "Nombre",
            "TipoElemento",
            "Grupo",
            "ProductTeam",
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
                width="stretch",
                height=520,
            )
        st.caption(
            f"Horas base totales: **{res.total_base:,.2f} h** → tamaño **{res.tamano}** "
            f"→ factor de ajuste por volumen **{res.factor_volumen:.0%}**"
        )


with tab_etapas:
    st.caption(
        "Reparto de las mismas horas de la pestaña Resultado, pero agrupadas por etapa en "
        "vez de por grupo tecnológico. El total de esta tabla siempre coincide con el de "
        "Resultado (ver aviso de cuadre arriba)."
    )
    st.subheader("Reparto de horas por etapa")
    if not res.por_etapa.empty:
        st.dataframe(res.por_etapa, hide_index=True, width="stretch")
        totales = res.por_etapa[list(ETAPAS.values())].sum().round(2)
        st.bar_chart(totales)

        total_check = round(float(res.por_etapa["Total"].sum()), 2)
        st.caption(
            f"Suma de todas las etapas y grupos: **{total_check:,.2f} h** "
            f"→ debe coincidir con el Subtotal agrupaciones de Resultado (**{res.total_etapas:,.2f} h**)."
        )
    else:
        st.info("Añade historias en la pestaña Datos de Entrada para ver el reparto por etapa.")


with tab_param:
    st.caption(
        "Tabla de pesos (horas por unidad de tarea, incluye Testing y las tareas extra de "
        "Incidencias/Defects) y ajuste por volumen/complejidad."
    )

    st.subheader("Tabla de pesos (editable)")
    st.caption(
        "Horas base por unidad de tarea, según variación y complejidad. Las tareas de "
        "Testing parten de un peso ×2 sobre su equivalente de Host como punto de partida "
        "— ajústalo aquí si tienes cifras reales."
    )

    grupos = ["(todos)"] + P.grupos
    filtro = st.selectbox("Filtrar por grupo tecnológico", grupos)

    vista = P.pesos if filtro == "(todos)" else P.pesos[P.pesos["Grupo"] == filtro]
    editado_pesos = st.data_editor(
        vista,
        width="stretch",
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
        width="stretch",
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
        "Porcentaje de esfuerzo de cada etapa, por tamaño de proyecto y grupo tecnológico "
        "(Host, Java, Testing). El tamaño (PEQUEÑO/MEDIANO/GRANDE) se elige automáticamente "
        "según las horas base totales."
    )

    st.subheader("Porcentajes por etapa (editable)")
    st.caption(
        "Los porcentajes de Testing parten como copia de los de Host (no hay cifras propias "
        "todavía) — ajústalos aquí si son distintos. La suma de cada fila no tiene por qué "
        "ser 1."
    )
    P.etapas = st.data_editor(
        P.etapas,
        width="stretch",
        num_rows="dynamic",
        column_config={
            e: st.column_config.NumberColumn(e, min_value=0.0, max_value=1.0, step=0.01, format="%.2f")
            for e in ETAPAS.values()
        },
        key="editor_etapas",
    )
    sumas = P.etapas.copy()
    sumas["Suma"] = sumas[list(ETAPAS.values())].sum(axis=1).round(3)
    st.dataframe(sumas[["Tamaño", "Grupo", "Suma"]], hide_index=True, width="stretch")

    st.divider()
    st.subheader("Umbrales de tamaño de proyecto")
    st.caption(
        "Límite superior de horas base para cada tramo — determina qué bloque de la "
        "tabla de arriba se aplica al calcular."
    )
    P.tamanos = st.data_editor(
        P.tamanos,
        width="stretch",
        num_rows="dynamic",
        column_config={
            "LimiteSuperiorHoras": st.column_config.NumberColumn("Límite superior (h)", step=50)
        },
        key="editor_tamanos",
    )


with tab_timeline:
    st.caption(
        "Timeline relativo: cada historia es una barra con sus etapas activas encadenadas "
        "en secuencia (día 1, día 2...), a razón de las horas/día configuradas en la "
        "barra lateral. No representa fechas de calendario ni la contención de capacidad "
        "entre historias de un mismo equipo — para eso, ver Balanceo de carga."
    )

    timeline = construir_timeline(res, P)
    if timeline.empty:
        st.info("Añade historias en Datos de Entrada para ver el timeline.")
    else:
        equipos_disponibles = ["(todos)"] + sorted(timeline["ProductTeam"].dropna().unique().tolist())
        filtro_equipo = st.selectbox("Filtrar por Product Team", equipos_disponibles, key="filtro_timeline")
        vista_tl = timeline if filtro_equipo == "(todos)" else timeline[timeline["ProductTeam"] == filtro_equipo]

        orden_etiquetas = (
            vista_tl.sort_values(["ProductTeam", "Etiqueta"])["Etiqueta"].drop_duplicates().tolist()
        )

        chart = (
            alt.Chart(vista_tl)
            .mark_bar(height=14, cornerRadius=3)
            .encode(
                x=alt.X("Inicio:Q", title="Día"),
                x2="Fin:Q",
                y=alt.Y("Etiqueta:N", title=None, sort=orden_etiquetas),
                color=alt.Color(
                    "Etapa:N",
                    title="Etapa",
                    scale=alt.Scale(domain=list(COLOR_ETAPA.keys()), range=list(COLOR_ETAPA.values())),
                ),
                tooltip=[
                    alt.Tooltip("Etiqueta:N", title="Historia"),
                    alt.Tooltip("ProductTeam:N", title="Product Team"),
                    alt.Tooltip("Etapa:N"),
                    alt.Tooltip("Inicio:Q", format=".2f", title="Día inicio"),
                    alt.Tooltip("Fin:Q", format=".2f", title="Día fin"),
                    alt.Tooltip("Horas:Q", format=".2f"),
                ],
            )
            .properties(height=max(220, 26 * len(orden_etiquetas)))
        )
        st.altair_chart(chart, width="stretch")
        st.dataframe(vista_tl, hide_index=True, width="stretch")


with tab_balanceo:
    st.caption(
        "Compara las horas esperadas de cada Product Team (según las historias que tiene "
        "asignadas) contra su capacidad real, calculada a partir de sus FTEs fijos y del "
        "buffer de imprevistos. Holgura negativa = desbordamiento."
    )

    st.subheader("Product Teams")
    P.equipos = st.data_editor(
        P.equipos,
        width="stretch",
        num_rows="dynamic",
        key="editor_equipos",
    )

    st.subheader("FTEs por Product Team y grupo tecnológico (editable)")
    P.capacidad = st.data_editor(
        P.capacidad,
        width="stretch",
        num_rows="dynamic",
        column_config={
            "ProductTeam": st.column_config.SelectboxColumn("Product Team", options=P.equipos_lista),
            "Grupo": st.column_config.SelectboxColumn("Grupo", options=P.grupos),
            "FTE": st.column_config.NumberColumn("FTE", min_value=0.0, step=0.5),
        },
        key="editor_capacidad",
    )

    st.divider()
    semanas = st.number_input(
        "Horizonte (semanas)",
        value=4.0,
        min_value=1.0,
        step=1.0,
        help="Periodo sobre el que se compara el trabajo esperado contra la capacidad disponible.",
    )

    cap = calcular_capacidad(res, P, semanas)
    st.subheader(f"Holgura / desbordamiento a {semanas:.0f} semanas")

    if not cap.empty:
        cap_chart = cap.copy()
        cap_chart["Equipo · Grupo"] = cap_chart["ProductTeam"] + " · " + cap_chart["Grupo"]
        orden = cap_chart.sort_values("Holgura")["Equipo · Grupo"].tolist()
        holgura_chart = (
            alt.Chart(cap_chart)
            .mark_bar(cornerRadius=3)
            .encode(
                x=alt.X("Holgura:Q", title="Holgura (h) — negativo = desbordamiento"),
                y=alt.Y("Equipo · Grupo:N", title=None, sort=orden),
                color=alt.condition(
                    alt.datum.Holgura < 0, alt.value(COLOR_DESBORDAMIENTO), alt.value(COLOR_HOLGURA)
                ),
                tooltip=[
                    alt.Tooltip("ProductTeam:N", title="Product Team"),
                    alt.Tooltip("Grupo:N"),
                    alt.Tooltip("FTE:Q", format=".1f"),
                    alt.Tooltip("HorasEsperadas:Q", format=".2f", title="Horas esperadas"),
                    alt.Tooltip("HorasDisponibles:Q", format=".2f", title="Horas disponibles"),
                    alt.Tooltip("Holgura:Q", format=".2f"),
                ],
            )
            .properties(height=max(180, 28 * len(orden)))
        )
        st.altair_chart(holgura_chart, width="stretch")

        def _resaltar_holgura(v: float) -> str:
            return f"background-color: {'#fde8e8' if v < 0 else '#e6f4ea'}"

        st.dataframe(
            cap.style.map(_resaltar_holgura, subset=["Holgura"]).format(
                {"FTE": "{:.1f}", "HorasEsperadas": "{:.2f}", "HorasDisponibles": "{:.2f}", "Holgura": "{:.2f}"}
            ),
            hide_index=True,
            width="stretch",
        )

        desbordados = cap[cap["Holgura"] < 0]
        if not desbordados.empty:
            for _, fila in desbordados.iterrows():
                st.error(
                    f"⚠️ {fila['ProductTeam']} / {fila['Grupo']}: desbordamiento de "
                    f"{abs(fila['Holgura']):,.2f} h en {semanas:.0f} semanas "
                    f"({fila['HorasEsperadas']:,.2f} h esperadas vs {fila['HorasDisponibles']:,.2f} h disponibles)."
                )
        else:
            st.success("✅ Ningún Product Team está desbordado en este horizonte.")
    else:
        st.info("Define al menos un Product Team y su capacidad para ver el balanceo.")


with tab_exp:
    st.subheader("Exportar valoración")

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        st.session_state.elementos.to_excel(xw, sheet_name="DATOS ENTRADA", index=False)
        if not res.detalle.empty:
            res.detalle.to_excel(xw, sheet_name="RESULTADO", index=False)
            res.por_etapa.to_excel(xw, sheet_name="ETAPAS", index=False)
            resumen_por_equipo(res).to_excel(xw, sheet_name="POR PRODUCT TEAM", index=False)
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
        calcular_capacidad(res, P, semanas).to_excel(xw, sheet_name="CAPACIDAD", index=False)

    st.download_button(
        "⬇️ Descargar valoración en Excel",
        buf.getvalue(),
        "valoracion_proi.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
    )

    if not res.detalle.empty:
        st.download_button(
            "⬇️ Descargar detalle en CSV",
            res.detalle.to_csv(index=False).encode("utf-8-sig"),
            "detalle_valoracion.csv",
            "text/csv",
            width="stretch",
        )
