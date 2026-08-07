"""
Motor de cálculo de la valoración PROI.

Réplica en Python de la lógica del libro Valoracion_PROI_v0.xlsm:

  1. Horas base del elemento  = PESOS[tipo][variación_complejidad] * cantidad
  2. Horas por etapa          = ROUND(horas_base * %etapa_seleccionada, 2), por cada
                                una de las 6 etapas (TABLA ETAPAS: tamaño x grupo)
  3. Horas del elemento       = suma de sus 6 columnas de etapa ya redondeadas
  4. Ajuste por complejidad   = ROUND(factor_volumen * total_etapas, 2)
  5. Total proyecto           = total_etapas + ajuste_complejidad + ajuste_manual

El detalle (`Resultado.detalle`) es la única fuente de verdad: tanto la vista
"Resultado" (agrupada por Grupo tecnológico) como la vista "Etapas" (agrupada
por etapa) se calculan a partir de las mismas filas ya redondeadas, así que
sus totales siempre cuadran entre sí — a diferencia del libro Excel original,
donde RESULTADO y ETAPAS mantenían copias independientes con distinto orden
de redondeo y podían divergir (126.27 vs 126.27125 en el caso de ejemplo).

Todos los parámetros son datos, no constantes: se cargan de /data y pueden
editarse desde la interfaz.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"

ETAPAS: dict[str, str] = {
    "R": "Requisitos",
    "F": "Funcional",
    "T": "Técnico",
    "C": "Construcción",
    "P": "Pruebas",
    "I": "Implantación",
}
COMPLEJIDADES = ["Alta", "Media-Alta", "Media", "Baja", "Mínima"]
VARIACIONES = ["Elemento Nuevo", "Elemento Modificado"]

CODIGO_DE_ETAPA: dict[str, str] = {v: k for k, v in ETAPAS.items()}

COLUMNAS_ELEMENTOS = [
    "Nombre",
    "Descripción",
    "TipoElemento",
    "Complejidad",
    "Variación",
    *ETAPAS.values(),
    "ClaveAgrupación",
    "DescripciónAgrupación",
    "Cantidad",
]


@dataclass
class Parametros:
    """Conjunto completo de parámetros configurables del modelo."""

    pesos: pd.DataFrame
    etapas: pd.DataFrame
    ajuste_volumen: pd.DataFrame
    tamanos: pd.DataFrame
    ajuste_manual: float = 0.0
    desc_ajuste_manual: str = ""
    tamano_forzado: str | None = None

    @classmethod
    def por_defecto(cls, data_dir: Path | str = DATA_DIR) -> "Parametros":
        d = Path(data_dir)
        return cls(
            pesos=pd.read_csv(d / "pesos.csv"),
            etapas=pd.read_csv(d / "etapas.csv"),
            ajuste_volumen=pd.read_csv(d / "ajuste_volumen.csv"),
            tamanos=pd.read_csv(d / "tamanos.csv"),
        )

    def guardar(self, data_dir: Path | str = DATA_DIR) -> None:
        d = Path(data_dir)
        d.mkdir(parents=True, exist_ok=True)
        self.pesos.to_csv(d / "pesos.csv", index=False)
        self.etapas.to_csv(d / "etapas.csv", index=False)
        self.ajuste_volumen.to_csv(d / "ajuste_volumen.csv", index=False)
        self.tamanos.to_csv(d / "tamanos.csv", index=False)

    @property
    def tipos_elemento(self) -> list[str]:
        return self.pesos["TipoElemento"].tolist()

    @property
    def grupos(self) -> list[str]:
        return self.etapas["Grupo"].drop_duplicates().tolist()

    def grupo_de(self, tipo: str) -> str:
        """Grupo tecnológico (Host, Java, SAP...) al que pertenece un tipo."""
        fila = self.pesos.loc[self.pesos["TipoElemento"] == tipo, "Grupo"]
        if fila.empty:
            raise KeyError(f"Tipo de elemento desconocido: {tipo!r}")
        return str(fila.iloc[0])

    def peso(self, tipo: str, variacion: str, complejidad: str) -> float:
        """Horas base unitarias según la TABLA DE PESOS."""
        clave = "Nuevo" if "Nuevo" in variacion else "Modificado"
        col = f"{clave}_{complejidad}"
        fila = self.pesos.loc[self.pesos["TipoElemento"] == tipo]
        if fila.empty:
            raise KeyError(f"Tipo de elemento desconocido: {tipo!r}")
        if col not in self.pesos.columns:
            raise KeyError(f"Complejidad desconocida: {complejidad!r}")
        return float(fila.iloc[0][col])

    def tamano_proyecto(self, horas_base_total: float) -> str:
        """PEQUEÑO / MEDIANO / GRANDE según el total de horas base."""
        if self.tamano_forzado:
            return self.tamano_forzado
        tab = self.tamanos.sort_values("LimiteSuperiorHoras")
        for _, r in tab.iterrows():
            if horas_base_total < float(r["LimiteSuperiorHoras"]):
                return str(r["Tamaño"])
        return str(tab.iloc[-1]["Tamaño"])

    def porcentajes_etapa(self, tamano: str, grupo: str) -> dict[str, float]:
        fila = self.etapas[(self.etapas["Tamaño"] == tamano) & (self.etapas["Grupo"] == grupo)]
        if fila.empty:
            raise KeyError(f"Sin porcentajes de etapa para {tamano!r} / {grupo!r}")
        return {e: float(fila.iloc[0][e]) for e in ETAPAS.values()}

    def factor_volumen(self, horas_base_total: float) -> float:
        """Equivalente a VLOOKUP(total; AjusteVolumen; 2; VERDADERO)."""
        tab = self.ajuste_volumen.sort_values("DesdeHoras")
        factor = float(tab.iloc[0]["Factor"])
        for _, r in tab.iterrows():
            if horas_base_total >= float(r["DesdeHoras"]):
                factor = float(r["Factor"])
            else:
                break
        return factor


def etapas_activas(fila) -> list[str]:
    """Etapas marcadas (True) para un elemento, a partir de sus columnas checkbox
    Requisitos/Funcional/Técnico/Construcción/Pruebas/Implantación."""
    return [e for e in ETAPAS.values() if pd.notna(fila.get(e)) and bool(fila.get(e))]


def etapas_como_codigo(activas: list[str]) -> str:
    """Nombres de etapa -> código corto para mostrar en el detalle, p. ej. 'F+T+C+P+I'."""
    return "+".join(CODIGO_DE_ETAPA[e] for e in ETAPAS.values() if e in activas)


@dataclass
class Resultado:
    detalle: pd.DataFrame
    por_etapa: pd.DataFrame
    total_base: float = 0.0
    total_etapas: float = 0.0
    factor_volumen: float = 0.0
    ajuste_complejidad: float = 0.0
    ajuste_manual: float = 0.0
    total_proyecto: float = 0.0
    tamano: str = ""
    avisos: list[str] = field(default_factory=list)


def calcular(elementos: pd.DataFrame, p: Parametros) -> Resultado:
    """Calcula la valoración completa a partir de la lista de elementos."""
    avisos: list[str] = []
    filas = []

    df = elementos.copy()
    df = df[df["TipoElemento"].notna() & (df["TipoElemento"].astype(str).str.strip() != "")]

    for i, r in df.iterrows():
        try:
            grupo = p.grupo_de(r["TipoElemento"])
            unit = p.peso(r["TipoElemento"], str(r["Variación"]), str(r["Complejidad"]))
        except KeyError as e:
            avisos.append(f"Fila {i + 1}: {e}")
            continue
        cant = float(r.get("Cantidad") or 1)
        activas = etapas_activas(r)
        if not activas:
            avisos.append(
                f"Fila {i + 1} ({r.get('Nombre', '')}): sin ninguna etapa marcada "
                f"— el elemento no aportará horas."
            )
        filas.append(
            {
                "Nombre": r.get("Nombre", ""),
                "TipoElemento": r["TipoElemento"],
                "Grupo": grupo,
                "Complejidad": r["Complejidad"],
                "Variación": r["Variación"],
                "Etapas": etapas_como_codigo(activas),
                "EtapasActivas": activas,
                "ClaveAgrupación": r.get("ClaveAgrupación", ""),
                "Cantidad": cant,
                "HorasUnitarias": unit,
                "HorasBase": unit * cant,
            }
        )

    cols_etapa = list(ETAPAS.values())
    if not filas:
        vacio = pd.DataFrame(columns=["Nombre", "Grupo", "HorasBase", "%Etapas", "Horas"] + cols_etapa)
        return Resultado(detalle=vacio, por_etapa=pd.DataFrame(columns=["Grupo"] + cols_etapa), avisos=avisos)

    det = pd.DataFrame(filas)
    total_base = float(det["HorasBase"].sum())

    tamano = p.tamano_proyecto(total_base)

    for etapa in cols_etapa:
        det[etapa] = 0.0
    det["%Etapas"] = 0.0
    det["Horas"] = 0.0

    for idx, r in det.iterrows():
        pct = p.porcentajes_etapa(tamano, r["Grupo"])
        activas = r["EtapasActivas"]
        total_pct = 0.0
        for etapa in cols_etapa:
            v = pct[etapa] if etapa in activas else 0.0
            # Redondeado aquí (no al calcular "Horas" por separado) para que la suma
            # de las columnas de etapa siempre reconstruya exactamente el total del
            # elemento: evita el descuadre que tenía el Excel entre RESULTADO y ETAPAS.
            det.at[idx, etapa] = round(r["HorasBase"] * v, 2)
            total_pct += v
        det.at[idx, "%Etapas"] = total_pct
        det.at[idx, "Horas"] = det.loc[idx, cols_etapa].sum()

    det = det.drop(columns=["EtapasActivas"])
    total_etapas = round(float(det["Horas"].sum()), 2)

    factor = p.factor_volumen(total_base)
    ajuste_compl = round(factor * total_etapas, 2)
    total_proyecto = round(total_etapas + ajuste_compl + p.ajuste_manual, 2)

    por_etapa = det.groupby("Grupo", as_index=False)[cols_etapa].sum().round(2)
    por_etapa["Total"] = por_etapa[cols_etapa].sum(axis=1).round(2)

    return Resultado(
        detalle=det,
        por_etapa=por_etapa,
        total_base=round(total_base, 2),
        total_etapas=total_etapas,
        factor_volumen=factor,
        ajuste_complejidad=ajuste_compl,
        ajuste_manual=float(p.ajuste_manual),
        total_proyecto=total_proyecto,
        tamano=tamano,
        avisos=avisos,
    )


def resumen_agrupaciones(res: Resultado) -> pd.DataFrame:
    """Equivalente a la hoja RESULTADO: subtotales por grupo tecnológico."""
    if res.detalle.empty:
        return pd.DataFrame(columns=["Grupo", "Horas"])
    g = res.detalle.groupby("Grupo", as_index=False)["Horas"].sum().round(2)
    return g.sort_values("Horas", ascending=False, ignore_index=True)


@dataclass
class Cuadre:
    """Compara el subtotal visto 'por Resultado' (agrupado por Grupo) contra
    el visto 'por Etapas' (agrupado por etapa) — deben coincidir siempre."""

    total_resultado: float
    total_etapas: float
    diferencia: float
    ok: bool


def verificar_cuadre(res: Resultado) -> Cuadre:
    total_resultado = round(float(resumen_agrupaciones(res)["Horas"].sum()), 2) if not res.detalle.empty else 0.0
    total_etapas = round(float(res.por_etapa["Total"].sum()), 2) if not res.por_etapa.empty else 0.0
    diff = round(total_resultado - total_etapas, 2)
    return Cuadre(total_resultado=total_resultado, total_etapas=total_etapas, diferencia=diff, ok=diff == 0)
