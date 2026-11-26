"""Cliente sencillo para la API pública de Albion Online (la de la killboard).

La API no es oficial ni está documentada:
- No pide clave.
- No dice cuántas peticiones podemos hacer, así que vamos despacio (1 por segundo).
- A veces falla o tarda mucho, así que reintentamos con una espera cada vez mayor.

Ejemplo de uso:
    api = AlbionApi("europa")
    jugador = api.buscar_jugador("NombreDelJugador")
    kills = api.kills(jugador["Id"])
"""

import time

import requests

SERVIDORES = {
    "europa": "https://gameinfo-ams.albiononline.com/api/gameinfo",
    "america": "https://gameinfo.albiononline.com/api/gameinfo",
    "asia": "https://gameinfo-sgp.albiononline.com/api/gameinfo",
}


class ErrorApiAlbion(Exception):
    """La API no ha devuelto una respuesta válida."""


class AlbionApi:
    def __init__(self, servidor="europa", segundos_entre_peticiones=1.0,
                 reintentos=3, sesion=None):
        if servidor not in SERVIDORES:
            raise ValueError(
                f"Servidor '{servidor}' no válido. Usa uno de: {', '.join(SERVIDORES)}")

        self.servidor = servidor
        self.url_base = SERVIDORES[servidor]
        self.segundos_entre_peticiones = segundos_entre_peticiones
        self.reintentos = reintentos

        # Una sesión reutiliza la conexión y es más rápida que requests.get suelto.
        # En los tests se pasa una sesión falsa para no llamar a internet.
        self.sesion = sesion or requests.Session()
        self.sesion.headers["User-Agent"] = "albion-tracker (proyecto de clase)"

        self._hora_ultima_peticion = 0.0

    # ------------------------------------------------------------------
    # Métodos públicos: uno por cada dato que necesitamos
    # ------------------------------------------------------------------

    def buscar_jugadores(self, texto):
        """Devuelve la lista de jugadores cuyo nombre contiene el texto."""
        datos = self._get("/search", {"q": texto})
        if not datos:
            return []
        return datos.get("players", [])

    def buscar_jugador(self, nombre):
        """Devuelve el jugador con ese nombre exacto (sin mirar mayúsculas) o None."""
        for jugador in self.buscar_jugadores(nombre):
            if jugador["Name"].lower() == nombre.lower():
                return jugador
        return None

    def jugador(self, jugador_id):
        """Ficha completa de un jugador (fama, gremio, estadísticas...)."""
        return self._get(f"/players/{jugador_id}")

    def kills(self, jugador_id):
        """Últimos eventos en los que el jugador mató a alguien."""
        return self._get(f"/players/{jugador_id}/kills") or []

    def muertes(self, jugador_id):
        """Últimos eventos en los que el jugador murió."""
        return self._get(f"/players/{jugador_id}/deaths") or []

    def evento(self, event_id):
        """Un evento concreto por su id."""
        return self._get(f"/events/{event_id}")

    def eventos_recientes(self, limite=51, desde=0):
        """Últimas muertes de todo el servidor (la API admite como mucho 51 por página)."""
        return self._get("/events", {"limit": limite, "offset": desde}) or []

    # ------------------------------------------------------------------
    # Parte interna: pausa entre peticiones y reintentos
    # ------------------------------------------------------------------

    def _esperar_turno(self):
        """Duerme lo necesario para no hacer más de una petición por segundo."""
        pasado = time.monotonic() - self._hora_ultima_peticion
        if pasado < self.segundos_entre_peticiones:
            time.sleep(self.segundos_entre_peticiones - pasado)

    def _get(self, ruta, parametros=None):
        """Hace un GET a la API y devuelve el JSON ya convertido a dict/list.

        - 200: devuelve los datos.
        - 404: devuelve None (no existe).
        - 429 o 5xx o error de red: espera y lo vuelve a intentar.
        - Otro código: lanza ErrorApiAlbion sin reintentar.
        """
        url = self.url_base + ruta
        ultimo_error = ""

        for intento in range(1, self.reintentos + 1):
            self._esperar_turno()
            self._hora_ultima_peticion = time.monotonic()

            try:
                respuesta = self.sesion.get(url, params=parametros, timeout=20)
            except requests.RequestException as error:
                ultimo_error = f"error de red: {error}"
            else:
                if respuesta.status_code == 200:
                    try:
                        return respuesta.json()
                    except ValueError:
                        # A veces la API devuelve una página HTML de error con código 200
                        ultimo_error = "la respuesta no es JSON"
                elif respuesta.status_code == 404:
                    return None
                elif respuesta.status_code == 429 or respuesta.status_code >= 500:
                    ultimo_error = f"HTTP {respuesta.status_code}"
                else:
                    raise ErrorApiAlbion(f"{url} devolvió HTTP {respuesta.status_code}")

            if intento < self.reintentos:
                time.sleep(2 ** intento)  # 2 s, 4 s, 8 s...

        raise ErrorApiAlbion(f"{url} falló {self.reintentos} veces ({ultimo_error})")
