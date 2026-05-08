import datetime
import re
import random
from urllib.parse import urljoin


from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from dotenv import load_dotenv
import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, MessageHandler, filters, PicklePersistence, CommandHandler, \
    ConversationHandler
import json
import logging
from telegram.error import BadRequest
import pytz

from data.data import PILOTS, TRACKS, TEAMS
import aiohttp

# # Запускаем логгирование
# logging.basicConfig(
#     format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG
# )
#
# logger = logging.getLogger(__name__)

WAITING_FOR_QUERY = "search"
WAITING_FOR_REMINDER = "reminder"
ASKING_CHOICE = "choice"
WAITING_FOR_GAME = "game"
CHECKING_RESPONSE = 0

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

ua = UserAgent()
random_user_agent = ua.random
headers = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "User-Agent": random_user_agent
}


def remove_job_if_exists(name, context):
    """
       Удаляет задание с заданным именем.
    """
    current_jobs = context.job_queue.get_jobs_by_name(name)
    job_name = f"{name}_hour"
    current_hour_jobs = context.job_queue.get_jobs_by_name(job_name)
    is_deleted = False
    if current_jobs:
        for job in current_jobs:
            job.schedule_removal()
            is_deleted = True
    if current_hour_jobs:
        for job in current_hour_jobs:
            job.schedule_removal()
            is_deleted = True
    return is_deleted


async def start(update, context):
    user = update.effective_user
    await update.message.reply_html(
        rf"Привет {user.mention_html()}! Я бот по формуле 1!🏎 Знаю много чего интересного, 🔍все функции ты можешь найти по команде /help",
    )
    keyboard = [
        [InlineKeyboardButton("Да", callback_data="yes")],
        [InlineKeyboardButton("Нет", callback_data="no")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        '❓Хочешь установить напоминание о гонках?',
        reply_markup=reply_markup
    )

    return WAITING_FOR_REMINDER


async def reminder_callback(update, context):
    query = update.callback_query
    await query.answer()

    choice = query.data  # "yes" или "no"

    if choice == 'yes':
        # Переходим к следующему вопросу
        keyboard = [
            [InlineKeyboardButton("За неделю", callback_data="choice_week")],
            [InlineKeyboardButton("За день", callback_data="choice_day")],
            [InlineKeyboardButton("За час", callback_data="choice_hour")],
            [InlineKeyboardButton("За неделю + день + час", callback_data="choice_all")]
        ]

        await query.edit_message_text(
            "Отлично! Выбери время напоминания:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ASKING_CHOICE

    elif choice == 'no':
        await query.edit_message_text(
            "❌ Хорошо, напоминания устанавливать не будем.\n"
            "Если передумаешь, напиши /start"
        )
        return ConversationHandler.END


async def choice_time_callback(update, context):
    query = update.callback_query
    await query.answer()

    choice = query.data  # choice_day, choice_hour или choice_day_and_hour
    messages = {
        "choice_week": "📌Я буду присылать напоминание об этапах гонки за неделю)",
        "choice_day": "📌Я буду присылать напоминание об этапах гонки за день)",
        "choice_hour": "📌Я буду присылать напоминание об этапах гонки за час)",
        "choice_all": "📌Я буду присылать напоминание об этапах гонки за неделю, день и час)",
    }

    await query.edit_message_text(
        f"{messages[choice]}\n\n"
        f"⚙Чтобы изменить настройки, снова напиши /start"
    )

    chat_id = update.callback_query.message.chat_id
    r = remove_job_if_exists(str(chat_id), context)

    moscow_tz = pytz.timezone('Europe/Moscow')
    context.job_queue.run_daily(reminder_for_the_day, time=datetime.time(hour=12, minute=0, tzinfo=moscow_tz),
                                data={"chat_id": chat_id, "choice": choice}, name=str(chat_id))

    context.user_data['choice'] = choice

    return ConversationHandler.END


async def reminder_for_the_day(context):
    """Отправляет сообщение-напоминание ."""
    job_data = context.job.data
    chat_id = job_data.get("chat_id")
    choice = job_data.get("choice")

    if not os.path.exists('calendar.json'):
        await find_the_calendar(context)
    elif await upcoming_event() < 1:
        await find_the_calendar(context)
    with open('calendar.json', 'r', encoding='utf-8') as f:
        stages = json.load(f)
    tz = pytz.timezone('Europe/Moscow')
    current_time = datetime.datetime.now(tz)

    is_print_week, is_print_day = False, False
    for key, data in stages.items():
        for stage in data:
            if ' ' in stage[1] and ':' in stage[1]:
                event_time = tz.localize(datetime.datetime.strptime(stage[1], "%d.%m.%Y %H:%M"))
            else:
                event_time = tz.localize(datetime.datetime.strptime(stage[1], '%d.%m.%Y'))
            diff = event_time - current_time

            if (choice == 'choice_week' or choice == 'choice_all') and diff.days == 7 and not is_print_week:
                text = f"🔔НАПОМИНАНИЕ!🔔\n\n❗Через 7 дней❗\n{key},\n{stage[0]}\n\n📆Время проведения этапа:\n {stage[1]}"
                if text:
                    if chat_id:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=text
                        )
                        is_print_week = True
            if (choice == 'choice_day' or choice == 'choice_all') and diff.days == 1 and not is_print_day:
                text = f"🔔НАПОМИНАНИЕ!🔔\n\n❗Через 1 день❗\n{key},\n{stage[0]}\n\n📆Время проведения этапа:\n {stage[1]}"
                if text:
                    if chat_id:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=text
                        )
                        is_print_day = True
            if (choice == 'choice_hour' or choice == 'choice_all') and diff.days == 0:
                time_reminder = event_time - datetime.timedelta(hours=1)
                job_name = f"{chat_id}_hour"
                context.job_queue.run_once(reminder_for_the_hour, when=time_reminder,
                                           data={"chat_id": chat_id, "choice": choice, "data": [key, stage]},
                                           name=job_name)


async def reminder_for_the_hour(context):
    """Отправляет сообщение-напоминание ."""
    job_data = context.job.data
    chat_id = job_data.get("chat_id")
    key, stage = job_data.get("data")

    if chat_id:
        text = f"🔔НАПОМИНАНИЕ!🔔\n\n❗Остался 1 час❗\n{key},\n{stage[0]}\n\n📆Время проведения этапа:\n {stage[1]}"
        await context.bot.send_message(
            chat_id=chat_id,
            text=text
        )


async def restore_all_reminders(app):
    """Восстанавливает задания напоминаний после перезапуска бота."""
    persistence = app.persistence
    if persistence is None:
        return

    # Получаем все сохранённые user_data (ключ - chat_id, значение - словарь)
    all_user_data = getattr(persistence, 'user_data', {})

    for chat_id_str, user_data in all_user_data.items():
        choice = user_data.get('choice')
        print(choice)
        if not choice:
            continue
        chat_id = int(chat_id_str)
        r = remove_job_if_exists(str(chat_id), app)

        moscow_tz = pytz.timezone('Europe/Moscow')
        app.job_queue.run_daily(reminder_for_the_day, time=datetime.time(hour=12, minute=0, tzinfo=moscow_tz),
                                data={"chat_id": chat_id, "choice": choice}, name=str(chat_id))

        is_subscribe = user_data.get('subscribe_to_news')
        print(is_subscribe)
        if is_subscribe:
            print('восстановили subscribe_to_news')
            app.job_queue.run_repeating(newsletter, interval=600, first=5,
                                            data={"chat_id": chat_id}, name=f'news_{str(chat_id)}')

async def find_the_calendar(context):
    async with aiohttp.ClientSession() as session:
        async with session.get("https://www.championat.com/auto/_f1/tournament/1032/calendar/",
                               headers=headers) as response:
            res = await response.text()
    soup = BeautifulSoup(res, 'lxml')

    calendar_title = soup.find_all('div', class_='tournament-calendar__title')
    calendar_name = soup.find_all('td', class_='tournament-calendar__name')
    calendar_date = soup.find_all('td', class_='tournament-calendar__date')
    data = {}

    try:
        last_data = datetime.datetime.strptime(calendar_date[0].text.strip(), "%d.%m.%Y %H:%M")
    except ValueError:
        last_data = datetime.datetime.strptime(calendar_date[0].text.strip(), "%d.%m.%Y")
    for line in calendar_title:
        data[line.text.strip()] = []
        while calendar_name:
            try:
                present_data = datetime.datetime.strptime(calendar_date[0].text.strip(), "%d.%m.%Y %H:%M")
            except ValueError:
                present_data = datetime.datetime.strptime(calendar_date[0].text.strip(), "%d.%m.%Y")

            days_diff = (present_data - last_data).days
            last_data = present_data
            if days_diff <= 2:
                data[line.text.strip()].append([calendar_name[0].text.strip(),
                                                calendar_date[0].text.strip()])
                calendar_name = calendar_name[1:]
                calendar_date = calendar_date[1:]
            else:
                break
    with open('calendar.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


async def find_the_top_leaders(context):
    async with aiohttp.ClientSession() as session:
        async with session.get("https://www.championat.com/auto/_f1/tournament/1032/standing/",
                               headers=headers) as response:
            res = await response.text()
    soup = BeautifulSoup(res, 'lxml')

    top_leaders = soup.find_all(['span', 'td'], class_=['table-item__name', 'points-table__total _nohover _fixed-column'])
    data = {}
    data['pilots'] = {}
    data['teams'] = {}
    for i in range(0, len(top_leaders), 2):
        if re.search(r'[a-zA-Z]', top_leaders[i].text.strip()):
            data['teams'][top_leaders[i].text.strip()] = top_leaders[i + 1].text.strip()
        elif not top_leaders[i].text.strip().isdigit():
            data['pilots'][top_leaders[i].text.strip()] = top_leaders[i + 1].text.strip()
    with open('leaders.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


async def find_pilots(context):
    async with aiohttp.ClientSession() as session:
        async with session.get("https://www.championat.com/auto/_f1/tournament/1032/players/",
                               headers=headers) as response:
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
    with open('pilots.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)



async def upcoming_event():
    tz = pytz.timezone('Europe/Moscow')
    current_time = datetime.datetime.now(tz)
    with open('calendar.json', 'r', encoding='utf-8') as f:
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


async def print_the_calendar(update, context):
    if not os.path.exists('calendar.json'):
        await find_the_calendar(context)
    elif await upcoming_event() < 1:
        await find_the_calendar(context)
    with open('calendar.json', 'r', encoding='utf-8') as f:
        calendar = json.load(f)
    print_data = ''
    for key, data in calendar.items():
        print_data += ' '.join([key, data[0][1], '-', data[-1][1]]) + '\n' + '\n'
    await update.message.reply_text(print_data)


async def print_top_leaders(update, context):
    if not os.path.exists('leaders.json'):
        await find_the_top_leaders(context)
    elif await upcoming_event() < 1:
        await find_the_top_leaders(context)
    with open('leaders.json', 'r', encoding='utf-8') as f:
        leaders = json.load(f)

    top_pilots, top_teams = leaders['pilots'], leaders['teams']
    ans = '🏅Личный зачёт:\n\n'
    for name, points in top_pilots.items():
        ans += f'{name} -  {points}\n\n'
    await update.message.reply_text(ans)
    ans = '🏆Командный зачёт:\n\n'
    for name, points in top_teams.items():
        ans += f'{name} -  {points}\n\n'
    await update.message.reply_text(ans)


async def print_pilots(update, context):
    if not os.path.exists('pilots.json'):
        await find_pilots(context)
    with open('pilots.json', 'r', encoding='utf-8') as f:
        pilots = json.load(f)
    print_data = ''
    for name, data in pilots.items():
        print_data += name + ' - ' + data['Команда'] + '\n'
        print_data += 'Дата рождения: ' + data['День рождения'] + '\n' + '\n'
    await update.message.reply_text(print_data)


async def help(update, context):
    await update.message.reply_text('''
/start - старт, установление напоминаний
(/stop_reminder - отмена напоминаний)
/calendar - расписание этапов
/top_leaders - очки лидеров
/pilots - информация о пилотах
/play - игра "Угадай трассу по схеме"
/subscribe_to_news - подписка на новостную рассылку
/search - поиск
/cancel - завершение поиска/старта
/help - помощь''')


async def search_start(update, context):
    keyboard = [
        [InlineKeyboardButton("Пилоты", callback_data="pilots")],
        [InlineKeyboardButton("Команды", callback_data="teams")],
        [InlineKeyboardButton("Этапы", callback_data="stages")],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        '🔍 Что хотите найти?\n\n'
        'Я могу дать информацию по:\n'
        '✔ имени пилота\n'
        '✔ команде\n'
        '✔ названию этапа/дате/городу проведения\n\n'
        'Сначала выберите категорию поиска:',
        reply_markup=reply_markup
    )

    return WAITING_FOR_QUERY


async def button_callback(update, context):
    query = update.callback_query
    await query.answer()

    category = query.data  # "pilots", "teams" или "stages"
    context.user_data['search_category'] = category
    example = ''
    if category == 'pilots':
        example = 'Ферстаппен/Леклер/макс'
    elif category == 'teams':
        example = 'Ferrari/red bull/mclaren'
    elif category == 'stages':
        example = 'этап 2/Италия/Мельбурн/28.11.2026'

    await query.edit_message_text(
        f"✅ Вы выбрали поиск по категории: {category}!\n\n"
        f"Теперь введите ваш запрос.\n"
        f"Например: {example}\n"
        f"🔚Для выхода напишите /cancel"
    )

    return WAITING_FOR_QUERY


async def search_query(update, context):
    query = update.message.text.strip()

    # Получаем выбранную категорию
    category = context.user_data.get('search_category')

    if not category:
        # Если категория не выбрана, предлагаем выбрать заново
        await update.message.reply_text(
            "❌ Сначала выберите категорию поиска!\n"
            "Используйте /search для начала"
        )
        return ConversationHandler.END

    # Ищем в соответствующей базе данных
    result = None
    if category == 'stages':
        if not os.path.exists('calendar.json'):
            await find_the_calendar(context)
        elif await upcoming_event() < 1:
            await find_the_calendar(context)
        with open('calendar.json', 'r', encoding='utf-8') as f:
            calendar = json.load(f)
        for key, data in calendar.items():
            data = '\n\n'.join([stage[0] + ' ' + stage[1] for stage in data])
            # query.lower() == ' '.join(key.lower().split()[:2])[:-1] -> номер этапа(этап 1, этап 12 и т.д.)
            if (query.lower() == ' '.join(key.lower().split()[:2])[:-1] or
                    query.lower() in key.lower() or query.lower() in data):
                result = f'🏁Нашли в календаре:\n {key}\n {data}'
                key = key.split('. ')[1] # отделяем название города и страну
                try:
                    await context.bot.send_photo(chat_id=update.message.chat_id,
                                                 photo=f'photo/tracks/{TRACKS[key]}', caption=key)
                except (KeyError, BadRequest):
                    ...
                break
    elif category == 'pilots':
        if not os.path.exists('pilots.json'):
            await find_pilots(context)
        with open('pilots.json', 'r', encoding='utf-8') as f:
            pilots = json.load(f)
        for key, data in pilots.items():
            if query.lower() in key.lower():
                result = f'{key}\n'
                for parameter, value in data.items():
                    result += parameter + ': ' + value + '\n'
                result += PILOTS[key][1]
                try:
                    await context.bot.send_photo(chat_id=update.message.chat_id,
                                                 photo=f'photo/pilots/{PILOTS[key][0]}', caption=key)
                except (KeyError, BadRequest):
                    ...
                break
    elif category == 'teams':
        for name_team, data in TEAMS.items():
            if query.lower() in name_team.lower():
                result = data[1]
                try:
                    await context.bot.send_photo(chat_id=update.message.chat_id,
                                                 photo=f'photo/teams/{data[0]}', caption=name_team)
                except (KeyError, BadRequest):
                    ...
                break
    if result is None:
        result = "❌ Ничего не найдено."
    await update.message.reply_text(f"🔍 Результат по запросу '{query}'\n"
                                    f"{result}")

    # Остаемся в режиме поиска
    return WAITING_FOR_QUERY


async def bad_commands(update, context):
    command = update.message.text
    if command == '/cancel':
        return await cancel(update, context)
    await update.message.reply_text(
        "❗Во время поиска доступна только команда /cancel\n"
        "Введите текст для поиска или /cancel для выхода"
    )
    return WAITING_FOR_QUERY

async def bad_game_commands(update, context):
    command = update.message.text
    if command == '/cancel':
        return await cancel(update, context)
    await update.message.reply_text(
        "❗Во время игры доступна только команда /cancel\n"
        "Продолжайте игру или напишите /cancel для выхода"
    )
    return CHECKING_RESPONSE

async def cancel(update, context):
    """Выход из режима поиска"""
    # Очищаем выбранную категорию
    context.user_data.pop('search_category', None)
    context.user_data.pop('right_answer', None)
    await update.message.reply_text(
        "❌Отмена диалога"
    )
    return ConversationHandler.END


async def stop_reminder(update, context):
    chat_id = update.effective_chat.id
    job_name = str(chat_id)
    removed = remove_job_if_exists(job_name, context)

    # Очищаем сохранённый выбор в user_data (если есть)
    context.user_data.pop('choice', None)

    if removed:
        await update.message.reply_text("✅ Напоминания о гонках отключены.")
    else:
        await update.message.reply_text("❌ У вас не было активных напоминаний.")


async def send_new_question(update, context):
    """Генерирует новый вопрос и отправляет его пользователю."""
    # Выбираем 3 случайные трассы
    random_tracks = random.sample(list(TRACKS), 3)
    right_answer = random.choice(random_tracks)
    context.user_data['right_answer'] = right_answer

    keyboard = [
        [InlineKeyboardButton(f'{random_tracks[0]}', callback_data=f"{random_tracks[0]}")],
        [InlineKeyboardButton(f'{random_tracks[1]}', callback_data=f"{random_tracks[1]}")],
        [InlineKeyboardButton(f'{random_tracks[2]}', callback_data=f"{random_tracks[2]}")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=f'photo/tracks/{TRACKS[right_answer]}',
        caption="В какой стране находится эта трасса?",
        reply_markup=reply_markup
    )


async def game_start(update, context):
    await update.message.reply_text(
        "Твоя задача отгадать страну, где находятся трассы!\n"
        "Я буду отправлять тебе фотографии, а ты из предложенных вариантов должен выбрать правильный!\n"
        "Чем больше подряд отгадаешь, тем лучше!"
    )

    keyboard = [
        [InlineKeyboardButton("Да", callback_data="yes")],
        [InlineKeyboardButton("Нет", callback_data="no")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        '❓ Начнём игру?',
        reply_markup=reply_markup
    )
    return WAITING_FOR_GAME

async def play_game(update, context):
    """Обрабатывает нажатие 'Да' или 'Нет' на старте"""
    query = update.callback_query
    await query.answer()

    if query.data == 'yes':
        await query.edit_message_text("Игра началась!")
        await send_new_question(update, context)
        return CHECKING_RESPONSE

    elif query.data == 'no':
        await query.edit_message_text("❌ Если захочешь поиграть, напиши /play")
        return ConversationHandler.END

async def checking_response(update, context):
    """Проверяет ответ пользователя и сразу задаёт следующий вопрос."""
    query = update.callback_query
    await query.answer()

    right_answer = context.user_data.get('right_answer')
    user_answer = query.data

    if user_answer == right_answer:
        await query.message.reply_text("✅ Правильно!")
    else:
        await query.message.reply_text(f"❌ Не угадал. Правильный ответ: {right_answer}")

    await send_new_question(update, context)
    return CHECKING_RESPONSE

async def subscribe_to_news(update, context):
    chat_id = update.effective_chat.id

    await update.message.reply_text('Ты подписался на новостную рассылку! Чтобы отписаться напиши /unsubscribe_from_news')

    jobs = context.job_queue.get_jobs_by_name(f'news_{str(chat_id)}')
    if jobs:
        for job in jobs:
            job.schedule_removal()
    context.job_queue.run_repeating(newsletter, interval=600, first=5,
                                data={"chat_id": chat_id}, name=f'news_{str(chat_id)}')
    context.user_data['subscribe_to_news'] = True

async def newsletter(context):
    job_data = context.job.data
    chat_id = job_data.get("chat_id")

    news_random_user_agent = ua.random
    news_headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "User-Agent": news_random_user_agent
    }
    url = 'https://www.f1news.ru'
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=news_headers) as response:
            res = await response.text()
    soup = BeautifulSoup(res, 'lxml')

    link = soup.find(class_='b-news-list__title')
    absolute_link= ''
    if link:
        link = link.get('href')
        absolute_link = urljoin(url, link)
    if absolute_link:
        async with aiohttp.ClientSession() as session:
            async with session.get(absolute_link, headers=headers) as response:
                res = await response.text()
        soup = BeautifulSoup(res, 'lxml')

        title = soup.find('div', class_='post_head').text
        text = soup.find('div', class_='post_content post_auto').text

        title = '\n'.join([line.strip() for line in title.splitlines() if line.strip()][:-1])
        text = '\n\n'.join(text.split('\n'))

        if os.path.exists('last_news.txt'):
            with open('last_news.txt', 'r', encoding='utf-8') as f:
                last_news = f.read()
        else:
            last_news = ''
        if last_news != title:
                await context.bot.send_message(
                        chat_id=chat_id,
                        text=title + text
                    )
                with open('last_news.txt', 'w', encoding='utf-8') as f:
                    f.write(title)

async def unsubscribe_from_news(update, context):
    context.user_data['subscribe_to_news'] = False

    chat_id = update.effective_chat.id
    name = f'news_{str(chat_id)}'
    jobs = context.job_queue.get_jobs_by_name(name)
    if jobs:
        for job in jobs:
            job.schedule_removal()
        await update.message.reply_text('Подписка на новости отключена!')
    else:
        await update.message.reply_text('Вы не были подписаны на новостную рассылку')

def main():
    persistence = PicklePersistence(filepath="bot_data.pickle")
    application = Application.builder().token(BOT_TOKEN).persistence(persistence).post_init(
        restore_all_reminders).build()

    conv_handler_search = ConversationHandler(
        entry_points=[CommandHandler('search', search_start)],
        states={
            WAITING_FOR_QUERY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, search_query),
                MessageHandler(filters.COMMAND, bad_commands),
                CallbackQueryHandler(button_callback)
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    application.add_handler(conv_handler_search)

    conv_handler_reminder = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            WAITING_FOR_REMINDER: [
                CallbackQueryHandler(reminder_callback),  # обработчик кнопок
            ],
            ASKING_CHOICE: [
                CallbackQueryHandler(choice_time_callback)
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    application.add_handler(conv_handler_reminder)

    conv_handler_game = ConversationHandler(
        entry_points=[CommandHandler('play', game_start)],
        states={
            WAITING_FOR_GAME: [
                CallbackQueryHandler(play_game),
            ],
            CHECKING_RESPONSE: [
                CallbackQueryHandler(checking_response),
                MessageHandler(filters.COMMAND, bad_game_commands),
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    application.add_handler(conv_handler_game)

    application.add_handler(CommandHandler("calendar", print_the_calendar))
    application.add_handler(CommandHandler("top_leaders", print_top_leaders))
    application.add_handler(CommandHandler("pilots", print_pilots))
    application.add_handler(CommandHandler("help", help))
    application.add_handler(CommandHandler("stop_reminder", stop_reminder))
    application.add_handler(CommandHandler("subscribe_to_news", subscribe_to_news))
    application.add_handler(CommandHandler("unsubscribe_from_news", unsubscribe_from_news))


    application.job_queue.run_repeating(
        find_the_calendar,
        interval=3600,  # раз в час
        first=10
    )
    application.job_queue.run_repeating(
        find_the_top_leaders,
        interval=3600,  # раз в час
        first=20
    )
    application.job_queue.run_repeating(
        find_pilots,
        interval=3600,  # раз в час
        first=30
    )
    application.run_polling()


if __name__ == '__main__':
    main()
