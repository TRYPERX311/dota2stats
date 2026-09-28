"""
Планировщик сбора статистики.

Запускает collector.run() сразу при старте,
затем каждые 12 часов.
"""

import traceback

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

import collector


def safe_run():
    """Обёртка вокруг collector.run() — чтобы падение сбора не убивало планировщик."""
    try:
        collector.run()
    except Exception:
        print("[scheduler] Ошибка во время сбора статистики:")
        traceback.print_exc()


def main():
    scheduler = BlockingScheduler(timezone="UTC")

    scheduler.add_job(
        safe_run,
        trigger=IntervalTrigger(hours=12),
        id="collect_stats",
        max_instances=1,        # не запускать второй экземпляр, если предыдущий ещё работает
        coalesce=True,          # пропущенные запуски схлопнуть в один
        misfire_grace_time=600, # 10 минут допуска на «опоздание»
    )

    print("[scheduler] Старт. Интервал: 12 часов. Первый запуск — сразу.")

    # Первый запуск сразу, синхронно
    safe_run()

    # Дальше — по расписанию
    scheduler.start()


if __name__ == "__main__":
    main()