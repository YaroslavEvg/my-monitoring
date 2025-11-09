import threading
import logging
from waitress import serve
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
import init
from threads.campuses.campuses import get_campus
from threads.campuses.participants import get_participants
from threads.campuses.coalitions import get_coalitions
from threads.campuses.clusters import get_clusters
from threads.clusters.maps import get_maps
from threads.clusters.mapsOnline import get_mapsOnline
from threads.sales import get_sales
from threads.events import get_events
from threads.coalitions_participants import get_coalitions_participants
from threads.participants.info import get_participants_info
from threads.participants.skills import get_participants_skills
from threads.participants.projects import get_participants_projects

# Тайм-аут на выполнение задачи (24 часа)
TASK_TIMEOUT = 86400 * 2  # 24 часа в секундах

init.init_logging()

app = Flask(__name__)

# Установка параметров планировщика
executors = {
    'default': ThreadPoolExecutor(20)
}
scheduler = BackgroundScheduler(executors=executors)

# def schedule_jobs():
#     global scheduler

#     jobs = {
#         'get_campus': get_campus,
#         'get_participants': get_participants,
#         'get_coalitions': get_coalitions,
#         'get_clusters': get_clusters,
#         'get_maps': get_maps,
#         'get_sales': get_sales,
#         'get_events': get_events,
#         'get_coalitions_participants': get_coalitions_participants,
#         'get_participants_info': get_participants_info,
#         'get_participants_skills': get_participants_skills,
#         'get_participants_projects': get_participants_projects
#     }

#     interval_jobs = {
#         'get_sales': {'hours': 1},
#         'get_events': {'minutes': 2}
#     }

#     cron_jobs = {
#         'get_campus': {'day_of_week': '0-6', 'hour': '1', 'minute': '0'}, # Каждую субботу в 8:00
#         'get_participants': {'day_of_week': '0-6', 'hour': '1', 'minute': '10'}, # Каждый день в 1:00
#         'get_participants_info': {'day_of_week': '0-6', 'hour': '3', 'minute': '0'}, # Каждый день в 3:00
#         'get_participants_skills': {'day_of_week': '0-6', 'hour': '6', 'minute': '0'}, # Каждый день в 6:00
#         # 'get_clusters': {'day_of_week': 'wed', 'hour': '5', 'minute': '0'}, # Каждую среду в 5:00
#         # 'get_maps': {'day_of_week': 'wed', 'hour': '6', 'minute': '0'}, # Каждую среду в 6:00
#         'get_coalitions_participants': {'day_of_week': 'fri', 'hour': '2', 'minute': '0'}, # Каждую пятницу в 2:00
#         'get_coalitions': {'day_of_week': 'tue', 'hour': '3', 'minute': '0'}, # Каждый вторник в 3:00
#         'get_participants_projects': {'day_of_week': '0-6', 'hour': '9', 'minute': '0'} # Каждый день в 9:00
#     }

#     for job_id, interval in interval_jobs.items():
#         func = jobs[job_id]
#         if scheduler.get_job(job_id):
#             scheduler.remove_job(job_id)
#         scheduler.add_job(func=func, trigger="interval", id=job_id, **interval, max_instances=3, misfire_grace_time=3600)

#     for job_id, cron_time in cron_jobs.items():
#         func = jobs[job_id]
#         if scheduler.get_job(job_id):
#             scheduler.remove_job(job_id)
#         scheduler.add_job(func=func, trigger='cron', id=job_id, **cron_time, max_instances=3, misfire_grace_time=3600)

#     scheduler.start()

def timeout_handler(func, timeout):
    """Запускает функцию с тайм-аутом. Возвращает True, если выполнена, иначе False."""
    thread = threading.Thread(target=func)
    thread.start()
    thread.join(timeout)  # Ждем завершения задачи до тайм-аута
    if thread.is_alive():
        logging.error(f"Задача {func.__name__} не завершилась за {timeout} секунд и будет принудительно завершена.")
        return False  # Задача не завершилась
    return True  # Задача успешно завершена

def wrap_with_timeout(func):
    """Обертка для задач с тайм-аутом."""
    def wrapper():
        if not timeout_handler(func, TASK_TIMEOUT):
            logging.error(f"Перезапуск задачи {func.__name__} после тайм-аута.")
            timeout_handler(func, TASK_TIMEOUT)  # Перезапускаем задачу, если она не завершилась
    return wrapper

def schedule_jobs():
    global scheduler

    jobs = {
        'get_campus': get_campus,
        'get_participants': get_participants,
        'get_coalitions': get_coalitions,
        'get_clusters': get_clusters,
        'get_maps': get_maps,
        'get_sales': get_sales,
        'get_events': get_events,
        'get_coalitions_participants': get_coalitions_participants,
        'get_participants_info': get_participants_info,
        'get_participants_skills': get_participants_skills,
        'get_participants_projects': get_participants_projects
    }

    interval_jobs = {
        'get_sales': {'hours': 1},
        'get_events': {'minutes': 2}
    }

    cron_jobs = {
        'get_campus': {'day_of_week': '0-6', 'hour': '1', 'minute': '0'}, # Каждый день в 1:00
        'get_participants': {'day_of_week': '0-6', 'hour': '1', 'minute': '10'}, # Каждый день в 1:10
        'get_participants_info': {'day_of_week': '0-6', 'hour': '3', 'minute': '0'}, # Каждый день в 3:00
        'get_participants_skills': {'day_of_week': '0-6', 'hour': '6', 'minute': '0'}, # Каждый день в 6:00
        'get_coalitions_participants': {'day_of_week': 'fri', 'hour': '2', 'minute': '0'}, # Пятница в 2:00
        'get_coalitions': {'day_of_week': 'tue', 'hour': '3', 'minute': '0'} #, # Вторник в 3:00
        # 'get_participants_projects': {'day_of_week': '0-6', 'hour': '9', 'minute': '0'} # Каждый день в 9:00
    }

    for job_id, interval in interval_jobs.items():
        func = wrap_with_timeout(jobs[job_id])  # Оборачиваем задачу в тайм-аут
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
        scheduler.add_job(func=func, trigger="interval", id=job_id, **interval, max_instances=1, misfire_grace_time=3600)

    for job_id, cron_time in cron_jobs.items():
        func = wrap_with_timeout(jobs[job_id])  # Оборачиваем задачу в тайм-аут
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
        scheduler.add_job(func=func, trigger='cron', id=job_id, **cron_time, max_instances=1, misfire_grace_time=3600)

    scheduler.start()

def run_initial_tasks():
    get_campus()
    get_coalitions()
    # get_clusters()
    # get_maps()
    # get_mapsOnline()
    get_sales()
    get_events()
    get_participants()
    get_participants_info()
    get_coalitions_participants()
    get_participants_skills()

if __name__ == '__main__':
    scheduler_thread = threading.Thread(target=schedule_jobs)
    scheduler_thread.daemon = True
    scheduler_thread.start()
    get_events()
    # get_participants_info()
    # get_participants_skills()
    # run_initial_tasks()
    serve(app, host='0.0.0.0', port=8000)
