"""ETL: lee los datos en bruto de MongoDB y los pasa limpios a MySQL.

- Extraer:    los eventos de Mongo que aún no se han cargado.
- Transformar: cada evento (un JSON enorme) se convierte en filas sencillas.
- Cargar:     las filas se insertan en MySQL y el evento se marca como cargado.

Se puede ejecutar todas las veces que se quiera: lo que ya está no se duplica.

Uso:
    python -m tracker.etl          (solo los eventos nuevos)
    python -m tracker.etl --todo   (vuelve a procesar todos, por ejemplo tras cambiar el ETL)
"""

import argparse
import sys
from datetime import datetime

from tracker.almacen_mongo import conectar_mongo
from tracker.almacen_mysql import conectar_mysql

TAMANO_LOTE = 100  # cada cuántos eventos se hace commit

# ----------------------------------------------------------------------
# Transformar: funciones puras (sin base de datos), fáciles de probar
# ----------------------------------------------------------------------


def a_fecha(texto):
    """'2026-11-25T15:26:45.114877100Z' -> datetime(2026, 11, 25, 15, 26, 45).

    La API da 9 decimales en los segundos; nos quedamos con los segundos enteros.
    """
    if not texto:
        return None
    return datetime.fromisoformat(texto[:19])


def arma_de(jugador):
    """Tipo del arma principal, p. ej. 'T5_2H_LONGBOW', o None si no llevaba."""
    mano = (jugador.get("Equipment") or {}).get("MainHand")
    return mano["Type"] if mano else None


def fila_jugador(doc):
    """Ficha de la colección jugadores de Mongo -> fila de la tabla jugadores."""
    return {
        "id": doc["Id"],
        "nombre": doc["Name"],
        "gremio": doc.get("GuildName") or None,
        "servidor": doc["_servidor"],
        "kill_fame": doc.get("KillFame"),
        "death_fame": doc.get("DeathFame"),
        "actualizado": doc.get("_actualizado"),
    }


def transformar_evento(doc):
    """Un evento de Mongo -> (fila de eventos, filas de participaciones, jugadores que salen).

    Participantes de la API:
    - Killer:       el que da el golpe final  -> rol 'asesino'
    - Victim:       el que muere              -> rol 'victima'
    - Participants: todos los que hicieron daño o curaron, incluido el Killer
                    -> los que no son el Killer tienen rol 'asistente'
    """
    servidor = doc["_servidor"]
    event_id = doc["EventId"]
    asesino = doc["Killer"]
    victima = doc["Victim"]
    participantes = doc.get("Participants") or []

    evento = {
        "event_id": event_id,
        "fecha": a_fecha(doc["TimeStamp"]),
        "servidor": servidor,
        "fama_total": doc.get("TotalVictimKillFame") or 0,
        "num_participantes": doc.get("numberOfParticipants") or len(participantes),
        "tam_grupo": doc.get("groupMemberCount") or 1,
        "zona": doc.get("KillArea"),
        "batalla_id": doc.get("BattleId"),
    }

    # Daño hecho por cada participante, para ponérselo también al asesino.
    dano_por_jugador = {p["Id"]: p.get("DamageDone") for p in participantes}

    def participacion(jugador, rol):
        return {
            "event_id": event_id,
            "jugador_id": jugador["Id"],
            "rol": rol,
            "ip_media": round(jugador.get("AverageItemPower") or 0, 2),
            "arma": arma_de(jugador),
            "dano": dano_por_jugador.get(jugador["Id"]) if rol != "victima" else None,
        }

    participaciones = [participacion(asesino, "asesino"), participacion(victima, "victima")]
    for p in participantes:
        if p["Id"] != asesino["Id"]:
            participaciones.append(participacion(p, "asistente"))

    # Todos los jugadores que salen en el evento, sin repetir, para la tabla jugadores.
    jugadores = {}
    for j in [asesino, victima, *participantes]:
        jugadores[j["Id"]] = {"id": j["Id"], "nombre": j["Name"],
                              "gremio": j.get("GuildName") or None, "servidor": servidor}

    return evento, participaciones, list(jugadores.values())


# ----------------------------------------------------------------------
# Extraer y cargar
# ----------------------------------------------------------------------


def cargar(mongo, mysql, todo=False):
    """Pasa los jugadores y los eventos de Mongo a MySQL. Devuelve un resumen."""
    resumen = {"jugadores": 0, "eventos_nuevos": 0, "eventos_repetidos": 0, "errores": 0}

    # 1. Las fichas completas de jugadores (son pocas, se cargan siempre todas).
    for doc in mongo.jugadores.find():
        mysql.guardar_jugador(fila_jugador(doc))
        resumen["jugadores"] += 1
    mysql.confirmar()

    # 2. Los eventos que aún no se han pasado a MySQL.
    filtro = {} if todo else {"_cargado_mysql": {"$ne": True}}
    pendientes = []  # EventId del lote actual, para marcarlos en Mongo tras el commit

    for doc in mongo.eventos.find(filtro).sort("EventId", 1):
        try:
            evento, participaciones, jugadores = transformar_evento(doc)
        except (KeyError, TypeError, ValueError) as error:
            # Un evento raro no debe parar el ETL: se avisa y se sigue.
            print(f"Evento {doc.get('EventId')} con un formato inesperado: {error!r}")
            resumen["errores"] += 1
            continue

        for jugador in jugadores:
            mysql.guardar_jugador_si_no_existe(jugador)
        if mysql.guardar_evento(evento, participaciones):
            resumen["eventos_nuevos"] += 1
        else:
            resumen["eventos_repetidos"] += 1
        pendientes.append(doc["EventId"])

        if len(pendientes) >= TAMANO_LOTE:
            _cerrar_lote(mongo, mysql, pendientes)
            pendientes = []

    _cerrar_lote(mongo, mysql, pendientes)
    return resumen


def _cerrar_lote(mongo, mysql, event_ids):
    """Commit en MySQL y, solo si ha ido bien, marca los eventos como cargados en Mongo."""
    if not event_ids:
        return
    mysql.confirmar()
    mongo.eventos.update_many({"EventId": {"$in": event_ids}},
                              {"$set": {"_cargado_mysql": True}})


def main():
    parser = argparse.ArgumentParser(description="Pasa los datos de MongoDB a MySQL")
    parser.add_argument("--todo", action="store_true",
                        help="vuelve a procesar todos los eventos, no solo los nuevos")
    args = parser.parse_args()

    mongo = conectar_mongo()
    mysql = conectar_mysql()
    if mongo is None or mysql is None:
        return 1

    mysql.crear_tablas()
    try:
        resumen = cargar(mongo, mysql, todo=args.todo)
    except Exception:
        mysql.deshacer()
        raise

    print(f"Jugadores actualizados: {resumen['jugadores']}")
    print(f"Eventos nuevos en MySQL: {resumen['eventos_nuevos']} "
          f"(ya estaban: {resumen['eventos_repetidos']}, con errores: {resumen['errores']})")
    print(f"Total en MySQL: {mysql.contar('eventos')} eventos, "
          f"{mysql.contar('participaciones')} participaciones, "
          f"{mysql.contar('jugadores')} jugadores")
    return 0


if __name__ == "__main__":
    sys.exit(main())
