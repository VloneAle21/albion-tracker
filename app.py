"""Web del Albion Tracker (Streamlit).

Arrancar con:
    streamlit run app.py

Tres páginas:
- Perfil:    estadísticas y gráficas de un jugador.
- Comparar:  varios jugadores en la misma tabla.
- Seguidos:  a quién sigue el worker; añadir y quitar jugadores.
"""

from datetime import timezone

import streamlit as st

from tracker import estadisticas as est
from tracker import graficos
from tracker.almacen_mongo import conectar_mongo
from tracker.almacen_mysql import conectar_mysql
from tracker.etl import cargar
from tracker.seguidos import seguir_jugador

st.set_page_config(page_title="Albion Tracker", page_icon="⚔️", layout="wide")


# ----------------------------------------------------------------------
# Conexiones y datos
# ----------------------------------------------------------------------

@st.cache_resource
def mongo():
    """Una sola conexión a Mongo para toda la web (pymongo se puede compartir)."""
    almacen = conectar_mongo()
    if almacen is None:
        # Se lanza un error en vez de devolver None para que Streamlit no lo guarde en caché.
        raise ConnectionError("MongoDB no responde")
    return almacen


def abrir_mysql():
    """Una conexión nueva a MySQL cada vez (PyMySQL no se debe compartir entre usuarios)."""
    almacen = conectar_mysql()
    if almacen is None:
        st.error("No se puede conectar a MySQL. Revisa que esté arrancado y los datos de `.env`.")
        st.stop()
    tablas_creadas(almacen)
    return almacen


@st.cache_resource
def tablas_creadas(_almacen):
    """Crea las tablas la primera vez (en un MySQL nuevo aún no existen).

    cache_resource hace que solo se ejecute una vez; el _ delante del parámetro
    le dice a Streamlit que no lo use para la caché.
    """
    _almacen.crear_tablas()
    return True


# ttl=60: los datos se guardan un minuto; así la web va rápida y se actualiza sola.
@st.cache_data(ttl=60)
def lista_jugadores():
    mysql = abrir_mysql()
    try:
        return est.jugadores_con_datos(mysql.conexion)
    finally:
        mysql.conexion.close()


@st.cache_data(ttl=60)
def eventos_de(jugador_id):
    mysql = abrir_mysql()
    try:
        return est.cargar_eventos_jugador(mysql.conexion, jugador_id)
    finally:
        mysql.conexion.close()


def seguidos():
    try:
        return mongo().listar_seguidos()
    except ConnectionError:
        st.error("No se puede conectar a MongoDB. ¿Está arrancado?")
        st.stop()


def hora_local(fecha_utc):
    if fecha_utc is None:
        return "nunca"
    return fecha_utc.replace(tzinfo=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")


def opciones_de_jugadores():
    """{texto que se ve: id}. Primero los seguidos, luego el resto por número de eventos."""
    jugadores = lista_jugadores()
    ids_seguidos = {s["jugador_id"] for s in seguidos()}
    jugadores = jugadores.assign(seguido=jugadores["id"].isin(ids_seguidos))
    jugadores = jugadores.sort_values(["seguido", "eventos"], ascending=False)
    opciones = {}
    for fila in jugadores.itertuples():
        marca = "★ " if fila.seguido else ""
        opciones[f"{marca}{fila.nombre} ({fila.eventos} eventos)"] = fila.id
    return opciones, ids_seguidos


def mostrar(fig):
    # theme=None: que Streamlit no cambie nuestros colores.
    st.plotly_chart(fig, theme=None, config={"displayModeBar": False})


# ----------------------------------------------------------------------
# Página: perfil
# ----------------------------------------------------------------------

def pagina_perfil():
    st.title("Perfil de jugador")
    opciones, ids_seguidos = opciones_de_jugadores()
    if not opciones:
        st.info("Todavía no hay datos. Sigue a algún jugador en la página **Seguidos**.")
        return

    elegido = st.selectbox("Jugador", list(opciones), help="★ = jugadores que sigue el worker")
    jugador_id = opciones[elegido]
    df = eventos_de(jugador_id)
    r = est.resumen(df)

    st.caption(f"Datos desde el {r['desde']:%d/%m/%Y %H:%M} hasta el {r['hasta']:%d/%m/%Y %H:%M}, "
               "en hora de Madrid. Solo cuenta lo que ha guardado el worker.")
    if jugador_id not in ids_seguidos:
        st.info("A este jugador no se le sigue: solo aparecen los eventos en los que coincidió "
                "con un jugador seguido. Síguelo en **Seguidos** para tener todos sus datos.")

    racha = est.rachas(df)
    ip = est.item_power(df)
    fila1 = st.columns(4)
    fila1[0].metric("Kills", r["kills"])
    fila1[1].metric("Muertes", r["muertes"])
    fila1[2].metric("K/D", r["kd"])
    fila1[3].metric("Ratio de fama", r["ratio_fama"],
                    help="Fama de las víctimas que mató entre la fama que dio al morir")
    fila2 = st.columns(4)
    fila2[0].metric("Mejor racha", racha["mejor"], help="Kills seguidas sin morir")
    fila2[1].metric("Racha actual", racha["actual"], help="Kills desde su última muerte")
    fila2[2].metric("Item Power al matar", ip["ip_kills"] or "-")
    fila2[3].metric("Item Power al morir", ip["ip_muertes"] or "-")

    st.subheader("Actividad por día")
    mostrar(graficos.por_dia(est.por_dia(df)))

    izquierda, derecha = st.columns(2)
    with izquierda:
        st.subheader("Armas")
        tabla_armas = est.por_arma(df)
        mostrar(graficos.armas(tabla_armas))
        with st.expander("Ver la tabla de armas"):
            st.dataframe(tabla_armas)
    with derecha:
        st.subheader("¿Cuándo mata?")
        st.caption("Kills por día de la semana y hora")
        mostrar(graficos.mapa_calor(est.mapa_calor(df)))

    st.subheader("Por hora del día")
    tabla_horas = est.por_hora(df)
    mostrar(graficos.por_hora(tabla_horas))
    mejores = est.mejores_horas(df)
    if len(mejores):
        texto = ", ".join(f"{h:02d}h (K/D {fila.kd})" for h, fila in mejores.iterrows())
        st.write(f"**Mejores horas** (K/D de 1 o más, con al menos 3 eventos): {texto}")
    else:
        st.write("**Mejores horas:** todavía no hay ninguna hora con K/D de 1 o más "
                 "y al menos 3 eventos.")

    st.subheader("Solo frente a grupo")
    grupos = est.por_grupo(df)
    izquierda, derecha = st.columns(2)
    with izquierda:
        st.markdown("**Kills**, según el tamaño de su grupo")
        mostrar(graficos.una_serie(grupos.index, grupos["kills (su grupo)"],
                                   graficos.KILLS, "kills"))
    with derecha:
        st.markdown("**Muertes**, según el tamaño del grupo enemigo")
        mostrar(graficos.una_serie(grupos.index, grupos["muertes (grupo enemigo)"],
                                   graficos.MUERTES, "muertes"))

    st.subheader("Últimos eventos")
    st.dataframe(est.ultimos_eventos(df), hide_index=True)


# ----------------------------------------------------------------------
# Página: comparar
# ----------------------------------------------------------------------

def pagina_comparar():
    st.title("Comparar jugadores")
    opciones, ids_seguidos = opciones_de_jugadores()
    por_defecto = [texto for texto, id in opciones.items() if id in ids_seguidos][:2]
    elegidos = st.multiselect("Jugadores (hasta 4)", list(opciones), default=por_defecto,
                              max_selections=4)
    if len(elegidos) < 2:
        st.info("Elige al menos dos jugadores.")
        return

    # El nombre sin la estrella ni el número de eventos
    datos = {texto.lstrip("★ ").rsplit(" (", 1)[0]: eventos_de(opciones[texto])
             for texto in elegidos}
    tabla = est.comparar(datos)

    st.dataframe(tabla.rename(columns={
        "kills": "Kills", "muertes": "Muertes", "kd": "K/D", "ratio_fama": "Ratio de fama",
        "mejor_racha": "Mejor racha", "arma_favorita": "Arma favorita",
        "ip_kills": "IP al matar", "ip_muertes": "IP al morir"}))

    izquierda, derecha = st.columns(2)
    with izquierda:
        st.subheader("K/D")
        mostrar(graficos.una_serie(tabla.index, tabla["kd"], graficos.KILLS, "de K/D"))
    with derecha:
        st.subheader("Kills y muertes")
        mostrar(graficos.comparar_kills_muertes(tabla))
    st.caption("Cada jugador cuenta desde que lo seguimos, así que puede haber más datos de uno "
               "que de otro.")


# ----------------------------------------------------------------------
# Página: seguidos
# ----------------------------------------------------------------------

def pagina_seguidos():
    st.title("Jugadores seguidos")
    st.write("El worker descarga sus kills y muertes cada pocos minutos. "
             "La API solo da los 10 últimos eventos, así que conviene seguirlos cuanto antes.")

    lista = seguidos()
    if lista:
        st.dataframe([{
            "Jugador": s["nombre"],
            "Servidor": s["servidor"],
            "Seguido desde": hora_local(s["desde"]),
            "Última consulta": hora_local(s["ultima_consulta"]),
            "Estado": f"Error: {s['ultimo_error']}" if s["ultimo_error"] else "OK",
        } for s in lista], hide_index=True)
    else:
        st.info("Todavía no sigues a nadie.")

    izquierda, derecha = st.columns(2)
    with izquierda:
        st.subheader("Seguir a un jugador")
        with st.form("seguir", clear_on_submit=True):
            nombre = st.text_input("Nombre exacto del jugador")
            servidor = st.selectbox("Servidor", ["europa", "america", "asia"])
            if st.form_submit_button("Seguir", type="primary") and nombre.strip():
                with st.spinner("Buscando y descargando..."):
                    ok, mensaje = seguir_jugador(mongo(), nombre.strip(), servidor)
                    if ok:
                        mysql = abrir_mysql()
                        try:
                            cargar(mongo(), mysql)  # para que salga ya en el perfil
                        finally:
                            mysql.conexion.close()
                        st.cache_data.clear()
                if ok:
                    # Se recarga para que la tabla de arriba ya lo incluya.
                    st.toast(mensaje)
                    st.rerun()
                st.error(mensaje)

    with derecha:
        st.subheader("Dejar de seguir")
        if lista:
            nombre = st.selectbox("Jugador", [s["nombre"] for s in lista], key="quitar")
            if st.button("Dejar de seguir"):
                mongo().dejar_de_seguir(nombre)
                # toast en vez de success: se sigue viendo después de recargar la página
                st.toast(f"Ya no sigues a {nombre}. Sus eventos guardados no se borran.")
                st.rerun()


# ----------------------------------------------------------------------

paginas = st.navigation([
    st.Page(pagina_perfil, title="Perfil", icon=":material/person:", default=True),
    st.Page(pagina_comparar, title="Comparar", icon=":material/compare_arrows:", url_path="comparar"),
    st.Page(pagina_seguidos, title="Seguidos", icon=":material/star:", url_path="seguidos"),
])
paginas.run()
