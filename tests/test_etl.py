"""Tests del ETL.

- La transformación se prueba sin base de datos.
- La carga se prueba con mongomock y un MySQL falso que apunta lo que recibe.
- Al final hay un test con MySQL de verdad que solo se ejecuta si hay conexión.
"""

from datetime import datetime

import mongomock
import pytest

from tracker.almacen_mongo import AlmacenMongo
from tracker.etl import a_fecha, arma_de, cargar, fila_jugador, transformar_evento


def jugador(id, nombre, arma="T5_2H_LONGBOW", ip=1200.456, gremio="Los Guapos", dano=None):
    datos = {"Id": id, "Name": nombre, "GuildName": gremio, "AverageItemPower": ip,
             "Equipment": {"MainHand": {"Type": arma} if arma else None}}
    if dano is not None:
        datos["DamageDone"] = dano
    return datos


def evento_mongo(event_id=1, participantes=None):
    """Un evento como los que guarda el worker en Mongo (recortado)."""
    if participantes is None:
        participantes = [jugador("a", "Pepito", dano=800.0), jugador("c", "Lolo", dano=200.0)]
    return {
        "EventId": event_id, "TimeStamp": "2026-11-25T15:26:45.114877100Z",
        "Killer": jugador("a", "Pepito"),
        "Victim": jugador("b", "Juanito", arma=None, gremio=""),
        "Participants": participantes,
        "TotalVictimKillFame": 9720, "numberOfParticipants": len(participantes),
        "groupMemberCount": 2, "KillArea": "OPEN_WORLD", "BattleId": 99,
        "_servidor": "europa",
    }


# ----------------------------------------------------------------------
# Transformar
# ----------------------------------------------------------------------

def test_a_fecha_quita_los_decimales():
    assert a_fecha("2026-11-25T15:26:45.114877100Z") == datetime(2026, 11, 25, 15, 26, 45)
    assert a_fecha(None) is None


def test_arma_de_sin_arma():
    assert arma_de(jugador("x", "X", arma=None)) is None
    assert arma_de({"Equipment": None}) is None


def test_transformar_evento():
    evento, participaciones, jugadores = transformar_evento(evento_mongo())

    assert evento == {"event_id": 1, "fecha": datetime(2026, 11, 25, 15, 26, 45),
                      "servidor": "europa", "fama_total": 9720, "num_participantes": 2,
                      "tam_grupo": 2, "zona": "OPEN_WORLD", "batalla_id": 99}

    por_rol = {(p["jugador_id"], p["rol"]): p for p in participaciones}
    assert set(por_rol) == {("a", "asesino"), ("b", "victima"), ("c", "asistente")}
    assert por_rol[("a", "asesino")]["dano"] == 800.0     # sale de Participants
    assert por_rol[("a", "asesino")]["ip_media"] == 1200.46
    assert por_rol[("b", "victima")]["arma"] is None
    assert por_rol[("b", "victima")]["dano"] is None

    assert sorted(j["id"] for j in jugadores) == ["a", "b", "c"]
    assert next(j for j in jugadores if j["id"] == "b")["gremio"] is None  # "" -> None


def test_transformar_evento_solo():
    """Kill en solitario: el asesino es el único participante, no hay asistentes."""
    _, participaciones, _ = transformar_evento(evento_mongo(participantes=[jugador("a", "Pepito")]))
    assert [p["rol"] for p in participaciones] == ["asesino", "victima"]


def test_fila_jugador():
    doc = {"Id": "a", "Name": "Pepito", "GuildName": "", "KillFame": 10, "DeathFame": 5,
           "_servidor": "europa", "_actualizado": datetime(2026, 11, 26)}
    assert fila_jugador(doc) == {"id": "a", "nombre": "Pepito", "gremio": None,
                                 "servidor": "europa", "kill_fame": 10, "death_fame": 5,
                                 "actualizado": datetime(2026, 11, 26)}


# ----------------------------------------------------------------------
# Cargar (con un MySQL falso)
# ----------------------------------------------------------------------

class MysqlFalso:
    def __init__(self):
        self.jugadores = {}
        self.eventos = {}
        self.commits = 0

    def guardar_jugador(self, fila):
        self.jugadores[fila["id"]] = fila

    def guardar_jugador_si_no_existe(self, fila):
        self.jugadores.setdefault(fila["id"], fila)

    def guardar_evento(self, evento, participaciones):
        if evento["event_id"] in self.eventos:
            return False
        self.eventos[evento["event_id"]] = participaciones
        return True

    def confirmar(self):
        self.commits += 1


@pytest.fixture
def mongo():
    almacen = AlmacenMongo(cliente=mongomock.MongoClient())
    almacen.crear_indices()
    return almacen


def test_cargar_pasa_eventos_y_los_marca(mongo):
    mongo.guardar_eventos([evento_mongo(1), evento_mongo(2)], "europa")
    mysql = MysqlFalso()

    resumen = cargar(mongo, mysql)

    assert resumen["eventos_nuevos"] == 2
    assert sorted(mysql.eventos) == [1, 2]
    assert sorted(mysql.jugadores) == ["a", "b", "c"]
    assert mongo.eventos.count_documents({"_cargado_mysql": True}) == 2


def test_cargar_dos_veces_solo_procesa_lo_nuevo(mongo):
    mongo.guardar_eventos([evento_mongo(1)], "europa")
    mysql = MysqlFalso()
    cargar(mongo, mysql)

    mongo.guardar_eventos([evento_mongo(2)], "europa")
    resumen = cargar(mongo, mysql)
    assert resumen["eventos_nuevos"] == 1
    assert resumen["eventos_repetidos"] == 0


def test_cargar_todo_reprocesa_sin_duplicar(mongo):
    mongo.guardar_eventos([evento_mongo(1)], "europa")
    mysql = MysqlFalso()
    cargar(mongo, mysql)
    resumen = cargar(mongo, mysql, todo=True)
    assert resumen == {"jugadores": 0, "eventos_nuevos": 0, "eventos_repetidos": 1, "errores": 0}


def test_un_evento_roto_no_para_el_etl(mongo):
    roto = evento_mongo(1)
    del roto["Killer"]
    mongo.guardar_eventos([roto, evento_mongo(2)], "europa")
    mysql = MysqlFalso()

    resumen = cargar(mongo, mysql)

    assert resumen["errores"] == 1 and resumen["eventos_nuevos"] == 1
    # El roto no se marca como cargado, para poder arreglarlo y volver a cargarlo.
    assert mongo.eventos.find_one({"EventId": 1}).get("_cargado_mysql") is None


def test_la_ficha_completa_no_se_pisa(mongo):
    mongo.guardar_jugador({"Id": "a", "Name": "Pepito", "KillFame": 500, "DeathFame": 1}, "europa")
    mongo.guardar_eventos([evento_mongo(1)], "europa")
    mysql = MysqlFalso()
    cargar(mongo, mysql)
    assert mysql.jugadores["a"]["kill_fame"] == 500


# ----------------------------------------------------------------------
# Con MySQL de verdad (base de datos albion_tracker_test)
# ----------------------------------------------------------------------

def test_cargar_en_mysql_real(mongo, mysql_real):
    mongo.guardar_jugador({"Id": "a", "Name": "Pepito", "KillFame": 500, "DeathFame": 1}, "europa")
    mongo.guardar_eventos([evento_mongo(1), evento_mongo(2)], "europa")

    cargar(mongo, mysql_real)
    cargar(mongo, mysql_real, todo=True)  # la segunda vez no debe duplicar nada

    assert mysql_real.contar("eventos") == 2
    assert mysql_real.contar("participaciones") == 6
    assert mysql_real.contar("jugadores") == 3
    with mysql_real.conexion.cursor() as cursor:
        cursor.execute("SELECT kill_fame FROM jugadores WHERE id = 'a'")
        assert cursor.fetchone()[0] == 500
