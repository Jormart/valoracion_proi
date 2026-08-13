# Valoración PROI

Aplicación Streamlit para estimar el esfuerzo (horas) de un conjunto de
tareas de la Cadencia 6.x, repartido por etapa de desarrollo, grupo
tecnológico y Product Team — con balanceo de carga frente a la capacidad
real de cada equipo.

Nace como reimplementación en Python del libro Excel `Valoracion_PROI_v0.xlsm`,
corrigiendo varias inconsistencias del original (ver [Notas de diseño](#notas-de-diseño)).

## Arranque rápido

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Estructura

```
valoracion_proi/
├── app.py              # interfaz Streamlit (todas las pestañas)
├── engine.py            # motor de cálculo, sin dependencias de UI
├── requirements.txt
└── data/                 # parámetros por defecto, todos editables desde la app
    ├── pesos.csv              # horas base por tipo de tarea × complejidad × variación
    ├── etapas.csv             # % de esfuerzo por etapa, según grupo tecnológico
    ├── ajuste_volumen.csv     # factor de ajuste por complejidad según horas totales
    ├── product_teams.csv      # lista de Product Teams (PT1, PT3, PT6...)
    ├── capacidad.csv          # FTEs fijos por Product Team y grupo tecnológico
    ├── capacidad_config.csv   # horas/semana, buffer de imprevistos, horas/día
    └── elementos_ejemplo.csv  # tareas de ejemplo precargadas al abrir la app
```

`engine.py` no importa Streamlit: toda la lógica de cálculo se puede probar o
reutilizar de forma independiente de la interfaz.

## Modelo de datos

Cada fila de **Datos de Entrada** es una tarea de la Cadencia 6.x con:

- **Tipo de elemento** → determina el **Grupo** tecnológico (Host, Java o
  Testing) y las horas base por unidad, vía la tabla de pesos.
- **Complejidad** y **Variación** (Elemento Nuevo / Modificado) → columna de
  la tabla de pesos.
- **Etapas** marcadas con checkbox — Funcional, Técnico, Construcción,
  Pruebas, Implantación — cada una aporta su % configurado en Tabla Etapas.
- **Product Team** — a qué equipo se asigna la tarea.
- **ClaveAgrupación** (opcional) — para ligar tareas extra de testing
  (Análisis, Regresión, Incidencias, Defects) a la tarea principal: basta
  con crear una fila nueva con la misma clave. La pestaña Resultado agrega
  esas filas en "Por tarea".

Las horas de una tarea son la suma de sus columnas de etapa, cada una
`ROUND(horas_base × %etapa, 2)`. El total del proyecto añade un ajuste por
volumen/complejidad y un ajuste manual.

## Pestañas

| Pestaña | Contenido |
|---|---|
| 📋 Datos de Entrada | tabla editable de tareas de la Cadencia 6.x |
| 📊 Resultado | subtotales por grupo, por Product Team y por tarea; detalle fila a fila |
| 🔩 Etapas | reparto de horas por etapa (mismo dato que Resultado, otro eje de agregación) |
| ⚖️ Parámetros | tabla de pesos y ajuste por volumen, editables |
| 📐 Tabla Etapas | % de esfuerzo por etapa, por grupo tecnológico |
| 🗓️ Timeline | Gantt relativo: cada tarea como barra con sus etapas encadenadas en días |
| ⚖️ Balanceo de carga | horas esperadas vs. capacidad disponible por Product Team, con holguras/desbordamientos |
| ⬇️ Exportar | descarga del libro completo en Excel o el detalle en CSV |

Resultado y Etapas siempre cuadran entre sí: ambas se calculan a partir de la
misma tabla de detalle, ya redondeada, en vez de mantenerse como copias
independientes (ver más abajo). Un aviso ✅/⚠️ visible en la cabecera lo
confirma en cada recálculo.

## Notas de diseño

- **Cuadre garantizado por construcción.** El Excel original mantenía
  `RESULTADO` y `ETAPAS` como tablas separadas, con distinto orden de
  redondeo, y podían divergir (126.27 vs 126.27125 h en el caso de ejemplo).
  Aquí solo existe una tabla de detalle; todas las vistas son agregaciones
  de las mismas celdas ya redondeadas.
- **Sin clasificación de tamaño de proyecto.** El Excel original tenía tres
  bloques de % por etapa (PEQUEÑO/MEDIANO/GRANDE de `TABLA ETAPAS`), aunque
  en la práctica sus fórmulas quedaban siempre fijadas al bloque PEQUEÑO. El
  trabajo se organiza por cadencias semanales, no por proyectos, así que ese
  eje no aportaba nada y se eliminó: `TABLA ETAPAS` tiene ahora un único %
  por grupo tecnológico (se conservaron los valores que antes eran el
  bloque PEQUEÑO, que es lo que el Excel aplicaba de facto).
- **Etapas seleccionables por checkbox**, no por código de texto libre
  (`F+T+C+P+I`) — evita errores de escritura que antes se descartaban en
  silencio.
- **Pesos de Testing y umbrales de capacidad son puntos de partida
  editables, no cifras cerradas:**
  - Los pesos de `Testing: Análisis/Regresión/Incidencias/Defects` parten de
    ×2 sobre el peso equivalente de Host, a falta de cifras reales propias.
  - Los % de etapa de Testing en `Tabla Etapas` son una copia de los de Host.
  - Los FTEs de `capacidad.csv` son los de PT1, PT3 y PT6 (PT2 no incluido a
    petición). El buffer de imprevistos (20%) se aplica igual a todos los
    roles porque no hay desglose de Teamleads en los datos disponibles — si
    hace falta un margen distinto para Teamleads (30%), hay que modelarlos
    como fila propia en `capacidad.csv`.

  Todo esto es editable desde la app (pestañas Parámetros, Tabla Etapas y
  Balanceo de carga) y se puede fijar como nuevo valor por defecto con el
  botón "Guardar parámetros" de la barra lateral.
