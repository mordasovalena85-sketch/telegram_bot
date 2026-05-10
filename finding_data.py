import datetime
import json
import re

import aiohttp
import pytz

from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from telegram.ext import ConversationHandler


def get_headers():
    """Возвращает headers"""

    # создаём рандомный UserAgent
    ua = UserAgent()
    random_user_agent = ua.random
    return {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "User-Agent": random_user_agent
    }



async def find_the_calendar(context):
    """Парсинг сайта для поиска расписания гонок,
    Запись данных в JSON-файл"""
    async with aiohttp.ClientSession() as session:
        async with session.get("https://www.championat.com/auto/_f1/tournament/1032/calendar/",
                               headers=get_headers()) as response:
            res = await response.text()
    soup = BeautifulSoup(res, 'lxml')

    calendar_title = soup.find_all('div', class_='tournament-calendar__title')  # общие названия уикендов
    calendar_name = soup.find_all('td', class_='tournament-calendar__name')  # названия каждых этапов
    calendar_date = soup.find_all('td', class_='tournament-calendar__date')  # даты этапов
    data = {}

    # записываем прошлую дату
    try:
        last_data = datetime.datetime.strptime(calendar_date[0].text.strip(), "%d.%m.%Y %H:%M")
    except ValueError:
        last_data = datetime.datetime.strptime(calendar_date[0].text.strip(), "%d.%m.%Y")
    for line in calendar_title:
        data[line.text.strip()] = []
        while calendar_name:
            # записываем следующую дату
            try:
                present_data = datetime.datetime.strptime(calendar_date[0].text.strip(), "%d.%m.%Y %H:%M")
            except ValueError:
                present_data = datetime.datetime.strptime(calendar_date[0].text.strip(), "%d.%m.%Y")

            # ищем разницу между двумя соседними датами
            days_diff = (present_data - last_data).days
            last_data = present_data
            # если разница большая, значит начинаем записывать данные этапов в следующий уикенд
            if days_diff <= 2:
                data[line.text.strip()].append([calendar_name[0].text.strip(),
                                                calendar_date[0].text.strip()])
                calendar_name = calendar_name[1:]
                calendar_date = calendar_date[1:]
            else:
                break
    with open('data/calendar.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


async def find_the_top_leaders(context):
    """Парсинг сайта для поиска топа лидеров,
    Запись данных в JSON-файл"""
    async with aiohttp.ClientSession() as session:
        async with session.get("https://www.championat.com/auto/_f1/tournament/1032/standing/",
                               headers=get_headers()) as response:
            res = await response.text()
    soup = BeautifulSoup(res, 'lxml')

    top_leaders = soup.find_all(['span', 'td'],
                                class_=['table-item__name', 'points-table__total _nohover _fixed-column'])
    data = {}
    data['pilots'] = {}
    data['teams'] = {}
    for i in range(0, len(top_leaders), 2):
        # если название на английском, значит это название команды
        if re.search(r'[a-zA-Z]', top_leaders[i].text.strip()):
            data['teams'][top_leaders[i].text.strip()] = top_leaders[i + 1].text.strip()
        # отсеиваем ненужные данные, остальные являются пилотами
        elif not top_leaders[i].text.strip().isdigit():
            data['pilots'][top_leaders[i].text.strip()] = top_leaders[i + 1].text.strip()
    with open('data/leaders.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


async def find_pilots(context):
    """Парсинг сайта для поиска информации о пилотах,
        Запись данных в JSON-файл"""
    async with aiohttp.ClientSession() as session:
        async with session.get("https://www.championat.com/auto/_f1/tournament/1032/players/",
                               headers=get_headers()) as response:
            res = await response.text()
    soup = BeautifulSoup(res, 'lxml')

    pilots = soup.find_all(['span', 'td'], class_=['table-item__name',
                                                   'table-responsive__row-item _player-team _order_2 _order_mobile_4 _tablet',
                                                   'table-responsive__row-item _right _order_5 _desktop',
                                                   'table-responsive__row-item _right _w-5 _order_6 _desktop',
                                                   'table-responsive__row-item _right _w-5 _order_7 _desktop'])
    data = {}
    for i in range(0, len(pilots), 5):
        data[pilots[i].text.strip()] = {}
        data[pilots[i].text.strip()]['Команда'] = pilots[i + 1].text.strip()
        data[pilots[i].text.strip()]['День рождения'] = pilots[i + 2].text.strip()
        if pilots[i + 3].text.strip():
            data[pilots[i].text.strip()]['Рост'] = pilots[i + 3].text.strip()
        if pilots[i + 4].text.strip():
            data[pilots[i].text.strip()]['Вес'] = pilots[i + 4].text.strip()
    data = dict(sorted(data.items()))
    with open('data/pilots.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


async def upcoming_event():
    """Поиск ближайшего события(будущего или прошедшего)
    и вывод количества часов до него"""
    tz = pytz.timezone('Europe/Moscow')
    current_time = datetime.datetime.now(tz)
    with open('data/calendar.json', 'r', encoding='utf-8') as f:
        calendar = json.load(f)
    differences = []
    for key, data in calendar.items():
        for stage in data:
            if ' ' in stage[1] and ':' in stage[1]:
                event_time = tz.localize(datetime.datetime.strptime(stage[1], "%d.%m.%Y %H:%M"))
            else:
                event_time = tz.localize(datetime.datetime.strptime(stage[1], '%d.%m.%Y'))
            diff = event_time - current_time
            differences.append(abs(diff))
    return min(differences).seconds / 3600


async def cancel(update, context):
    """Завершение диалога поиска, игры, старта"""
    context.user_data.pop('search_category', None)
    context.user_data.pop('right_answer', None)
    await update.message.reply_text(
        "❌Отмена диалога"
    )
    return ConversationHandler.END
