from logging import Logger
from typing import List

from dds_to_cdm.cdm_settings_repository import EtlSetting, CdmEtlSettingsRepository
from lib import PgConnect
from datetime import date
from lib.dict_util import json2str
from psycopg import Connection
from psycopg.rows import class_row
from pydantic import BaseModel


class DclObj(BaseModel):
    courier_id: str
    courier_name: str
    settlement_year: int
    settlement_month: int
    orders_count: int
    orders_total_sum: float
    rate_avg: float
    order_processing_fee: float
    courier_order_sum: float
    courier_tips_sum: float
    courier_reward_sum: float


class DclStgRepository:
    def __init__(self, pg: PgConnect) -> None:
        self._db = pg

    def list_dcl(self, dcl_threshold: str) -> List[DclObj]:
        with self._db.client().cursor(row_factory=class_row(DclObj)) as cur:
            cur.execute(
                """
                    with 
                        metrics as (
                            select distinct
                                dc.id as courier_id,
                                dc.courier_name as courier_name,
                                dt.year as settlement_year,
                                dt.month as settlement_month,
                                count(do2.id) as orders_count,
                                sum(dd."sum") as orders_total_sum,
                                avg(dd.rate) as rate_avg,
                                sum(dd."sum") * 0.25 as order_processing_fee,
                                case
                                    when avg(dd.rate) < 4 then sum(dd."sum") * 0.05
                                    when avg(dd.rate) >= 4 and avg(dd.rate) < 4.5 then sum(dd."sum") * 0.07
                                    when avg(dd.rate) >= 4.5 and avg(dd.rate) < 4.9 then sum(dd."sum") * 0.08
                                    when avg(dd.rate) >= 4.9 then sum(dd."sum") * 0.1
                                end as courier_order_sum,
                                sum(dd.tip_sum) as courier_tips_sum        	
                            from dds.dm_deliveries dd
                            join dds.dm_couriers dc on dc.courier_id = dd.courier_id
                            join dds.dm_orders do2 on dd.order_id = do2.order_key
                            join dds.dm_timestamps dt on do2.timestamp_id = dt.id 
                            group by dc.id, dc.courier_name, dt.year, dt.month)
                    select distinct 
                        courier_id,
                        courier_name,
                        settlement_year,
                        settlement_month,
                        orders_count,
                        orders_total_sum,
                        rate_avg, 
                        order_processing_fee,
                        courier_order_sum,
                        courier_tips_sum,
                        courier_order_sum + courier_tips_sum * 0.95 as courier_reward_sum
                    from metrics as m
                    WHERE m.courier_id > %(threshold)s
                    ORDER BY m.courier_id ASC --Обязательна сортировка по id, т.к. id используем в качестве курсора.
                """, {
                    "threshold": dcl_threshold
                }
            )
            objs = cur.fetchall()
        return objs


class DclCdmRepository:
    def insert_dcl(self, conn: Connection, dcl: DclObj) -> None:
        with conn.cursor() as cur:
            cur.execute(
                  """
                    INSERT INTO cdm.dm_courier_ledger (courier_id, courier_name, settlement_year, settlement_month, orders_count, orders_total_sum, rate_avg, order_processing_fee, courier_order_sum, courier_tips_sum, courier_reward_sum)
                    VALUES (%(courier_id)s, %(courier_name)s, %(settlement_year)s, %(settlement_month)s, %(orders_count)s, %(orders_total_sum)s, %(rate_avg)s, %(order_processing_fee)s, %(courier_order_sum)s, %(courier_tips_sum)s, %(courier_reward_sum)s)
                """,
                {
                    "courier_id": dcl.courier_id,
                    "courier_name": dcl.courier_name,
                    "settlement_year": dcl.settlement_year,
                    "settlement_month": dcl.settlement_month,
                    "orders_count": dcl.orders_count,
                    "orders_total_sum": dcl.orders_total_sum,
                    "rate_avg": dcl.rate_avg,
                    "order_processing_fee": dcl.order_processing_fee,
                    "courier_order_sum": dcl.courier_order_sum,
                    "courier_tips_sum": dcl.courier_tips_sum,
                    "courier_reward_sum": dcl.courier_reward_sum
                },
            )


class DclLoader:
    WF_KEY = "Dcl_workflow"
    LAST_LOADED_ID_KEY = "last_loaded_id"

    def __init__(self, pg_dest: PgConnect, log: Logger) -> None:
        self.pg_dest = pg_dest
        self.origin = DclStgRepository(pg_dest)
        self.dds = DclCdmRepository()
        self.settings_repository = CdmEtlSettingsRepository()
        self.log = log

    def load_dcl(self):
        # открываем транзакцию.
        # Транзакция будет закоммичена, если код в блоке with пройдет успешно (т.е. без ошибок).
        # Если возникнет ошибка, произойдет откат изменений (rollback транзакции).
        with self.pg_dest.connection() as conn:

            # Прочитываем состояние загрузки
            # Если настройки еще нет, заводим ее.
            wf_setting = self.settings_repository.get_setting(conn, self.WF_KEY)
            if not wf_setting:
                wf_setting = EtlSetting(id=0, workflow_key=self.WF_KEY, workflow_settings={self.LAST_LOADED_ID_KEY: -1})

            # Вычитываем очередную пачку объектов.
            last_loaded = wf_setting.workflow_settings[self.LAST_LOADED_ID_KEY]
            load_queue = self.origin.list_dcl(last_loaded)
            self.log.info(f"Found {len(load_queue)} dcl to load.")
            if not load_queue:
                self.log.info("Quitting.")
                return

            # Сохраняем объекты в базу dwh.
            for dcl in load_queue:
                self.dds.insert_dcl(conn, dcl)

            # Сохраняем прогресс.
            # Мы пользуемся тем же connection, поэтому настройка сохранится вместе с объектами,
            # либо откатятся все изменения целиком.
            wf_setting.workflow_settings[self.LAST_LOADED_ID_KEY] = max([t.courier_id for t in load_queue])
            wf_setting_json = json2str(wf_setting.workflow_settings)  # Преобразуем к строке, чтобы положить в БД.
            self.settings_repository.save_setting(conn, wf_setting.workflow_key, wf_setting_json)

            self.log.info(f"Load finished on {wf_setting.workflow_settings[self.LAST_LOADED_ID_KEY]}")
