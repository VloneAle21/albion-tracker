"""Tests de las estadísticas con datos inventados (sin base de datos).

Al final hay uno que carga los datos desde MySQL real, si hay conexión.
"""

from datetime import datetime

import mongomock
import pandas as pd

from tracker import estadisticas as est
from tracker.almacen_mongo import AlmacenMongo
from tracker.etl import cargar


def datos(*eventos):
    """Crea el DataFrame preparado a partir de tuplas cortas:

    (fecha UTC 'AAAA-MM-DD HH:MM', rol, arma, ip, fama, tam_grupo)
    """
    filas = []
    for i, (fecha, rol, arma, ip, fama, grupo) in enumerate(eventos, start=1):
        filas.append({"event_id": i, "fecha": datetime.fromisoformat(fecha), "fama_total": fama,
                      "tam_grupo": grupo, "num_participantes": grupo, "zona": "OPEN_WORLD",
                      "rol": rol, "ip_media": ip, "arma": arma, "dano": None})
    return est.preparar(pd.DataFrame(filas))


ARCO = "T5_2H_LONGBOW"
ARCO_ENCANTADO = "T6_2H_LONGBOW@2"
BACULO = "T6_MAIN_FROSTSTAFF_AVALON@4"

# Lunes 23-11-2026. 18:00 UTC son las 19:00 en Madrid.
EJEMPLO = datos(
    ("2026-11-23 18:00", "asesino", ARCO, 1200, 1000, 1),
    ("2026-11-23 18:10", "asesino", ARCO_ENCANTADO, 1300, 2000, 1),
    ("2026-11-23 18:20", "victima", ARCO, 1000, 500, 8),
    ("2026-11-23 18:30", "asesino", BACULO, 1400, 3000, 4),
    ("2026-11-23 18:40", "asesino", BACULO, 1400, 1000, 4),
    ("2026-11-23 18:50", "asesino", BACULO, 1400, 1000, 30),
    ("2026-11-24 09:00", "victima", None, 800, 700, 1),
    ("2026-11-24 09:10", "asesino", ARCO, 1200, 500, 1),
    ("2026-11-24 09:20", "asistente", BACULO, 1400, 900, 5),
)


def test_arma_base():
    assert est.arma_base(ARCO) == "Longbow"
    assert est.arma_base(ARCO_ENCANTADO) == "Longbow"
    assert est.arma_base(BACULO) == "Froststaff Avalon"
    assert est.arma_base(None) == "Sin arma"


def test_preparar_pasa_a_hora_de_madrid():
    assert EJEMPLO["hora"].iloc[0] == 19          # 18:00 UTC -> 19:00 en invierno
    assert EJEMPLO["dia"].iloc[0] == 0            # lunes


def test_kd():
    assert est.kd(6, 2) == 3.0
    assert est.kd(5, 0) == 5.0
    assert est.kd(0, 0) == 0.0


def test_resumen():
    r = est.resumen(EJEMPLO)
    assert (r["kills"], r["muertes"], r["asistencias"]) == (6, 2, 1)
    assert r["kd"] == 3.0
    assert r["fama_ganada"] == 8500 and r["fama_perdida"] == 1200
    assert r["ratio_fama"] == 7.08


def test_rachas():
    # kill, kill, MUERE, kill x3, MUERE, kill (la asistencia no cuenta)
    assert est.rachas(EJEMPLO) == {"mejor": 3, "actual": 1}


def test_rachas_sin_datos():
    assert est.rachas(EJEMPLO.iloc[0:0]) == {"mejor": 0, "actual": 0}


def test_por_arma_junta_tiers_y_encantamientos():
    tabla = est.por_arma(EJEMPLO)
    # Empatan a 3 kills y K/D 3.0: va primero el báculo porque no ha muerto con él.
    assert list(tabla.index) == ["Froststaff Avalon", "Longbow", "Sin arma"]
    assert tabla.loc["Longbow"].to_dict() == {"kills": 3, "muertes": 1, "kd": 3.0}
    assert tabla.loc["Froststaff Avalon", "kills"] == 3   # la asistencia no cuenta


def test_por_arma_con_minimo():
    assert list(est.por_arma(EJEMPLO, minimo=2).index) == ["Froststaff Avalon", "Longbow"]


def test_por_hora():
    tabla = est.por_hora(EJEMPLO)
    assert len(tabla) == 24
    assert tabla.loc[19].to_dict() == {"kills": 5, "muertes": 1, "kd": 5.0}
    assert tabla.loc[10].to_dict() == {"kills": 1, "muertes": 1, "kd": 1.0}
    assert tabla.loc[3, "kills"] == 0


def test_mejores_horas_ignora_las_que_tienen_pocos_datos():
    assert list(est.mejores_horas(EJEMPLO, minimo=3).index) == [19]


def test_mejores_horas_no_incluye_horas_con_kd_menor_que_1():
    df = datos(("2026-11-23 18:00", "victima", ARCO, 1000, 500, 1),
               ("2026-11-23 18:10", "victima", ARCO, 1000, 500, 1),
               ("2026-11-23 18:20", "asesino", ARCO, 1000, 500, 1))
    assert len(est.mejores_horas(df, minimo=3)) == 0


def test_mapa_calor():
    tabla = est.mapa_calor(EJEMPLO)
    assert tabla.shape == (7, 24)
    assert tabla.loc["Lunes", 19] == 5
    assert tabla.loc["Martes", 10] == 1
    assert tabla.values.sum() == 6


def test_por_grupo():
    tabla = est.por_grupo(EJEMPLO)
    assert tabla["kills (su grupo)"].to_dict() == {"Solo": 3, "2-5": 2, "6-20": 0,
                                                    "Más de 20 (ZvZ)": 1}
    assert tabla["muertes (grupo enemigo)"].to_dict() == {"Solo": 1, "2-5": 0, "6-20": 1,
                                                           "Más de 20 (ZvZ)": 0}


def test_item_power():
    assert est.item_power(EJEMPLO) == {"ip_kills": 1317, "ip_muertes": 900}


def test_item_power_sin_muertes():
    assert est.item_power(EJEMPLO[EJEMPLO["es_kill"]])["ip_muertes"] is None


def test_comparar():
    otro = datos(("2026-11-23 18:00", "victima", ARCO, 1000, 500, 1))
    tabla = est.comparar({"Pepito": EJEMPLO, "Juanito": otro})
    assert list(tabla.index) == ["Pepito", "Juanito"]
    assert tabla.loc["Pepito", "arma_favorita"] == "Froststaff Avalon"
    assert tabla.loc["Juanito", "kd"] == 0.0
    assert tabla.loc["Juanito", "arma_favorita"] == "Longbow"


def test_por_dia_rellena_los_dias_sin_eventos():
    df = datos(("2026-11-23 18:00", "asesino", ARCO, 1200, 1000, 1),
               ("2026-11-25 18:00", "victima", ARCO, 1200, 1000, 1))
    tabla = est.por_dia(df)
    assert list(tabla["kills"]) == [1, 0, 0]
    assert list(tabla["muertes"]) == [0, 0, 1]


def test_por_dia_sin_datos():
    assert len(est.por_dia(EJEMPLO.iloc[0:0])) == 0


def test_ultimos_eventos():
    tabla = est.ultimos_eventos(EJEMPLO, cuantos=2)
    assert list(tabla["qué pasa"]) == ["Asiste", "Mata"]
    assert tabla["fecha"].iloc[0] == "2026-11-24 10:20"


# ----------------------------------------------------------------------
# Con MySQL de verdad
# ----------------------------------------------------------------------

def test_cargar_desde_mysql_real(mysql_real):
    mongo = AlmacenMongo(cliente=mongomock.MongoClient())
    mongo.crear_indices()
    jugador = {"Id": "a", "Name": "Pepito", "GuildName": "", "AverageItemPower": 1234.5,
               "Equipment": {"MainHand": {"Type": ARCO}}}
    victima = {"Id": "b", "Name": "Juanito", "GuildName": "", "AverageItemPower": 900,
               "Equipment": {"MainHand": None}}
    mongo.guardar_eventos([{
        "EventId": 1, "TimeStamp": "2026-11-23T18:00:00.0000000Z", "Killer": jugador,
        "Victim": victima, "Participants": [jugador], "TotalVictimKillFame": 1000,
        "numberOfParticipants": 1, "groupMemberCount": 1, "KillArea": "OPEN_WORLD",
        "BattleId": 1}], "europa")
    cargar(mongo, mysql_real)

    encontrado = est.buscar_jugador(mysql_real.conexion, "pepito")
    assert encontrado == {"id": "a", "nombre": "Pepito", "gremio": None}

    lista = est.jugadores_con_datos(mysql_real.conexion)
    assert set(lista["nombre"]) == {"Pepito", "Juanito"}

    df = est.cargar_eventos_jugador(mysql_real.conexion, "a")
    assert est.resumen(df)["kills"] == 1
    assert df["ip_media"].iloc[0] == 1234.5     # Decimal de MySQL convertido a float
    assert df["arma_base"].iloc[0] == "Longbow"
    assert df["hora"].iloc[0] == 19
