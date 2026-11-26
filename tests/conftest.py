"""Fixtures compartidos por todos los tests."""

import pytest


@pytest.fixture
def mysql_real():
    from tracker.almacen_mysql import conectar_mysql

    almacen = conectar_mysql("albion_tracker_test")
    if almacen is None:
        pytest.skip("No hay MySQL de pruebas (albion_tracker_test)")
    with almacen.conexion.cursor() as cursor:
        for tabla in ("participaciones", "eventos", "jugadores"):
            cursor.execute(f"DROP TABLE IF EXISTS {tabla}")
    almacen.crear_tablas()
    yield almacen
    almacen.conexion.close()
