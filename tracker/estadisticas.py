"""Estadísticas de un jugador a partir de los datos limpios de MySQL.

Cómo se usa desde código (la web de la fase 6 hará esto mismo):

    jugador = buscar_jugador(conexion, "Pepito")
    df = cargar_eventos_jugador(conexion, jugador["id"])
    resumen(df)      -> kills, muertes, K/D, fama...
    rachas(df)       -> mejor racha de kills sin morir y racha actual
    por_arma(df)     -> rendimiento con cada arma
    por_hora(df)     -> rendimiento por hora del día
    mapa_calor(df)   -> kills por día de la semana y hora
    por_grupo(df)    -> solo frente a grupo
    item_power(df)   -> Item Power medio en kills y en muertes
    comparar({...})  -> tabla con varios jugadores

Y desde la terminal:
    python -m tracker.estadisticas Pepito
    python -m tracker.estadisticas Pepito Juanito     (los compara)

Importante: solo se cuenta lo que ha guardado el worker. La API no da el historial
antiguo, así que las cifras son "desde que lo seguimos", no de toda su vida.
"""

import re
import sys

import pandas as pd

DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
GRUPOS = ["Solo", "2-5", "6-20", "Más de 20 (ZvZ)"]
ZONA_HORARIA = "Europe/Madrid"

# ----------------------------------------------------------------------
# Cargar los datos de MySQL
# ----------------------------------------------------------------------


def buscar_jugador(conexion, nombre):
    """Devuelve {"id", "nombre", "gremio"} del jugador o None (sin mirar mayúsculas)."""
    with conexion.cursor() as cursor:
        cursor.execute("SELECT id, nombre, gremio FROM jugadores WHERE LOWER(nombre) = LOWER(%s)",
                       (nombre,))
        fila = cursor.fetchone()
    if fila is None:
        return None
    return {"id": fila[0], "nombre": fila[1], "gremio": fila[2]}


def jugadores_con_datos(conexion, minimo=1):
    """Jugadores con al menos `minimo` participaciones, de más a menos eventos."""
    sql = """
        SELECT j.id, j.nombre, j.gremio, COUNT(*) AS eventos
        FROM jugadores j
        JOIN participaciones p ON p.jugador_id = j.id
        GROUP BY j.id, j.nombre, j.gremio
        HAVING COUNT(*) >= %s
        ORDER BY eventos DESC, j.nombre
    """
    with conexion.cursor() as cursor:
        cursor.execute(sql, (minimo,))
        filas = cursor.fetchall()
    return pd.DataFrame(filas, columns=["id", "nombre", "gremio", "eventos"])


def cargar_eventos_jugador(conexion, jugador_id):
    """Todas las participaciones del jugador, una fila por evento, ya preparadas."""
    sql = """
        SELECT e.event_id, e.fecha, e.fama_total, e.tam_grupo, e.num_participantes, e.zona,
               p.rol, p.ip_media, p.arma, p.dano
        FROM participaciones p
        JOIN eventos e ON e.event_id = p.event_id
        WHERE p.jugador_id = %s
        ORDER BY e.fecha
    """
    with conexion.cursor() as cursor:
        cursor.execute(sql, (jugador_id,))
        columnas = [c[0] for c in cursor.description]
        df = pd.DataFrame(cursor.fetchall(), columns=columnas)
    return preparar(df)


# ----------------------------------------------------------------------
# Preparar: columnas auxiliares que usan todas las estadísticas
# ----------------------------------------------------------------------


def arma_base(tipo):
    """'T6_MAIN_FROSTSTAFF_AVALON@4' -> 'Froststaff Avalon'.

    Se quita el tier (T6_), el encantamiento (@4) y el prefijo de la mano (MAIN_, 2H_...),
    para que el mismo arma en distintos tiers cuente como una sola.
    """
    # pandas convierte los None en NaN, así que se comprueba con pd.isna.
    if pd.isna(tipo) or not tipo:
        return "Sin arma"
    tipo = re.sub(r"^T\d+_", "", tipo)          # tier
    tipo = re.sub(r"@\d+$", "", tipo)           # encantamiento
    tipo = re.sub(r"^(MAIN|2H|OFF)_", "", tipo)  # mano
    return tipo.replace("_", " ").title()


def preparar(df, zona_horaria=ZONA_HORARIA):
    """Añade columnas: es_kill, es_muerte, fecha_local, hora, dia, arma_base."""
    df = df.copy()
    # MySQL devuelve los DECIMAL como Decimal de Python; pandas trabaja mejor con float.
    for columna in ("ip_media", "dano"):
        df[columna] = pd.to_numeric(df[columna], errors="coerce")

    df["es_kill"] = df["rol"] == "asesino"
    df["es_muerte"] = df["rol"] == "victima"

    # Las fechas se guardan en UTC; para "a qué hora juega" hay que pasarlas a hora local.
    df["fecha_local"] = pd.to_datetime(df["fecha"]).dt.tz_localize("UTC").dt.tz_convert(zona_horaria)
    df["hora"] = df["fecha_local"].dt.hour
    df["dia"] = df["fecha_local"].dt.day_of_week  # 0 = lunes

    df["arma_base"] = df["arma"].apply(arma_base)
    return df


def kd(kills, muertes):
    """K/D: kills entre muertes. Sin muertes, el K/D es el número de kills."""
    return round(kills / muertes, 2) if muertes else float(kills)


def _tabla_kd(agrupado):
    """De un groupby a una tabla con kills, muertes y K/D."""
    tabla = agrupado.agg(kills=("es_kill", "sum"), muertes=("es_muerte", "sum"))
    tabla["kd"] = [kd(k, m) for k, m in zip(tabla["kills"], tabla["muertes"])]
    return tabla


def _solo_kills_y_muertes(df):
    return df[df["es_kill"] | df["es_muerte"]]


# ----------------------------------------------------------------------
# Estadísticas
# ----------------------------------------------------------------------


def resumen(df):
    kills = int(df["es_kill"].sum())
    muertes = int(df["es_muerte"].sum())
    fama_ganada = int(df.loc[df["es_kill"], "fama_total"].sum())
    fama_perdida = int(df.loc[df["es_muerte"], "fama_total"].sum())
    return {
        "kills": kills,
        "muertes": muertes,
        "asistencias": int((df["rol"] == "asistente").sum()),
        "kd": kd(kills, muertes),
        "fama_ganada": fama_ganada,      # fama de las víctimas a las que dio el golpe final
        "fama_perdida": fama_perdida,    # fama que dio a otros al morir
        "ratio_fama": kd(fama_ganada, fama_perdida),
        "desde": df["fecha_local"].min() if len(df) else None,
        "hasta": df["fecha_local"].max() if len(df) else None,
    }


def rachas(df):
    """Mejor racha de kills seguidas sin morir y racha actual (desde la última muerte)."""
    mejor = actual = 0
    for es_kill in _solo_kills_y_muertes(df).sort_values("fecha")["es_kill"]:
        if es_kill:
            actual += 1
            mejor = max(mejor, actual)
        else:
            actual = 0
    return {"mejor": mejor, "actual": actual}


def por_arma(df, minimo=1):
    """Kills, muertes y K/D con cada arma. `minimo`: eventos mínimos para salir en la tabla."""
    tabla = _tabla_kd(_solo_kills_y_muertes(df).groupby("arma_base"))
    tabla = tabla[tabla["kills"] + tabla["muertes"] >= minimo]
    # Más kills primero; si empatan, mejor K/D; si siguen empatadas, menos muertes.
    return tabla.sort_values(["kills", "kd", "muertes"], ascending=[False, False, True])


def por_hora(df):
    """Kills, muertes y K/D por hora del día (0 a 23), en hora local."""
    tabla = _tabla_kd(_solo_kills_y_muertes(df).groupby("hora"))
    tabla = tabla.reindex(range(24), fill_value=0)
    tabla["kd"] = [kd(k, m) for k, m in zip(tabla["kills"], tabla["muertes"])]
    tabla.index.name = "hora"
    return tabla


def mejores_horas(df, minimo=3, cuantas=3):
    """Las horas con mejor K/D (al menos 1), contando solo las que tienen `minimo` eventos."""
    tabla = por_hora(df)
    tabla = tabla[(tabla["kills"] + tabla["muertes"] >= minimo) & (tabla["kd"] >= 1)]
    return tabla.sort_values(["kd", "kills"], ascending=False).head(cuantas)


def mapa_calor(df, valor="es_kill"):
    """Tabla día de la semana x hora con el número de kills (o de muertes con valor='es_muerte')."""
    tabla = df.pivot_table(index="dia", columns="hora", values=valor, aggfunc="sum", fill_value=0)
    tabla = tabla.reindex(index=range(7), columns=range(24), fill_value=0).astype(int)
    tabla.index = DIAS
    return tabla


def por_dia(df):
    """Kills y muertes de cada día (hora local), incluidos los días sin eventos."""
    df = _solo_kills_y_muertes(df)
    if not len(df):
        return pd.DataFrame(columns=["kills", "muertes"])
    dias = df["fecha_local"].dt.normalize()
    tabla = df.groupby(dias).agg(kills=("es_kill", "sum"), muertes=("es_muerte", "sum"))
    todos = pd.date_range(tabla.index.min(), tabla.index.max(), freq="D")
    tabla = tabla.reindex(todos, fill_value=0)
    tabla.index.name = "dia"
    return tabla


def ultimos_eventos(df, cuantos=20):
    """Tabla legible con los últimos eventos del jugador."""
    nombres_rol = {"asesino": "Mata", "victima": "Muere", "asistente": "Asiste"}
    ultimos = df.sort_values("fecha", ascending=False).head(cuantos)
    return pd.DataFrame({
        "fecha": ultimos["fecha_local"].dt.strftime("%Y-%m-%d %H:%M"),
        "qué pasa": ultimos["rol"].map(nombres_rol),
        "arma": ultimos["arma_base"],
        "item power": ultimos["ip_media"].round(0),
        "fama": ultimos["fama_total"],
        "tamaño del grupo": ultimos["tam_grupo"],
    }).reset_index(drop=True)


def grupo_de(tamano):
    if tamano <= 1:
        return GRUPOS[0]
    if tamano <= 5:
        return GRUPOS[1]
    if tamano <= 20:
        return GRUPOS[2]
    return GRUPOS[3]


def por_grupo(df):
    """Solo frente a grupo.

    Ojo: tam_grupo es el tamaño del grupo del ASESINO. Por eso:
    - en las kills, es el grupo del jugador (¿mata más solo o en grupo?);
    - en las muertes, es el grupo enemigo (¿contra cuántos muere?).
    No se puede sacar un K/D por grupo: no son los mismos grupos.
    """
    df = df.assign(grupo=df["tam_grupo"].apply(grupo_de))
    kills = df[df["es_kill"]].groupby("grupo").size()
    muertes = df[df["es_muerte"]].groupby("grupo").size()
    tabla = pd.DataFrame({
        "kills (su grupo)": kills.reindex(GRUPOS, fill_value=0),
        "muertes (grupo enemigo)": muertes.reindex(GRUPOS, fill_value=0),
    })
    tabla.index.name = "grupo"
    return tabla


def item_power(df):
    """Item Power medio del jugador cuando mata y cuando muere."""
    ip_kills = df.loc[df["es_kill"], "ip_media"].mean()
    ip_muertes = df.loc[df["es_muerte"], "ip_media"].mean()

    def redondear(valor):
        return None if pd.isna(valor) else round(float(valor))

    return {"ip_kills": redondear(ip_kills), "ip_muertes": redondear(ip_muertes)}


def comparar(jugadores):
    """jugadores: {nombre: df}. Devuelve una tabla con una fila por jugador."""
    filas = []
    for nombre, df in jugadores.items():
        r = resumen(df)
        armas = por_arma(df)
        ip = item_power(df)
        filas.append({
            "jugador": nombre,
            "kills": r["kills"],
            "muertes": r["muertes"],
            "kd": r["kd"],
            "ratio_fama": r["ratio_fama"],
            "mejor_racha": rachas(df)["mejor"],
            "arma_favorita": armas.index[0] if len(armas) else None,
            "ip_kills": ip["ip_kills"],
            "ip_muertes": ip["ip_muertes"],
        })
    return pd.DataFrame(filas).set_index("jugador")


# ----------------------------------------------------------------------
# Informe por terminal
# ----------------------------------------------------------------------


def informe(nombre, df):
    r = resumen(df)
    print(f"\n=== {nombre} ===")
    if not len(df):
        print("Sin eventos guardados todavía.")
        return
    print(f"Datos desde {r['desde']:%Y-%m-%d %H:%M} hasta {r['hasta']:%Y-%m-%d %H:%M} "
          "(solo lo que ha guardado el worker)")
    print(f"Kills {r['kills']}  ·  Muertes {r['muertes']}  ·  K/D {r['kd']}  ·  "
          f"Ratio de fama {r['ratio_fama']}")
    racha = rachas(df)
    print(f"Mejor racha sin morir: {racha['mejor']} kills  ·  Racha actual: {racha['actual']}")
    ip = item_power(df)
    print(f"Item Power medio: {ip['ip_kills']} cuando mata, {ip['ip_muertes']} cuando muere")

    print("\nArmas (top 5):")
    print(por_arma(df).head(5).to_string())
    print("\nMejores horas (mínimo 3 eventos):")
    horas = mejores_horas(df)
    print(horas.to_string() if len(horas) else "Todavía no hay datos suficientes.")
    print("\nSolo frente a grupo:")
    print(por_grupo(df).to_string())


def main():
    from tracker.almacen_mysql import conectar_mysql

    nombres = sys.argv[1:]
    if not nombres:
        print("Uso: python -m tracker.estadisticas Jugador [OtroJugador ...]")
        return 1

    mysql = conectar_mysql()
    if mysql is None:
        return 1

    datos = {}
    for nombre in nombres:
        jugador = buscar_jugador(mysql.conexion, nombre)
        if jugador is None:
            print(f"'{nombre}' no está en MySQL. ¿Lo sigues y has pasado el ETL?")
            continue
        datos[jugador["nombre"]] = cargar_eventos_jugador(mysql.conexion, jugador["id"])

    if len(datos) == 1:
        nombre, df = next(iter(datos.items()))
        informe(nombre, df)
    elif len(datos) > 1:
        print(comparar(datos).to_string())
    return 0 if datos else 1


if __name__ == "__main__":
    sys.exit(main())
