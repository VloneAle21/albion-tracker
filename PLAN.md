# Albion Tracker: plan del proyecto

Proyecto pensado para **dos alumnos de 2º de DAM**. Se busca un jugador de Albion
Online, la app va guardando sus kills y muertes, calcula estadísticas propias y
permite comparar jugadores.

## 1. Qué es una "partida" en Albion

Albion no tiene partidas como LoL. Lo que se registra es cada **evento de muerte**:
quién mató a quién, con qué equipo, cuánta fama dio, cuánta gente había en el grupo
y a qué hora. Ese evento es nuestra "partida".

La API **no es oficial**: es la que usa la killboard de la web. No pide clave, no
publica límites, a veces se cae y **solo devuelve las 10 últimas kills y las 10 últimas
muertes** de cada jugador. Además, dos llamadas seguidas pueden devolver eventos
distintos (lo hemos comprobado). Por eso necesitamos un proceso (el *worker*) que vaya consultando cada
pocos minutos y guardando el historial nosotros mismos.

## 2. Alcance

**Mínimo obligatorio (MVP)**

- Buscar un jugador por nombre y "seguirlo".
- Descargar sus kills y muertes cada X minutos sin duplicar eventos.
- Guardar las respuestas en bruto en MongoDB y los datos limpios en MySQL.
- Estadísticas:
  - K/D (kills y muertes) y ratio de fama.
  - Racha más larga de kills sin morir y racha actual.
  - Armas con mejor rendimiento (como "campeones con mejor winrate").
  - Horas y días en los que rinde mejor.
  - Solo frente a grupo.
  - Item Power medio en kills y en muertes.
- Comparar dos jugadores en la misma pantalla.
- Todo arranca con `docker compose up`.

**Extras, si sobra tiempo**

- Plata perdida y ganada, cruzando el equipo con los precios del mercado
  (API comunitaria del Albion Online Data Project).
- Estadísticas por gremio.
- Despliegue en un servidor en la nube con dominio.
- Bot de Discord que avise cuando un jugador seguido muere.

## 3. Tecnologías

| Pieza | Tecnología | Por qué |
|---|---|---|
| Lenguaje | Python 3.12 | Lo pide la idea del proyecto; `requests` y `pandas` son muy fáciles de usar |
| Llamadas a la API | `requests` | Lo más sencillo para HTTP |
| Datos en bruto | MongoDB + `pymongo` | El JSON se guarda tal cual, sin diseñar tablas |
| Datos limpios | MySQL 8 + `PyMySQL` | Ya lo conocéis de Bases de Datos; las estadísticas salen con SQL |
| Análisis | `pandas` | Agrupar y contar sin escribir bucles a mano |
| Interfaz | Streamlit + Plotly | Una web con gráficas en pocas líneas, sin HTML ni JavaScript |
| Contenedores | Docker Compose | Mongo, MySQL, worker y web se levantan con un comando |
| Tests | `pytest` (+ `mongomock`) | Probar sin internet y sin base de datos real |

No usamos FastAPI ni un frontend aparte: Streamlit lee directamente de MySQL y eso
basta para este proyecto.

## 4. Arquitectura

```
API de Albion ──► worker.py ──► MongoDB   (eventos y jugadores en bruto)
                                  │
                       etl.py ◄───┘
                         │
                         ▼
                       MySQL   (jugadores, eventos, participaciones)
                         │
                         ▼
               app.py (Streamlit) ──► el usuario
```

## 5. Modelo de datos

**MongoDB** (`albion_tracker`)

- `eventos`: cada evento tal cual llega de la API. Índice único en `EventId`.
- `jugadores`: la ficha de cada jugador tal cual llega. Índice único en `Id`.
- `descargas`: registro de cada descarga (qué se pidió, cuándo, cuántos eventos nuevos).
- `seguidos`: los jugadores que el worker tiene que consultar.

**MySQL** (`albion_tracker`)

```sql
jugadores(
  id VARCHAR(32) PRIMARY KEY, nombre VARCHAR(40), gremio VARCHAR(60),
  servidor VARCHAR(10), kill_fame BIGINT, death_fame BIGINT, actualizado DATETIME)

eventos(
  event_id BIGINT PRIMARY KEY, fecha DATETIME, servidor VARCHAR(10),
  fama_total INT, num_participantes INT, tam_grupo INT,
  zona VARCHAR(30), batalla_id BIGINT)

participaciones(
  event_id BIGINT, jugador_id VARCHAR(32),
  rol ENUM('asesino','victima','asistente'),
  ip_media DECIMAL(7,2), arma VARCHAR(60), dano DECIMAL(12,2),
  PRIMARY KEY (event_id, jugador_id, rol),
  FOREIGN KEY (event_id) REFERENCES eventos(event_id),
  FOREIGN KEY (jugador_id) REFERENCES jugadores(id))
```

Con estas tres tablas salen todas las estadísticas del MVP.

## 6. Reparto de tareas

Cada persona es responsable de su parte, pero **todo cambio lo revisa la otra persona**
con una Pull Request antes de unirlo a `main`.

| | Persona A: datos | Persona B: análisis y app |
|---|---|---|
| Sprint 1 | Cliente de la API + guardado en Mongo | Docker Compose, esquema MySQL, tablero de tareas en GitHub |
| Sprint 2 | Worker: seguir jugadores y descargar cada X min | Consultas SQL de prueba con datos de ejemplo |
| Sprint 3 | ETL Mongo → MySQL (repetible sin duplicar) | Funciones de estadísticas con `pandas` + tests |
| Sprint 4 | Robustez: errores, logs, caídas de la API | Web en Streamlit: buscador, perfil y comparador |
| Sprint 5 | Ayudar con extras / despliegue | Gráficas finales, README con capturas, presentación |

Sprints de **2 semanas** (unas 10 semanas en total). Al final de cada sprint se
hace una demo de lo que funciona.

## 7. Fases y qué hay que entregar

1. ✅ **Cliente de la API**: `tracker/albion_api.py`. Buscar jugador, ficha, kills,
   muertes y eventos, con pausa entre peticiones y reintentos. Tests sin internet.
2. ✅ **Guardado en Mongo**: `tracker/almacen_mongo.py`. Eventos sin duplicar por `EventId`.
3. ✅ **Worker**: `tracker/worker.py` recorre `seguidos` cada X minutos y ejecuta el ETL;
   `tracker/seguidos.py` para agregar, quitar y listar jugadores.
4. ✅ **ETL**: `tracker/etl.py` lee Mongo y rellena MySQL. Si se ejecuta dos veces, no duplica nada.
   Funciona también con MariaDB.
5. ✅ **Estadísticas**: `tracker/estadisticas.py`, una función por métrica, todas probadas
   con datos inventados. Las armas se agrupan por arma base (sin tier ni encantamiento).
   En "solo frente a grupo" las kills cuentan el grupo del jugador y las muertes el grupo
   enemigo (la API solo da el tamaño del grupo del asesino), así que no hay K/D por grupo.
6. ✅ **Web**: `app.py` (Streamlit) con perfil, comparador y gestión de seguidos;
   las gráficas están en `tracker/graficos.py`. Kills en azul y muertes en naranja
   en todas las gráficas (paleta comprobada para daltonismo).
7. **Docker y entrega**: `docker compose up` levanta todo; README con capturas.

**Arrancad el worker cuanto antes** (fase 3). Los eventos antiguos no se pueden
recuperar, así que cuanto antes empiece a guardar, más historial tendréis para la demo.

## 8. Normas del equipo

- Ramas: `main` siempre funciona. Cada tarea en su rama (`feature/worker`, `fix/reintentos`…).
- Commits pequeños y en castellano: "Añade reintentos al cliente de la API".
- Ninguna contraseña en el código: todo en `.env` (que no se sube a Git).
- Antes de abrir una PR: `pytest` en verde.

## 9. Riesgos

| Riesgo | Qué hacemos |
|---|---|
| La API se cae o va lenta | Reintentos con espera creciente; el worker no se para por un fallo |
| Nos bloquean por hacer demasiadas peticiones | Máximo 1 petición por segundo |
| La API solo da 10 kills y 10 muertes | El worker guarda desde el primer día y consulta a menudo |
| Dos llamadas seguidas devuelven eventos distintos | Se guarda todo y se deduplica por `EventId` |
| Cambia el formato del JSON | En Mongo se guarda en bruto; solo hay que tocar el ETL |
| En los ordenadores del centro no se puede instalar Docker (WSL bloqueado, error 403) | Pedirlo a informática con tiempo; mientras, todo funciona sin Docker y los archivos de Docker se prueban en un ordenador personal |
| Uno de los dos se retrasa | Demo cada 2 semanas; las tareas se pueden mover entre personas |
