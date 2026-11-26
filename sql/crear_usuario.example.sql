-- SOLO si usáis MySQL o MariaDB instalado en el ordenador (con Docker no hace falta,
-- docker-compose crea la base de datos y el usuario solo).
--
-- 1. Copiad este archivo como crear_usuario.sql y poned la misma contraseña que en .env
-- 2. Ejecutadlo como root:
--      mysql -u root -p -e "source sql/crear_usuario.sql"

CREATE DATABASE IF NOT EXISTS albion_tracker CHARACTER SET utf8mb4;
CREATE DATABASE IF NOT EXISTS albion_tracker_test CHARACTER SET utf8mb4;

CREATE USER IF NOT EXISTS 'tracker'@'localhost' IDENTIFIED BY 'PON_AQUI_LA_CONTRASEÑA';
GRANT ALL PRIVILEGES ON albion_tracker.*      TO 'tracker'@'localhost';
GRANT ALL PRIVILEGES ON albion_tracker_test.* TO 'tracker'@'localhost';
FLUSH PRIVILEGES;
