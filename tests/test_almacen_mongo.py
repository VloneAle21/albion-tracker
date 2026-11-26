"""Tests del guardado en MongoDB. Usan mongomock: una base de datos falsa en memoria."""

import mongomock
import pytest

from tracker.almacen_mongo import AlmacenMongo


@pytest.fixture
def almacen():
    almacen = AlmacenMongo(cliente=mongomock.MongoClient())
    almacen.crear_indices()
    return almacen


def evento(event_id):
    return {"EventId": event_id, "TimeStamp": "2026-11-25T15:26:45Z",
            "Killer": {"Id": "a", "Name": "Pepito"}, "Victim": {"Id": "b", "Name": "Juanito"},
            "TotalVictimKillFame": 1000}


def test_guarda_eventos_nuevos(almacen):
    assert almacen.guardar_eventos([evento(1), evento(2)], "europa") == 2
    assert almacen.contar_eventos() == 2


def test_no_duplica_eventos(almacen):
    almacen.guardar_eventos([evento(1), evento(2)], "europa")
    assert almacen.guardar_eventos([evento(2), evento(3)], "europa") == 1
    assert almacen.contar_eventos() == 3


def test_guarda_el_evento_tal_cual_con_el_servidor(almacen):
    almacen.guardar_eventos([evento(7)], "europa")
    guardado = almacen.eventos.find_one({"EventId": 7})
    assert guardado["Killer"]["Name"] == "Pepito"
    assert guardado["_servidor"] == "europa"
    assert "_descargado" in guardado


def test_guardar_jugador_actualiza_en_vez_de_duplicar(almacen):
    almacen.guardar_jugador({"Id": "a", "Name": "Pepito", "KillFame": 10}, "europa")
    almacen.guardar_jugador({"Id": "a", "Name": "Pepito", "KillFame": 99}, "europa")
    assert almacen.jugadores.count_documents({}) == 1
    assert almacen.jugadores.find_one({"Id": "a"})["KillFame"] == 99


def test_registrar_descarga(almacen):
    almacen.registrar_descarga("kills", "a", recibidos=5, nuevos=2)
    descarga = almacen.descargas.find_one()
    assert descarga["recibidos"] == 5 and descarga["nuevos"] == 2


# ----------------------------------------------------------------------
# Jugadores seguidos
# ----------------------------------------------------------------------

def test_seguir_un_jugador(almacen):
    assert almacen.seguir({"Id": "a", "Name": "Pepito"}, "europa") is True
    seguido = almacen.listar_seguidos()[0]
    assert seguido["nombre"] == "Pepito"
    assert seguido["servidor"] == "europa"
    assert seguido["ultima_consulta"] is None


def test_seguir_dos_veces_no_duplica(almacen):
    almacen.seguir({"Id": "a", "Name": "Pepito"}, "europa")
    assert almacen.seguir({"Id": "a", "Name": "Pepito"}, "europa") is False
    assert len(almacen.listar_seguidos()) == 1


def test_dejar_de_seguir_sin_mirar_mayusculas(almacen):
    almacen.seguir({"Id": "a", "Name": "Pepito"}, "europa")
    assert almacen.dejar_de_seguir("PEPITO") is True
    assert almacen.listar_seguidos() == []
    assert almacen.dejar_de_seguir("Pepito") is False


def test_marcar_consultado_guarda_el_error(almacen):
    almacen.seguir({"Id": "a", "Name": "Pepito"}, "europa")
    almacen.marcar_consultado("a", error="HTTP 503")
    seguido = almacen.listar_seguidos()[0]
    assert seguido["ultima_consulta"] is not None
    assert seguido["ultimo_error"] == "HTTP 503"
