"""Tests del worker con una API falsa y una base de datos falsa (mongomock)."""

import mongomock
import pytest

from tracker.albion_api import ErrorApiAlbion
from tracker.almacen_mongo import AlmacenMongo
from tracker.worker import Worker


def evento(event_id, asesino, victima):
    return {"EventId": event_id, "TimeStamp": "2026-11-25T15:26:45Z",
            "Killer": {"Id": asesino, "Name": asesino}, "Victim": {"Id": victima, "Name": victima},
            "TotalVictimKillFame": 1000}


# Lo que "devuelve la API" para cada jugador
DATOS = {
    "pepito": {"kills": [evento(1, "pepito", "x"), evento(2, "pepito", "y")],
               "muertes": [evento(3, "z", "pepito")]},
    "juanito": {"kills": [evento(4, "juanito", "x")], "muertes": []},
}


class ApiFalsa:
    """Imita a AlbionApi. Los jugadores de `fallan` lanzan ErrorApiAlbion."""

    def __init__(self, servidor, fallan=()):
        self.servidor = servidor
        self.fallan = set(fallan)

    def _comprobar(self, jugador_id):
        if jugador_id in self.fallan:
            raise ErrorApiAlbion("HTTP 503")

    def jugador(self, jugador_id):
        self._comprobar(jugador_id)
        return {"Id": jugador_id, "Name": jugador_id}

    def kills(self, jugador_id):
        self._comprobar(jugador_id)
        return DATOS[jugador_id]["kills"]

    def muertes(self, jugador_id):
        self._comprobar(jugador_id)
        return DATOS[jugador_id]["muertes"]


@pytest.fixture
def almacen():
    almacen = AlmacenMongo(cliente=mongomock.MongoClient())
    almacen.crear_indices()
    return almacen


def seguir(almacen, *nombres, servidor="europa"):
    for nombre in nombres:
        almacen.seguir({"Id": nombre, "Name": nombre}, servidor)


def test_ronda_sin_seguidos(almacen):
    assert Worker(almacen, crear_api=ApiFalsa).ronda() == 0


def test_ronda_guarda_los_eventos_de_todos(almacen):
    seguir(almacen, "pepito", "juanito")
    assert Worker(almacen, crear_api=ApiFalsa).ronda() == 4
    assert almacen.contar_eventos() == 4
    assert almacen.jugadores.count_documents({}) == 2
    for seguido in almacen.listar_seguidos():
        assert seguido["ultima_consulta"] is not None
        assert seguido["ultimo_error"] is None


def test_segunda_ronda_no_duplica(almacen):
    seguir(almacen, "pepito", "juanito")
    worker = Worker(almacen, crear_api=ApiFalsa)
    worker.ronda()
    assert worker.ronda() == 0
    assert almacen.contar_eventos() == 4


def test_si_un_jugador_falla_sigue_con_los_demas(almacen):
    seguir(almacen, "pepito", "juanito")
    worker = Worker(almacen, crear_api=lambda servidor: ApiFalsa(servidor, fallan={"juanito"}))
    assert worker.ronda() == 3
    estados = {s["nombre"]: s["ultimo_error"] for s in almacen.listar_seguidos()}
    assert estados == {"pepito": None, "juanito": "HTTP 503"}


def test_una_api_por_servidor(almacen):
    seguir(almacen, "pepito", servidor="europa")
    seguir(almacen, "juanito", servidor="america")
    worker = Worker(almacen, crear_api=ApiFalsa)
    worker.ronda()
    worker.ronda()
    assert sorted(worker.apis) == ["america", "europa"]
    assert almacen.eventos.find_one({"EventId": 4})["_servidor"] == "america"


def test_ejecutar_una_vez_no_se_queda_en_bucle(almacen):
    seguir(almacen, "pepito")
    Worker(almacen, crear_api=ApiFalsa).ejecutar(minutos=10, una_vez=True)
    assert almacen.contar_eventos() == 3


# ----------------------------------------------------------------------
# ETL al final de cada ronda
# ----------------------------------------------------------------------

class MysqlParaWorker:
    """MySQL falso: apunta los eventos que recibe. Si `roto`, falla como un MySQL caído."""

    def __init__(self, roto=False):
        self.roto = roto
        self.eventos = set()

    def asegurar_conexion(self):
        if self.roto:
            import pymysql
            raise pymysql.OperationalError(2003, "Can't connect to MySQL server")

    def guardar_jugador(self, fila):
        pass

    def guardar_jugador_si_no_existe(self, fila):
        pass

    def guardar_evento(self, evento, participaciones):
        nuevo = evento["event_id"] not in self.eventos
        self.eventos.add(evento["event_id"])
        return nuevo

    def confirmar(self):
        pass


def evento_completo(event_id, asesino, victima):
    """Como evento(), pero con lo que necesita el ETL."""
    e = evento(event_id, asesino, victima)
    e.update({"Participants": [], "numberOfParticipants": 1, "groupMemberCount": 1})
    return e


def test_ejecutar_pasa_lo_nuevo_a_mysql(almacen, monkeypatch):
    monkeypatch.setitem(DATOS, "pepito", {"kills": [evento_completo(1, "pepito", "x")],
                                          "muertes": [evento_completo(2, "z", "pepito")]})
    seguir(almacen, "pepito")
    mysql = MysqlParaWorker()
    Worker(almacen, crear_api=ApiFalsa, mysql=mysql).ejecutar(minutos=10, una_vez=True)
    assert mysql.eventos == {1, 2}


def test_si_mysql_falla_el_worker_sigue(almacen, monkeypatch):
    monkeypatch.setitem(DATOS, "pepito", {"kills": [evento_completo(1, "pepito", "x")],
                                          "muertes": []})
    seguir(almacen, "pepito")
    worker = Worker(almacen, crear_api=ApiFalsa, mysql=MysqlParaWorker(roto=True))
    worker.ejecutar(minutos=10, una_vez=True)  # no debe lanzar ninguna excepción
    assert almacen.contar_eventos() == 1       # en Mongo sí se ha guardado
    # y queda pendiente para cuando MySQL vuelva
    assert almacen.eventos.count_documents({"_cargado_mysql": {"$ne": True}}) == 1


# ----------------------------------------------------------------------
# seguir_jugador (la usan el comando de seguidos y la web)
# ----------------------------------------------------------------------

class ApiConBusqueda(ApiFalsa):
    def buscar_jugador(self, nombre):
        return {"Id": nombre.lower(), "Name": nombre} if nombre.lower() in DATOS else None


def test_seguir_jugador_hace_la_primera_descarga(almacen):
    from tracker.seguidos import seguir_jugador

    ok, mensaje = seguir_jugador(almacen, "Pepito", "europa", api=ApiConBusqueda("europa"))
    assert ok and "Ahora sigues a Pepito" in mensaje
    assert almacen.contar_eventos() == 3

    ok, mensaje = seguir_jugador(almacen, "Pepito", "europa", api=ApiConBusqueda("europa"))
    assert ok and mensaje == "Ya seguías a Pepito."


def test_seguir_jugador_que_no_existe(almacen):
    from tracker.seguidos import seguir_jugador

    ok, mensaje = seguir_jugador(almacen, "Nadie", "europa", api=ApiConBusqueda("europa"))
    assert not ok and "No hay ningún jugador" in mensaje
    assert almacen.listar_seguidos() == []
