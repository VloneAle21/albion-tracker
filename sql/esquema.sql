-- Esquema de los datos limpios. Funciona en MySQL 8 y en MariaDB 10.5+.
-- Se puede ejecutar varias veces: IF NOT EXISTS no toca lo que ya existe.

CREATE TABLE IF NOT EXISTS jugadores (
    id          VARCHAR(32)  PRIMARY KEY,
    nombre      VARCHAR(40)  NOT NULL,
    gremio      VARCHAR(60),
    servidor    VARCHAR(10)  NOT NULL,
    kill_fame   BIGINT,               -- NULL si solo lo conocemos por aparecer en un evento
    death_fame  BIGINT,
    actualizado DATETIME
) CHARACTER SET utf8mb4;

CREATE TABLE IF NOT EXISTS eventos (
    event_id          BIGINT      PRIMARY KEY,
    fecha             DATETIME    NOT NULL,   -- en UTC
    servidor          VARCHAR(10) NOT NULL,
    fama_total        INT         NOT NULL,
    num_participantes INT         NOT NULL,
    tam_grupo         INT         NOT NULL,
    zona              VARCHAR(30),
    batalla_id        BIGINT,
    INDEX idx_eventos_fecha (fecha)
) CHARACTER SET utf8mb4;

CREATE TABLE IF NOT EXISTS participaciones (
    event_id   BIGINT       NOT NULL,
    jugador_id VARCHAR(32)  NOT NULL,
    rol        ENUM('asesino', 'victima', 'asistente') NOT NULL,
    ip_media   DECIMAL(7,2),
    arma       VARCHAR(60),
    dano       DECIMAL(12,2),
    PRIMARY KEY (event_id, jugador_id, rol),
    INDEX idx_participaciones_jugador (jugador_id, rol),
    FOREIGN KEY (event_id)   REFERENCES eventos(event_id),
    FOREIGN KEY (jugador_id) REFERENCES jugadores(id)
) CHARACTER SET utf8mb4;
