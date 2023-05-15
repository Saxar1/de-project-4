import logging

import pendulum
from airflow.decorators import dag, task
from airflow.models.variable import Variable
from stg_to_dds.dds_settings_repository import DdsEtlSettingsRepository
from stg_to_dds.dds.user_loader import UserLoader
from stg_to_dds.dds.rest_loader import RestaurantLoader
from stg_to_dds.dds.timestamp_loader import TSLoader
from stg_to_dds.dds.product_loader import ProductLoader
from stg_to_dds.dds.order_loader import OrderLoader
from stg_to_dds.dds.fps_loader import FPSLoader

from lib import ConnectionBuilder

log = logging.getLogger(__name__)


@dag(
    schedule_interval='0/15 * * * *',
    start_date=pendulum.datetime(2022, 5, 5, tz="UTC"),
    catchup=False,
    tags=['sprint5', 'dds', 'stg'],
    is_paused_upon_creation=True
)
def sprint5_stg_to_dds_dag():
    # Создаем подключение к базе dwh.
    dwh_pg_connect = ConnectionBuilder.pg_conn("PG_WAREHOUSE_CONNECTION")

    settings_repository = DdsEtlSettingsRepository()

    # Объявляем таск, который загружает данные.
    @task(task_id="users_load")
    def load_users():
        # создаем экземпляр класса, в котором реализована логика.
        user_loader = UserLoader(dwh_pg_connect, log)
        user_loader.load_users()  # Вызываем функцию, которая перельет данные.

    @task(task_id="rest_load")
    def load_rest():
        # создаем экземпляр класса, в котором реализована логика.
        rest_loader = RestaurantLoader(dwh_pg_connect, log)
        rest_loader.load_restaurants()  # Вызываем функцию, которая перельет данные.
    
    @task(task_id="timestamp_load")
    def load_ts():
        # создаем экземпляр класса, в котором реализована логика.
        ts_loader = TSLoader(dwh_pg_connect, log)
        ts_loader.load_ts()  # Вызываем функцию, которая перельет данные.

    @task(task_id="product_load")
    def load_products():
        product_loader = ProductLoader(dwh_pg_connect, log)
        product_loader.load_products()

    @task(task_id="order_load")
    def load_orders():
        order_loader = OrderLoader(dwh_pg_connect, log)
        order_loader.load_orders()

    @task(task_id="fps_load")
    def load_fps():
        fps_loader = FPSLoader(dwh_pg_connect, log)
        fps_loader.load_fps()

    # Инициализируем объявленные таски.
    users_loader = load_users()
    rest_loader = load_rest()
    ts_loader = load_ts()
    product_loader = load_products()
    order_loader = load_orders()
    fps_loader = load_fps()
    
    # Далее задаем последовательность выполнения тасков.
    users_loader  # type: ignore
    rest_loader
    ts_loader
    product_loader
    order_loader
    fps_loader


stg_to_dds_dag = sprint5_stg_to_dds_dag()
