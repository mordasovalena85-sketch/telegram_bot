import requests
import datetime
import re

from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import pprint
from dotenv import load_dotenv
import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, Application, CallbackQueryHandler, MessageHandler, filters,PicklePersistence, CommandHandler, ConversationHandler
import json
import logging
from telegram.error import BadRequest
import pytz

from data.pilots_info import INFO, TRACKS, TEAMS
import aiohttp


# # Запускаем логгирование
# logging.basicConfig(
#     format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG
# )
#
# logger = logging.getLogger(__name__)

WAITING_FOR_QUERY = "search"
WAITING_FOR_REMINDER = "reminder"
ASKING_CHOICE = "choise"

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
    if current_jobs:
        for job in current_jobs:
            job.schedule_removal()

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

    choice = query.data # choice_day, choice_hour или choice_day_and_hour
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
    remove_job_if_exists(str(chat_id), context)

    moscow_tz = pytz.timezone('Europe/Moscow')
    context.job_queue.run_daily(reminder_for_the_day, time=datetime.time(hour=18, minute=0, tzinfo=moscow_tz),
                                data={"chat_id": chat_id, "choice": choice}, name=str(chat_id))

    context.user_data['choice'] = choice

    return ConversationHandler.END

async def reminder_for_the_day(context):
    """Отправляет сообщение-напоминание ."""
    job_data = context.job.data
    chat_id = job_data.get("chat_id")
    choice = job_data.get("choice")

    calendar = await find_the_calendar()
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
                text = f"🔔НАПОМИНАНИЕ!🔔\n\n❗Через 7 дней!\n{key},\n{stage[0]}\n\n📆Время проведения этапа:\n {stage[1]}"
                if text:
                    if chat_id:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=text
                        )
                        is_print_week = True
            if (choice == 'choice_day' or choice == 'choice_all') and diff.days == 1 and not is_print_day:
                text = f"🔔НАПОМИНАНИЕ!🔔\n\n❗Через 1 день\n{key},\n{stage[0]}\n\n📆Время проведения этапа:\n {stage[1]}"
                if text:
                    if chat_id:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=text
                        )
                        is_print_day = False
            if (choice == 'choice_hour' or choice == 'choice_all') and diff.days == 0:
                time_reminder = event_time - datetime.timedelta(hours=1)
                job_name = f"{chat_id}_hour_{key}_{stage[0]}"
                context.job_queue.run_once(reminder_for_the_hour, when=time_reminder,
                        data={"chat_id": chat_id, "choice": choice, "data": [key, stage]}, name=job_name)

                print('Установил напоминание на', time_reminder)


async def reminder_for_the_hour(context):
    """Отправляет сообщение-напоминание ."""
    job_data = context.job.data
    chat_id = job_data.get("chat_id")
    key, stage = job_data.get("data")

    if chat_id:
        text = f"🔔НАПОМИНАНИЕ!🔔\n\n❗Остался 1 час!\n{key},\n{stage[0]}\n\n📆Время проведения этапа:\n {stage[1]}"
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
        chat_id = int(chat_id_str)
        remove_job_if_exists(str(chat_id), app)

        moscow_tz = pytz.timezone('Europe/Moscow')
        app.job_queue.run_daily(reminder_for_the_day, time=datetime.time(hour=18, minute=0, tzinfo=moscow_tz),
                                    data={"chat_id": chat_id, "choice": choice}, name=str(chat_id))


async def find_the_calendar():
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
    return data


async def find_the_top_leaders():
    async with aiohttp.ClientSession() as session:
        async with session.get("https://www.championat.com/auto/_f1/tournament/1032/",
                               headers=headers) as response:
            res = await response.text()
    soup = BeautifulSoup(res, 'lxml')

    top_leaders = soup.find_all(['span', 'td'], class_=['table-item__name', '_right'])
    pilots = []
    teams = []
    for i in range(0, len(top_leaders), 2):
        if re.search(r'[a-zA-Z]', top_leaders[i].text.strip()):
            teams.append([top_leaders[i].text.strip(), top_leaders[i + 1].text.strip()])
        else:
            pilots.append([top_leaders[i].text.strip(), top_leaders[i + 1].text.strip()])
    return pilots, teams


async def find_pilots():
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
    ans = {}
    for i in range(0, len(pilots), 5):
        ans[pilots[i].text.strip()] = {}
        ans[pilots[i].text.strip()]['Команда'] = pilots[i + 1].text.strip()
        ans[pilots[i].text.strip()]['День рождения'] = pilots[i + 2].text.strip()
        if pilots[i + 3].text.strip():
            ans[pilots[i].text.strip()]['Рост'] = pilots[i + 3].text.strip()
        if pilots[i + 4].text.strip():
            ans[pilots[i].text.strip()]['Вес'] = pilots[i + 4].text.strip()
    ans = dict(sorted(ans.items()))
    return ans


async def print_the_calendar(update, context):
    calendar = await find_the_calendar()
    print_data = ''
    for key, data in calendar.items():
        print_data += ' '.join([key, data[0][1], '-', data[-1][1]]) + '\n' + '\n'
    await update.message.reply_text(print_data)


async def print_top_leaders(update, context):
    top_pilots, top_teams = await find_the_top_leaders()
    ans = '🏅Личный зачёт:\n\n'
    for leader in top_pilots:
        ans += f'{leader[0]} -  {leader[1]}\n\n'
    await update.message.reply_text(ans)
    ans = '🏆Командный зачёт:\n\n'
    for leader in top_teams:
        ans += f'{leader[0]} -  {leader[1]}\n\n'
    await update.message.reply_text(ans)


async def print_pilots(update, context):
    pilots = await find_pilots()
    print_data = ''
    for name, data in pilots.items():
        print_data += name + ' - ' + data['Команда'] + '\n'
        print_data += 'Дата рождения: ' + data['День рождения'] + '\n' + '\n'
    await update.message.reply_text(print_data)


async def help(update, context):
    await update.message.reply_text('''
/start - старт, установление напоминаний\n(/stop_reminder - отмена напоминаний)
/calendar - расписание этапов
/top_leaders - очки лидеров
/pilots - информация о пилотах
/search - поиск(/cancel - завершение поиска)
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
        calendar = await find_the_calendar()
        for key, data in calendar.items():
            data = '\n\n'.join([stage[0] + ' ' + stage[1] for stage in data])
            if (query.lower() == ' '.join(key.lower().split()[:2])[:-1] or
                    query.lower() in key.lower() or query.lower() in data):
                result = f'🏁Нашли в календаре:\n {key}\n {data}'
                key = key.split()[-2] + ' ' + key.split()[-1]
                try:
                    await context.bot.send_photo(chat_id=update.message.chat_id,
                                             photo=f'photo/tracks/{TRACKS[key][0]}', caption=key)
                except (KeyError, BadRequest):
                    ...
                break
    elif category == 'pilots':
        pilots = await find_pilots()
        for key, data in pilots.items():
            if query.lower() in key.lower():
                result = f'{key}\n'
                for parameter, value in data.items():
                    result += parameter + ': ' + value + '\n'
                result += INFO[key][1]
                try:
                    await context.bot.send_photo(chat_id=update.message.chat_id,
                                             photo=f'photo/{INFO[key][0]}', caption=key)
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


async def cancel(update, context):
    """Выход из режима поиска"""
    # Очищаем выбранную категорию
    context.user_data.pop('search_category', None)
    await update.message.reply_text(
        "🔍 Режим поиска выключен.\n"
        "Чтобы начать снова,\n"
        "напиши /search"
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




def main():
    persistence = PicklePersistence(filepath="bot_data.pickle")
    application = Application.builder().token(BOT_TOKEN).persistence(persistence).post_init(restore_all_reminders).build()

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
        entry_points=[CommandHandler('start', start)],  # start как точка входа
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

    application.add_handler(CommandHandler("calendar", print_the_calendar))
    application.add_handler(CommandHandler("top_leaders", print_top_leaders))
    application.add_handler(CommandHandler("pilots", print_pilots))
    application.add_handler(CommandHandler("help", help))
    application.add_handler(CommandHandler("stop_reminder", stop_reminder))

    application.run_polling()


if __name__ == '__main__':
    main()
