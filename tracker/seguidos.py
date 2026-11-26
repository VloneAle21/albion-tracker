"""Gestiona la lista de jugadores que sigue el worker.

Uso:
    python -m tracker.seguidos agregar NombreDelJugador [--servidor america]
    python -m tracker.seguidos quitar NombreDelJugador
    python -m tracker.seguidos lista
"""

import argparse
import sys
from datetime import timezone

from tracker import config
from tracker.albion_api import AlbionApi, ErrorApiAlbion
from tracker.almacen_mongo import conectar_mongo
from tracker.sincronizar import sincronizar_jugador


def seguir_jugador(almacen, nombre, servidor, api=None):
    """Busca al jugador, lo sigue y hace la primera descarga.

    Devuelve (ok, mensaje). La usan este comando y la web, cada uno muestra el mensaje a su manera.
    """
    api = api or AlbionApi(servidor)
    try:
        jugador = api.buscar_jugador(nombre)
    except ErrorApiAlbion as error:
        return False, f"La API de Albion ha fallado: {error}"
    if jugador is None:
        return False, f"No hay ningún jugador llamado '{nombre}' en {servidor}."

    if not almacen.seguir(jugador, servidor):
        return True, f"Ya seguías a {jugador['Name']}."

    # Primera descarga ahora, para no esperar a la siguiente ronda del worker.
    try:
        resultado = sincronizar_jugador(api, almacen, jugador["Id"])
    except ErrorApiAlbion as error:
        almacen.marcar_consultado(jugador["Id"], error=str(error))
        return True, (f"Ahora sigues a {jugador['Name']}, pero la primera descarga ha fallado "
                      f"({error}). El worker lo volverá a intentar.")

    almacen.marcar_consultado(jugador["Id"])
    return True, (f"Ahora sigues a {jugador['Name']} ({servidor}). "
                  f"Primera descarga: {resultado['nuevas_kills']} kills y "
                  f"{resultado['nuevas_muertes']} muertes nuevas.")


def agregar(almacen, nombre, servidor):
    ok, mensaje = seguir_jugador(almacen, nombre, servidor)
    print(mensaje)
    return 0 if ok else 1


def quitar(almacen, nombre):
    if almacen.dejar_de_seguir(nombre):
        print(f"Ya no sigues a {nombre}. Sus eventos guardados no se borran.")
        return 0
    print(f"No seguías a ningún jugador llamado '{nombre}'.")
    return 1


def lista(almacen):
    seguidos = almacen.listar_seguidos()
    if not seguidos:
        print("No sigues a nadie. Usa: python -m tracker.seguidos agregar Nombre")
        return 0

    print(f"{'Jugador':<20} {'Servidor':<9} {'Última consulta':<17} Estado")
    for s in seguidos:
        if s["ultima_consulta"]:
            # Mongo guarda la hora en UTC; se pasa a la hora local para mostrarla.
            hora_local = s["ultima_consulta"].replace(tzinfo=timezone.utc).astimezone()
            consulta = hora_local.strftime("%Y-%m-%d %H:%M")
        else:
            consulta = "nunca"
        estado = f"ERROR: {s['ultimo_error']}" if s["ultimo_error"] else "ok"
        print(f"{s['nombre']:<20} {s['servidor']:<9} {consulta:<17} {estado}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Jugadores que sigue el worker")
    acciones = parser.add_subparsers(dest="accion", required=True)

    p_agregar = acciones.add_parser("agregar", help="empezar a seguir a un jugador")
    p_agregar.add_argument("nombre")
    p_agregar.add_argument("--servidor", default=config.ALBION_SERVIDOR)

    p_quitar = acciones.add_parser("quitar", help="dejar de seguir a un jugador")
    p_quitar.add_argument("nombre")

    acciones.add_parser("lista", help="ver a quién se sigue")

    args = parser.parse_args()

    almacen = conectar_mongo()
    if almacen is None:
        return 1

    if args.accion == "agregar":
        return agregar(almacen, args.nombre, args.servidor)
    if args.accion == "quitar":
        return quitar(almacen, args.nombre)
    return lista(almacen)


if __name__ == "__main__":
    sys.exit(main())
