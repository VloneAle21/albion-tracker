"""Tests del cliente de la API. No llaman a internet: usan una sesión falsa."""

import pytest
import requests

from tracker import albion_api
from tracker.albion_api import AlbionApi, ErrorApiAlbion


class RespuestaFalsa:
    def __init__(self, codigo, datos=None):
        self.status_code = codigo
        self._datos = datos

    def json(self):
        if self._datos is None:
            raise ValueError("no es JSON")
        return self._datos


class SesionFalsa:
    """Devuelve las respuestas que le digamos, en orden, y apunta las URLs pedidas."""

    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.urls = []
        self.headers = {}

    def get(self, url, params=None, timeout=None):
        self.urls.append((url, params))
        respuesta = self.respuestas.pop(0)
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta


@pytest.fixture(autouse=True)
def sin_esperas(monkeypatch):
    """Los tests no deben dormir de verdad."""
    monkeypatch.setattr(albion_api.time, "sleep", lambda segundos: None)


def crear_api(*respuestas):
    return AlbionApi("europa", segundos_entre_peticiones=0, sesion=SesionFalsa(*respuestas))


BUSQUEDA = {"guilds": [], "players": [
    {"Id": "abc", "Name": "Pepito", "GuildName": "Los Guapos", "KillFame": 100, "DeathFame": 50},
    {"Id": "def", "Name": "Pepito2", "GuildName": None, "KillFame": 0, "DeathFame": 0},
]}


def test_servidor_no_valido():
    with pytest.raises(ValueError):
        AlbionApi("marte")


def test_buscar_jugadores_devuelve_la_lista():
    api = crear_api(RespuestaFalsa(200, BUSQUEDA))
    jugadores = api.buscar_jugadores("Pepito")
    assert [j["Id"] for j in jugadores] == ["abc", "def"]
    url, params = api.sesion.urls[0]
    assert url == "https://gameinfo-ams.albiononline.com/api/gameinfo/search"
    assert params == {"q": "Pepito"}


def test_buscar_jugador_por_nombre_exacto_sin_mayusculas():
    api = crear_api(RespuestaFalsa(200, BUSQUEDA))
    assert api.buscar_jugador("pepito")["Id"] == "abc"


def test_buscar_jugador_que_no_existe():
    api = crear_api(RespuestaFalsa(200, BUSQUEDA))
    assert api.buscar_jugador("Juanito") is None


def test_404_devuelve_none():
    api = crear_api(RespuestaFalsa(404))
    assert api.jugador("noexiste") is None


def test_kills_vacias_si_la_api_devuelve_404():
    api = crear_api(RespuestaFalsa(404))
    assert api.kills("noexiste") == []


def test_reintenta_si_el_servidor_falla():
    api = crear_api(RespuestaFalsa(503), RespuestaFalsa(200, [{"EventId": 1}]))
    assert api.muertes("abc") == [{"EventId": 1}]
    assert len(api.sesion.urls) == 2


def test_reintenta_si_hay_error_de_red_o_no_es_json():
    api = crear_api(requests.ConnectionError("sin red"), RespuestaFalsa(200, None),
                    RespuestaFalsa(200, []))
    assert api.kills("abc") == []
    assert len(api.sesion.urls) == 3


def test_se_rinde_tras_los_reintentos():
    api = crear_api(RespuestaFalsa(500), RespuestaFalsa(500), RespuestaFalsa(500))
    with pytest.raises(ErrorApiAlbion):
        api.kills("abc")


def test_error_400_no_se_reintenta():
    api = crear_api(RespuestaFalsa(400))
    with pytest.raises(ErrorApiAlbion):
        api.evento(123)
    assert len(api.sesion.urls) == 1


def test_eventos_recientes_manda_limite_y_desde():
    api = crear_api(RespuestaFalsa(200, []))
    api.eventos_recientes(limite=10, desde=20)
    assert api.sesion.urls[0][1] == {"limit": 10, "offset": 20}
