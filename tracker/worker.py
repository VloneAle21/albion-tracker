"""Worker: cada X minutos descarga las kills y muertes de los jugadores seguidos.

La API solo da las 10 últimas kills y muertes de cada jugador, así que el worker
tiene que estar siempre encendido para no perder eventos.

Al final de cada ronda pasa lo nuevo a MySQL (el ETL). Si MySQL no está, sigue
guardando en MongoDB y avisa; el ETL se puede ejecutar a mano más tarde.

Uso:
    python -m tracker.worker              (se queda en marcha; Ctrl+C para pararlo)
    python -m tracker.worker --minutos 5
    python -m tracker.worker --una-vez    (una sola ronda, útil para probar)
"""

import argparse
import logging
import sys
import time

import pymysql
from pymongo.errors import PyMongoError

from tracker import config
from tracker.albion_api import AlbionApi, ErrorApiAlbion
from tracker.almacen_mongo import conectar_mongo
from tracker.almacen_mysql import conectar_mysql
from tracker.etl import cargar
from tracker.sincronizar import sincronizar_jugador

log = logging.getLogger("worker")


class Worker:
    def __init__(self, almacen, crear_api=AlbionApi, mysql=None):
        self.almacen = almacen
        self.mysql = mysql  # None = sin MySQL, solo se guarda en MongoDB
        # crear_api es la clase AlbionApi; en los tests se cambia por una API falsa.
        self.crear_api = crear_api
        self.apis = {}  # una API por servidor: {"europa": AlbionApi("europa"), ...}

    def api_de(self, servidor):
        if servidor not in self.apis:
            self.apis[servidor] = self.crear_api(servidor)
        return self.apis[servidor]

    def ronda(self):
        """Consulta una vez a todos los seguidos. Devuelve cuántos eventos nuevos hay."""
        seguidos = self.almacen.listar_seguidos()
        if not seguidos:
            log.info("No hay jugadores seguidos. Añade uno con: "
                     "python -m tracker.seguidos agregar Nombre")
            return 0

        total_nuevos = 0
        for seguido in seguidos:
            nombre = seguido["nombre"]
            jugador_id = seguido["jugador_id"]
            try:
                resultado = sincronizar_jugador(
                    self.api_de(seguido["servidor"]), self.almacen, jugador_id)
            except ErrorApiAlbion as error:
                # Un jugador que falla no debe parar al resto.
                log.warning("%s: la API ha fallado (%s)", nombre, error)
                self.almacen.marcar_consultado(jugador_id, error=str(error))
                continue

            self.almacen.marcar_consultado(jugador_id)
            nuevos = resultado["nuevas_kills"] + resultado["nuevas_muertes"]
            total_nuevos += nuevos
            log.info("%s: %d kills y %d muertes nuevas", nombre,
                     resultado["nuevas_kills"], resultado["nuevas_muertes"])

        log.info("Ronda terminada: %d jugadores, %d eventos nuevos",
                 len(seguidos), total_nuevos)
        return total_nuevos

    def pasar_a_mysql(self):
        """Ejecuta el ETL con lo nuevo de esta ronda. Un fallo de MySQL no para el worker."""
        if self.mysql is None:
            return
        try:
            # Si la conexión se ha cortado (MySQL reiniciado, mucho tiempo parado...), reconecta.
            self.mysql.asegurar_conexion()
            resumen = cargar(self.almacen, self.mysql)
        except pymysql.MySQLError as error:
            log.error("MySQL ha fallado, se reintentará en la siguiente ronda: %s", error)
            return
        log.info("ETL: %d eventos nuevos en MySQL", resumen["eventos_nuevos"])

    def ejecutar(self, minutos, una_vez=False):
        """Hace rondas cada `minutos` minutos hasta que se pulse Ctrl+C."""
        log.info("Worker en marcha: una ronda cada %d minutos", minutos)
        try:
            while True:
                inicio = time.monotonic()
                try:
                    self.ronda()
                    self.pasar_a_mysql()
                except PyMongoError as error:
                    # Si Mongo se cae, se avisa y se prueba en la siguiente ronda.
                    log.error("MongoDB no responde: %s", error)

                if una_vez:
                    return

                # Se descuenta lo que ha tardado la ronda para que el ritmo sea fijo.
                espera = max(0, minutos * 60 - (time.monotonic() - inicio))
                log.info("Siguiente ronda dentro de %d segundos", espera)
                time.sleep(espera)
        except KeyboardInterrupt:
            log.info("Worker parado")


def main():
    parser = argparse.ArgumentParser(description="Descarga periódica de jugadores seguidos")
    parser.add_argument("--minutos", type=int, default=config.WORKER_MINUTOS)
    parser.add_argument("--una-vez", action="store_true", help="hace una sola ronda")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S")

    almacen = conectar_mongo()
    if almacen is None:
        return 1

    mysql = conectar_mysql()
    if mysql is None:
        log.warning("Sin MySQL: los eventos solo se guardarán en MongoDB")
    else:
        mysql.crear_tablas()  # en un MySQL nuevo (p. ej. con Docker) aún no existen

    Worker(almacen, mysql=mysql).ejecutar(args.minutos, una_vez=args.una_vez)
    return 0


if __name__ == "__main__":
    sys.exit(main())
