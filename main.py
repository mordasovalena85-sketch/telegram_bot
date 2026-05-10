import json
import os

from dotenv import load_dotenv

from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ConversationHandler, filters, MessageHandler, PicklePersistence)

from game import game_start, play_game, checking_response, CHECKING_RESPONSE, WAITING_FOR_GAME
from search import search_query, search_start, bad_commands, button_callback, WAITING_FOR_QUERY
from reminders import reminder_callback, restore_all_reminders, choice_time_callback, stop_reminder, start, \
    ASKING_CHOICE, WAITING_FOR_REMINDER
from subscribe_to_news import subscribe_to_news, unsubscribe_from_news
from finding_data import find_the_calendar, find_pilots, find_the_top_leaders, upcoming_event, cancel

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")



async def print_the_calendar(update, context):
    """Вывод календаря гонок"""
    if not os.path.exists('data/calendar.json'):
        await find_the_calendar(context)
    # если до гонки меньше часа, обновляем календарь
    elif await upcoming_event() < 1:
        await find_the_calendar(context)
    with open('data/calendar.json', 'r', encoding='utf-8') as f:
        calendar = json.load(f)
    print_data = ''
    for key, data in calendar.items():
        print_data += ' '.join([key, data[0][1], '-', data[-1][1]]) + '\n' + '\n'
    await update.message.reply_text(print_data)


async def print_top_leaders(update, context):
    """Вывод топа лидеров"""
    if not os.path.exists('data/leaders.json'):
        await find_the_top_leaders(context)
    # если до гонки меньше часа, обновляем топ
    elif await upcoming_event() < 1:
        await find_the_top_leaders(context)
    with open('data/leaders.json', 'r', encoding='utf-8') as f:
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
    """Вывод всех пилотов"""
    if not os.path.exists('data/pilots.json'):
        await find_pilots(context)
    with open('data/pilots.json', 'r', encoding='utf-8') as f:
        pilots = json.load(f)
    print_data = ''
    for name, data in pilots.items():
        print_data += name + ' - ' + data['Команда'] + '\n'
        print_data += 'Дата рождения: ' + data['День рождения'] + '\n' + '\n'
    await update.message.reply_text(print_data)


async def help(update, context):
    await update.message.reply_text('''
🔔/start - старт, установление напоминаний
🔕/stop_reminder - отмена напоминаний

📆/calendar - расписание этапов
🏆/top_leaders - очки лидеров
🧑‍🔧/pilots - информация о пилотах

🎮/play - игра "Угадай трассу по схеме"

🗞/subscribe_to_news - подписка на новостную рассылку
🚫/unsubscribe_from_news - отписка от новостной рассылки

🔎/search - поиск
❌/cancel - завершение поиска/старта
💡/help - помощь''')


async def bad_game_commands(update, context):
    """Обработка команд во время игры"""
    command = update.message.text
    if command == '/cancel':
        return await cancel(update, context)
    await update.message.reply_text(
        "❗Во время игры доступна только команда /cancel\n"
        "Продолжайте игру или напишите /cancel для выхода"
    )
    return CHECKING_RESPONSE


def main():
    persistence = PicklePersistence(filepath="data/bot_data.pickle")
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
        interval=3600,
        first=20
    )
    application.job_queue.run_repeating(
        find_pilots,
        interval=3600,
        first=30
    )
    application.run_polling()


if __name__ == '__main__':
    main()
