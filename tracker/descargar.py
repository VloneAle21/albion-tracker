"""Descarga un jugador con sus kills y muertes y lo guarda en MongoDB (una sola vez).

Para que se descargue solo cada X minutos, usa tracker.seguidos y tracker.worker.

Uso:
    python -m tracker.descargar NombreDelJugador
    python -m tracker.descargar NombreDelJugador --servidor america
    python -m tracker.descargar NombreDelJugador --sin-guardar   (solo muestra, sin Mongo)
"""

import argparse
import sys

from tracker import config
from tracker.albion_api import AlbionApi, ErrorApiAlbion
from tracker.almacen_mongo import conectar_mongo
from tracker.sincronizar import sincronizar_jugador


def mostrar_evento(evento, jugador_id):
    asesino = evento["Killer"]
    victima = evento["Victim"]
    if asesino["Id"] == jugador_id:
        texto = f"MATA a {victima['Name']}"
    else:
        texto = f"MUERE contra {asesino['Name']}"
    fecha = evento["TimeStamp"][:16].replace("T", " ")
    print(f"  {fecha}  {texto:<35} fama {evento['TotalVictimKillFame']:>8}")


def main():
    parser = argparse.ArgumentParser(description="Descarga un jugador de Albion Online")
    parser.add_argument("nombre")
    parser.add_argument("--servidor", default=config.ALBION_SERVIDOR)
    parser.add_argument("--sin-guardar", action="store_true",
                        help="no usa MongoDB, solo muestra los datos")
    args = parser.parse_args()

    api = AlbionApi(args.servidor)
    almacen = None
    if not args.sin_guardar:
        almacen = conectar_mongo()
        if almacen is None:
            return 1

    try:
        jugador = api.buscar_jugador(args.nombre)
        if jugador is None:
            print(f"No hay ningún jugador llamado '{args.nombre}' en {args.servidor}.")
            return 1

        if almacen:
            resultado = sincronizar_jugador(api, almacen, jugador["Id"])
            ficha, kills, muertes = resultado["ficha"], resultado["kills"], resultado["muertes"]
        else:
            ficha = api.jugador(jugador["Id"])
            kills = api.kills(jugador["Id"])
            muertes = api.muertes(jugador["Id"])
    except ErrorApiAlbion as error:
        print(f"La API de Albion ha fallado: {error}")
        return 1

    # Si la ficha completa falla, nos quedamos con los datos de la búsqueda.
    ficha = ficha or jugador
    gremio = ficha.get("GuildName") or "sin gremio"
    print(f"{ficha['Name']} ({gremio})  fama de kills: {ficha['KillFame']}  "
          f"fama de muertes: {ficha['DeathFame']}")
    print(f"Eventos recientes: {len(kills)} kills, {len(muertes)} muertes")
    for evento in sorted(kills + muertes, key=lambda e: e["TimeStamp"], reverse=True):
        mostrar_evento(evento, jugador["Id"])

    if almacen:
        nuevos = resultado["nuevas_kills"] + resultado["nuevas_muertes"]
        print(f"\nGuardado en MongoDB: {nuevos} eventos nuevos "
              f"({almacen.contar_eventos()} en total).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
