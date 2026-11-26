"""Guarda los datos limpios en MySQL (o MariaDB).

Tablas (ver sql/esquema.sql):
- jugadores:        un jugador por fila.
- eventos:          un evento de muerte por fila.
- participaciones:  quién participó en cada evento y cómo (asesino, víctima o asistente).
"""

from pathlib import Path

import pymysql

from tracker import config

ESQUEMA = Path(__file__).resolve().parent.parent / "sql" / "esquema.sql"


class AlmacenMysql:
    def __init__(self, conexion):
        self.conexion = conexion

    def crear_tablas(self):
        """Ejecuta sql/esquema.sql. Si las tablas ya existen, no hace nada."""
        sql = ESQUEMA.read_text(encoding="utf-8")
        # Se quitan los comentarios y se ejecuta cada sentencia por separado.
        lineas = [linea for linea in sql.splitlines() if not linea.strip().startswith("--")]
        sentencias = [s.strip() for s in "\n".join(lineas).split(";") if s.strip()]
        with self.conexion.cursor() as cursor:
            for sentencia in sentencias:
                cursor.execute(sentencia)
        self.conexion.commit()

    def guardar_jugador(self, fila):
        """Inserta un jugador o, si ya existe, actualiza sus datos."""
        sql = """
            INSERT INTO jugadores (id, nombre, gremio, servidor, kill_fame, death_fame, actualizado)
            VALUES (%(id)s, %(nombre)s, %(gremio)s, %(servidor)s,
                    %(kill_fame)s, %(death_fame)s, %(actualizado)s)
            ON DUPLICATE KEY UPDATE
                nombre = VALUES(nombre), gremio = VALUES(gremio),
                kill_fame = VALUES(kill_fame), death_fame = VALUES(death_fame),
                actualizado = VALUES(actualizado)
        """
        with self.conexion.cursor() as cursor:
            cursor.execute(sql, fila)

    def guardar_jugador_si_no_existe(self, fila):
        """Para los jugadores que solo conocemos por aparecer en un evento.

        INSERT IGNORE no toca a los que ya están, así no se pisa una ficha completa.
        """
        sql = """
            INSERT IGNORE INTO jugadores (id, nombre, gremio, servidor)
            VALUES (%(id)s, %(nombre)s, %(gremio)s, %(servidor)s)
        """
        with self.conexion.cursor() as cursor:
            cursor.execute(sql, fila)

    def guardar_evento(self, evento, participaciones):
        """Guarda un evento y sus participaciones. Devuelve False si el evento ya estaba."""
        sql_evento = """
            INSERT IGNORE INTO eventos (event_id, fecha, servidor, fama_total,
                                        num_participantes, tam_grupo, zona, batalla_id)
            VALUES (%(event_id)s, %(fecha)s, %(servidor)s, %(fama_total)s,
                    %(num_participantes)s, %(tam_grupo)s, %(zona)s, %(batalla_id)s)
        """
        sql_participacion = """
            INSERT IGNORE INTO participaciones (event_id, jugador_id, rol, ip_media, arma, dano)
            VALUES (%(event_id)s, %(jugador_id)s, %(rol)s, %(ip_media)s, %(arma)s, %(dano)s)
        """
        with self.conexion.cursor() as cursor:
            insertados = cursor.execute(sql_evento, evento)
            cursor.executemany(sql_participacion, participaciones)
        return insertados == 1

    def asegurar_conexion(self):
        """Comprueba que la conexión sigue viva y, si no, vuelve a conectar."""
        self.conexion.ping(reconnect=True)

    def confirmar(self):
        """Hace commit: hasta aquí, nada de lo guardado es definitivo."""
        self.conexion.commit()

    def deshacer(self):
        self.conexion.rollback()

    def contar(self, tabla):
        if tabla not in ("jugadores", "eventos", "participaciones"):
            raise ValueError(f"Tabla desconocida: {tabla}")
        with self.conexion.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) FROM {tabla}")
            return cursor.fetchone()[0]


def conectar_mysql(nombre_bd=None):
    """Crea el almacén con los datos del .env. Devuelve None si MySQL no responde."""
    try:
        conexion = pymysql.connect(
            host=config.MYSQL_HOST, port=config.MYSQL_PORT,
            user=config.MYSQL_USER, password=config.MYSQL_PASSWORD,
            database=nombre_bd or config.MYSQL_BD, charset="utf8mb4",
            connect_timeout=5,
        )
    except pymysql.MySQLError as error:
        print(f"No se puede conectar a MySQL en {config.MYSQL_HOST}:{config.MYSQL_PORT} "
              f"con el usuario '{config.MYSQL_USER}': {error.args[-1]}")
        print("Revisa MYSQL_USER y MYSQL_PASSWORD en .env (y sql/crear_usuario.example.sql).")
        return None
    return AlmacenMysql(conexion)
