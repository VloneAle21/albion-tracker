"""Descarga un jugador de la API y lo guarda en MongoDB.

La usan el worker, el comando de seguidos y el script de descarga, para que
la lógica esté en un solo sitio.
"""


def sincronizar_jugador(api, almacen, jugador_id):
    """Descarga la ficha, las kills y las muertes de un jugador y las guarda.

    Devuelve un diccionario con lo descargado y cuántos eventos eran nuevos.
    Si la API falla, lanza ErrorApiAlbion y no guarda nada de este jugador.
    """
    # Primero se descarga todo y luego se guarda: si falla una de las tres
    # peticiones, no queda el jugador guardado a medias.
    ficha = api.jugador(jugador_id)
    kills = api.kills(jugador_id)
    muertes = api.muertes(jugador_id)

    if ficha:
        almacen.guardar_jugador(ficha, api.servidor)

    nuevas_kills = almacen.guardar_eventos(kills, api.servidor)
    nuevas_muertes = almacen.guardar_eventos(muertes, api.servidor)
    almacen.registrar_descarga("kills", jugador_id, len(kills), nuevas_kills)
    almacen.registrar_descarga("muertes", jugador_id, len(muertes), nuevas_muertes)

    return {
        "ficha": ficha,
        "kills": kills,
        "muertes": muertes,
        "nuevas_kills": nuevas_kills,
        "nuevas_muertes": nuevas_muertes,
    }
