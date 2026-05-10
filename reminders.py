import datetime
import json
import os

import pytz

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler

from finding_data import find_the_calendar, upcoming_event
from subscribe_to_news import newsletter

ASKING_CHOICE = 'asking_choice'
WAITING_FOR_REMINDER = 'waiting_for_reminder'


def remove_job_if_exists(name, context):
    """Удаляет напоминание с заданным именем,
    Возвращает, было ли напоминание или нет"""
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
    """Начало работа бота, вопрос об установке напоминаний"""
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
    """Ответ на функцию start, выбор частоты напоминаний"""
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
    """Установка напоминания"""
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
        f"⚙Чтобы изменить настройки, снова напиши /start\n"
        f"⚙Чтобы отменить напоминания, напиши /stop_reminder"
    )

    chat_id = update.callback_query.message.chat_id
    r = remove_job_if_exists(str(chat_id), context)  # удаляем все напоминания

    moscow_tz = pytz.timezone('Europe/Moscow')
    # устанавливаем ежедневную задачу для напоминаний
    context.job_queue.run_daily(reminder_for_the_day, time=datetime.time(hour=12, minute=0, tzinfo=moscow_tz),
                                data={"chat_id": chat_id, "choice": choice}, name=str(chat_id))

    context.user_data['choice'] = choice  # сохраняем периодичность напоминаний пользователя

    return ConversationHandler.END


async def reminder_for_the_day(context):
    """Отправляет сообщение-напоминание"""
    job_data = context.job.data
    chat_id = job_data.get("chat_id")
    choice = job_data.get("choice")

    if not os.path.exists('data/calendar.json'):
        await find_the_calendar(context)
    # если до ближайшей гонки меньше часа, обновляем календарь
    elif await upcoming_event() < 1:
        await find_the_calendar(context)
    with open('data/calendar.json', 'r', encoding='utf-8') as f:
        stages = json.load(f)
    tz = pytz.timezone('Europe/Moscow')
    current_time = datetime.datetime.now(tz)

    is_print_week, is_print_day = False, False
    for key, data in stages.items():
        for stage in data:
            # форматируем время гонки
            if ' ' in stage[1] and ':' in stage[1]:
                event_time = tz.localize(datetime.datetime.strptime(stage[1], "%d.%m.%Y %H:%M"))
            else:
                event_time = tz.localize(datetime.datetime.strptime(stage[1], '%d.%m.%Y'))
            diff = event_time - current_time  # количество времени до гонки

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
                # если гонка сегодня, то ставим напоминание за час до времени гонки по календарю
                time_reminder = event_time - datetime.timedelta(hours=1)
                job_name = f"{chat_id}_hour"
                context.job_queue.run_once(reminder_for_the_hour, when=time_reminder,
                                           data={"chat_id": chat_id, "choice": choice, "data": [key, stage]},
                                           name=job_name)


async def reminder_for_the_hour(context):
    """Отправляет сообщение-напоминание за час до гонки"""
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
    """Восстанавливает задания после перезапуска бота"""
    persistence = app.persistence
    if persistence is None:
        return

    # Получаем все сохранённые user_data (ключ - chat_id, значение - словарь)
    all_user_data = getattr(persistence, 'user_data', {})

    for chat_id_str, user_data in all_user_data.items():
        choice = user_data.get('choice')
        if not choice:
            continue
        chat_id = int(chat_id_str)
        r = remove_job_if_exists(str(chat_id), app)  # удаляем задания, если они есть

        moscow_tz = pytz.timezone('Europe/Moscow')
        # устанавливаем ежедневные напоминания
        app.job_queue.run_daily(reminder_for_the_day, time=datetime.time(hour=12, minute=0, tzinfo=moscow_tz),
                                data={"chat_id": chat_id, "choice": choice}, name=str(chat_id))

        # восстанавливаем подписку на новости, если она есть
        is_subscribe = user_data.get('subscribe_to_news')
        if is_subscribe:
            app.job_queue.run_repeating(newsletter, interval=600, first=5,
                                        data={"chat_id": chat_id}, name=f'news_{str(chat_id)}')


async def stop_reminder(update, context):
    """Отключение напоминания о гонках"""
    chat_id = update.effective_chat.id
    job_name = str(chat_id)
    removed = remove_job_if_exists(job_name, context)

    # Очищаем сохранённый выбор в user_data (если есть)
    context.user_data.pop('choice', None)

    if removed:
        await update.message.reply_text("✅ Напоминания о гонках отключены.")
    else:
        await update.message.reply_text("❌ У вас не было активных напоминаний.")
