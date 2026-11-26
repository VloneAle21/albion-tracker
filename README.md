# Albion Tracker

Tracker de jugadores de Albion Online: busca un jugador, guarda su historial de
kills y muertes, saca estadísticas propias y compara jugadores.

El plan completo del proyecto, con el reparto de tareas, está en [PLAN.md](PLAN.md).

## Estado

- [x] Fase 1: cliente de la API (`tracker/albion_api.py`)
- [x] Fase 2: guardado en bruto en MongoDB (`tracker/almacen_mongo.py`)
- [x] Fase 3: worker y jugadores seguidos (`tracker/worker.py`, `tracker/seguidos.py`)
- [x] Fase 4: ETL a MySQL (`tracker/etl.py`, `tracker/almacen_mysql.py`, `sql/esquema.sql`)
- [x] Fase 5: estadísticas (`tracker/estadisticas.py`)
- [x] Fase 6: web en Streamlit (`app.py`, `tracker/graficos.py`)
- [ ] Fase 7: Docker completo y entrega

## Arrancar todo con Docker (lo más fácil)

Solo hace falta Docker Desktop.

```powershell
copy .env.example .env      # y cambiad las contraseñas
docker compose up -d --build
```

Se levantan cuatro contenedores: `mongo`, `mysql`, `worker` y `web`. La web queda en
http://localhost:8501. El worker arranca solo y vuelve a arrancar si se cae o si se
reinicia el ordenador (con Docker Desktop abierto).

```powershell
docker compose ps                 # ver qué está funcionando
docker compose logs -f worker     # ver lo que hace el worker (Ctrl+C para salir)
docker compose down               # pararlo todo (los datos se conservan)
docker compose down -v            # pararlo todo y BORRAR los datos
```

Para seguir a un jugador, usad la página **Seguidos** de la web, o:

```powershell
docker compose exec worker python -m tracker.seguidos agregar NombreDelJugador
```

Si los puertos 27017, 3306 u 8501 ya están ocupados en vuestro ordenador, cambiadlos
en `.env` (`DOCKER_PUERTO_MONGO`, `DOCKER_PUERTO_MYSQL`, `DOCKER_PUERTO_WEB`).

## Puesta en marcha sin Docker (para desarrollar)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
copy .env.example .env
```

Hacen falta MongoDB y MySQL (o MariaDB). Hay dos opciones:

- **Con Docker Desktop**: `docker compose up -d mongo mysql` levanta solo las dos bases
  de datos (en los puertos de `DOCKER_PUERTO_*`) y crea el usuario de MySQL con los
  datos de `.env`. Poned esos puertos en `MONGO_URI` y `MYSQL_PORT`.
- **Instalados en el ordenador**: MongoDB no necesita nada. Para MySQL/MariaDB, copiad
  `sql/crear_usuario.example.sql` como `sql/crear_usuario.sql`, poned la contraseña
  de `.env` y ejecutadlo como root:

  ```powershell
  mysql -u root -p -e "source sql/crear_usuario.sql"
  ```

MongoDB también puede estar en MongoDB Atlas (gratis): basta con poner su URL en `MONGO_URI`.

### MariaDB propia del proyecto (sin tocar la del sistema)

Si tenéis MariaDB instalado pero no queréis usar la base de datos del sistema (o no
sabéis la contraseña de root), podéis crear otra solo para el proyecto en el puerto 3307:

```powershell
& 'C:\Program Files\MariaDB 11.7\bin\mysql_install_db.exe' --datadir=C:\albion-db --port=3307 --password=CONTRASEÑA_DE_ROOT
```

Añadid `bind-address=127.0.0.1` debajo de `port=3307` en `C:\albion-db\my.ini`, para
que solo se pueda entrar desde vuestro ordenador, y arrancadla (dejad la ventana abierta):

```powershell
& 'C:\Program Files\MariaDB 11.7\bin\mysqld.exe' --defaults-file=C:\albion-db\my.ini --console
```

Después, ejecutad `sql/crear_usuario.sql` como root en esa instancia y poned en `.env`
`MYSQL_HOST=127.0.0.1` y `MYSQL_PORT=3307`.

Usad una carpeta con una ruta corta, como `C:\albion-db`. Con rutas muy largas
(más de unos 150 caracteres), Windows no deja crear los archivos y falla con
`Can't write to mysqld's stdin`.

Si se pierde la base de datos de MySQL no pasa nada: los datos en bruto siguen en
MongoDB y `python -m tracker.etl --todo` la reconstruye entera.

## Uso

### Seguir jugadores y dejar el worker en marcha

```powershell
# Empezar a seguir a un jugador (hace ya la primera descarga)
python -m tracker.seguidos agregar NombreDelJugador
python -m tracker.seguidos agregar OtroJugador --servidor america

# Ver a quién se sigue, cuándo se consultó y si hubo errores
python -m tracker.seguidos lista

# Dejar de seguir (sus eventos guardados no se borran)
python -m tracker.seguidos quitar NombreDelJugador

# Worker: descarga a todos los seguidos cada 10 minutos (Ctrl+C para pararlo)
python -m tracker.worker
python -m tracker.worker --minutos 5
python -m tracker.worker --una-vez
```

El worker tiene que estar encendido el mayor tiempo posible: la API solo da las
10 últimas kills y muertes, y lo que no se descarga a tiempo se pierde.

Al final de cada ronda, el worker también pasa lo nuevo a MySQL (el ETL). Si MySQL
no está, sigue guardando en MongoDB y lo pasa cuando MySQL vuelva.

### Web

```powershell
streamlit run app.py
```

Se abre en http://localhost:8501 con tres páginas:

- **Perfil**: métricas, actividad por día, armas, mapa de calor de día y hora,
  rendimiento por hora, solo frente a grupo y últimos eventos.
- **Comparar**: hasta 4 jugadores en una tabla y en gráficas.
- **Seguidos**: a quién sigue el worker; seguir y dejar de seguir jugadores
  (al seguir a uno se descargan ya sus datos y se pasan a MySQL).

Si cambiáis un módulo de `tracker/`, reiniciad Streamlit (Ctrl+C y otra vez
`streamlit run app.py`): al recargar la página solo se vuelve a leer `app.py`.

### Estadísticas por terminal

```powershell
# Informe de un jugador: K/D, fama, rachas, armas, mejores horas, solo/grupo, Item Power
python -m tracker.estadisticas NombreDelJugador

# Comparar varios jugadores en una tabla
python -m tracker.estadisticas Jugador1 Jugador2
```

Las cifras son "desde que lo seguimos", no de toda la vida del jugador: la API no
da el historial antiguo. Las horas se muestran en hora de Madrid.

### Pasar los datos a MySQL (ETL)

```powershell
# Pasa a MySQL los eventos nuevos de MongoDB
python -m tracker.etl

# Vuelve a procesarlos todos (por ejemplo, después de cambiar el ETL)
python -m tracker.etl --todo
```

Se puede ejecutar todas las veces que se quiera: no duplica nada. Crea las tablas
de `sql/esquema.sql` si no existen.

### Descarga suelta

```powershell
# Descarga un jugador una vez y lo guarda en MongoDB
python -m tracker.descargar NombreDelJugador

# Solo mirar, sin guardar nada
python -m tracker.descargar NombreDelJugador --sin-guardar

# Otro servidor (europa, america o asia)
python -m tracker.descargar NombreDelJugador --servidor america
```

## Tests

```powershell
pytest
```

Los tests no necesitan internet ni MongoDB: usan una sesión HTTP falsa y `mongomock`.
El test del ETL con MySQL real usa la base `albion_tracker_test` y se salta si no hay conexión.

## Sobre la API de Albion

- No es oficial ni está documentada. Es la que usa la killboard de la web.
- Servidores: `gameinfo-ams` (Europa), `gameinfo` (América) y `gameinfo-sgp` (Asia).
- Devuelve solo las 10 últimas kills y muertes de cada jugador, y dos llamadas
  seguidas pueden devolver eventos distintos. Por eso se guarda todo y se
  deduplica por `EventId`.
- `/events` admite como mucho `limit=51`.
- Hacemos 1 petición por segundo como máximo y reintentamos si la API falla.
