"""Guarda en MongoDB las respuestas de la API tal cual llegan (datos en bruto).

Colecciones:
- eventos:    cada evento de muerte. No se repite gracias al índice único en EventId.
- jugadores:  la ficha de cada jugador; se sobrescribe con la más reciente.
- descargas:  un registro de cada descarga, para saber qué hizo el worker y cuándo.
- seguidos:   los jugadores que el worker tiene que consultar (esta la creamos nosotros).
"""

from datetime import datetime, timezone

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import PyMongoError

from tracker import config


def ahora():
    return datetime.now(timezone.utc)


class AlmacenMongo:
    def __init__(self, uri="mongodb://localhost:27017", nombre_bd="albion_tracker",
                 cliente=None):
        # En los tests se pasa un cliente falso (mongomock) en vez de uno real.
        self.cliente = cliente or MongoClient(uri, serverSelectionTimeoutMS=5000)
        bd = self.cliente[nombre_bd]
        self.eventos = bd["eventos"]
        self.jugadores = bd["jugadores"]
        self.descargas = bd["descargas"]
        self.seguidos = bd["seguidos"]

    def crear_indices(self):
        """Se puede llamar todas las veces que se quiera: si ya existen, no hace nada."""
        self.eventos.create_index([("EventId", ASCENDING)], unique=True)
        self.eventos.create_index([("TimeStamp", DESCENDING)])
        self.jugadores.create_index([("Id", ASCENDING)], unique=True)
        self.descargas.create_index([("fecha", DESCENDING)])
        self.seguidos.create_index([("jugador_id", ASCENDING)], unique=True)

    def guardar_eventos(self, eventos, servidor):
        """Guarda los eventos que no estuvieran ya. Devuelve cuántos son nuevos."""
        nuevos = 0
        for evento in eventos:
            # $setOnInsert solo escribe si el evento NO existía (upsert=True lo crea).
            # Así, si el worker descarga el mismo evento dos veces, no se duplica.
            resultado = self.eventos.update_one(
                {"EventId": evento["EventId"]},
                {"$setOnInsert": {**evento, "_servidor": servidor, "_descargado": ahora()}},
                upsert=True,
            )
            if resultado.upserted_id is not None:
                nuevos += 1
        return nuevos

    def guardar_jugador(self, jugador, servidor):
        """Guarda (o actualiza) la ficha de un jugador."""
        documento = {**jugador, "_servidor": servidor, "_actualizado": ahora()}
        self.jugadores.replace_one({"Id": jugador["Id"]}, documento, upsert=True)

    def registrar_descarga(self, tipo, jugador_id, recibidos, nuevos):
        """Apunta qué se ha descargado. Útil para depurar el worker."""
        self.descargas.insert_one({
            "fecha": ahora(),
            "tipo": tipo,  # "kills", "muertes", "recientes"...
            "jugador_id": jugador_id,
            "recibidos": recibidos,
            "nuevos": nuevos,
        })

    # ------------------------------------------------------------------
    # Jugadores seguidos
    # ------------------------------------------------------------------

    def seguir(self, jugador, servidor):
        """Empieza a seguir a un jugador. Devuelve False si ya se seguía."""
        resultado = self.seguidos.update_one(
            {"jugador_id": jugador["Id"]},
            {
                "$set": {"nombre": jugador["Name"], "nombre_min": jugador["Name"].lower(),
                         "servidor": servidor},
                "$setOnInsert": {"desde": ahora(), "ultima_consulta": None,
                                 "ultimo_error": None},
            },
            upsert=True,
        )
        return resultado.upserted_id is not None

    def dejar_de_seguir(self, nombre):
        """Deja de seguir a un jugador por su nombre. Devuelve False si no se seguía."""
        resultado = self.seguidos.delete_one({"nombre_min": nombre.lower()})
        return resultado.deleted_count == 1

    def listar_seguidos(self):
        return list(self.seguidos.find({}, {"_id": 0}).sort("nombre_min", ASCENDING))

    def marcar_consultado(self, jugador_id, error=None):
        """Apunta cuándo se consultó un jugador y si hubo error (None = todo bien)."""
        self.seguidos.update_one(
            {"jugador_id": jugador_id},
            {"$set": {"ultima_consulta": ahora(), "ultimo_error": error}},
        )

    def contar_eventos(self):
        return self.eventos.count_documents({})


def conectar_mongo():
    """Crea el almacén con los datos del .env. Devuelve None si MongoDB no responde."""
    almacen = AlmacenMongo(config.MONGO_URI, config.MONGO_BD)
    try:
        almacen.crear_indices()
    except PyMongoError:
        print(f"No se puede conectar a MongoDB en {config.MONGO_URI}.")
        print("¿Está arrancado? Con Docker: 'docker compose up -d'")
        return None
    return almacen
