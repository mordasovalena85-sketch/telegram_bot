import requests
from datetime import datetime

from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import pprint
from dotenv import load_dotenv
import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, MessageHandler, filters, CommandHandler, ConversationHandler
import json

from data.pilots_info import INFO

WAITING_FOR_QUERY = 1


load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

ua = UserAgent()
random_user_agent = ua.random
headers = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "User-Agent": random_user_agent
}


def find_the_calendar():
    res = requests.get("https://www.championat.com/auto/_f1/tournament/1032/calendar/", headers=headers)
    soup = BeautifulSoup(res.text, 'lxml')

    calendar_title = soup.find_all('div', class_='tournament-calendar__title')
    calendar_name = soup.find_all('td', class_='tournament-calendar__name')
    calendar_date = soup.find_all('td', class_='tournament-calendar__date')
    data = {}

    try:
        last_data = datetime.strptime(calendar_date[0].text.strip(), "%d.%m.%Y %H:%M")
    except ValueError:
        last_data = datetime.strptime(calendar_date[0].text.strip(), "%d.%m.%Y")
    for line in calendar_title:
        data[line.text.strip()] = []
        while calendar_name:
            try:
                present_data = datetime.strptime(calendar_date[0].text.strip(), "%d.%m.%Y %H:%M")
            except ValueError:
                present_data = datetime.strptime(calendar_date[0].text.strip(), "%d.%m.%Y")

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


def find_the_top_leaders():
    res = requests.get("https://www.championat.com/auto/_f1/tournament/1032/", headers=headers)
    soup = BeautifulSoup(res.text, 'lxml')
    top_leaders = soup.find_all(['span', 'td'], class_=['table-item__name', '_right'])
    ans = ''
    for i in range(0, len(top_leaders), 2):
        ans += top_leaders[i].text.strip() + '\n' + 'Кол-во очков: ' + top_leaders[i + 1].text.strip() + '\n\n'
    return ans


def find_pilots():
    res = requests.get("https://www.championat.com/auto/_f1/tournament/1032/players/", headers=headers)
    soup = BeautifulSoup(res.text, 'lxml')

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
    calendar = find_the_calendar()
    print_data = ''
    for key, data in calendar.items():
        print_data += ' '.join([key, data[0][1], '-', data[-1][1]]) + '\n' + '\n'
    await update.message.reply_text(print_data)


async def print_top_leaders(update, context):
    await update.message.reply_text(find_the_top_leaders())


async def print_pilots(update, context):
    pilots = find_pilots()
    print_data = ''
    for name, data in pilots.items():
        print_data += name + ' - ' + data['Команда'] + '\n'
        print_data += 'Дата рождения: ' + data['День рождения'] + '\n' + '\n'
    await update.message.reply_text(print_data)


async def help(update, context):
    await update.message.reply_text('''
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
        '✅ имени пилота\n'
        '✅ команде\n'
        '✅ названию этапа/дате/городу проведения\n\n'
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
        f"Для выхода напишите /cancel"
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
        calendar = find_the_calendar()
        for key, data in calendar.items():
            data = '\n\n'.join([stage[0] + ' ' + stage[1] for stage in data])
            if (query.lower() == ' '.join(key.lower().split()[:2])[:-1] or
                    query.lower() in key.lower() or query.lower() in data):
                result = f'Нашли в календаре:\n {key}\n {data}'
    elif category == 'pilots':
        pilots = find_pilots()
        for key, data in pilots.items():
            if query.lower() in key.lower():
                result = f'{key}\n'
                for parameter, value in data.items():
                    result += parameter + ': ' + value + '\n'
                result += INFO[key][1]
                await context.bot.send_photo(chat_id=update.message.chat_id,
                                             photo=f'photo/{INFO[key][0]}', caption=key)
    await update.message.reply_text(f"🔍 Результат по запросу '{query}'\n"
                                    f"{result}")

    # Остаемся в режиме поиска
    return WAITING_FOR_QUERY


async def bad_commands(update, context):
    command = update.message.text

    if command == '/cancel':
        return await cancel(update, context)

    await update.message.reply_text(
        "Во время поиска доступна только команда /cancel\n"
        "Введите текст для поиска или /cancel для выхода"
    )
    return WAITING_FOR_QUERY


async def cancel(update, context):
    """Выход из режима поиска"""
    # Очищаем выбранную категорию
    context.user_data.pop('search_category', None)
    await update.message.reply_text(
        "🔍 Режим поиска выключен.\n"
        "Чтобы начать снова, напиши /search"
    )
    return ConversationHandler.END


def main():
    application = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
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

    # Добавляем обработчики
    application.add_handler(conv_handler)

    application.add_handler(CommandHandler("calendar", print_the_calendar))
    application.add_handler(CommandHandler("top_leaders", print_top_leaders))
    application.add_handler(CommandHandler("pilots", print_pilots))
    application.add_handler(CommandHandler("help", help))

    application.run_polling()


if __name__ == '__main__':
    main()
