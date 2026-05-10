import json
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ConversationHandler

from data.data import PILOTS, TEAMS, TRACKS
from finding_data import find_the_calendar, find_pilots, upcoming_event, cancel

WAITING_FOR_QUERY = 'waiting_for_query'


async def search_start(update, context):
    """Старт поиска,
    Выбор категории поиска"""

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
    """Ожидание запроса поиска"""
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
    """Поиск по выбранной категории"""
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

    result = None
    if category == 'stages':
        # обновляем данные если нужно
        if not os.path.exists('data/calendar.json'):
            await find_the_calendar(context)
        elif await upcoming_event() < 1:
            await find_the_calendar(context)
        with open('data/calendar.json', 'r', encoding='utf-8') as f:
            calendar = json.load(f)
        for key, data in calendar.items():
            data = '\n\n'.join([stage[0] + ' ' + stage[1] for stage in data])
            # query.lower() == ' '.join(key.lower().split()[:2])[:-1] -> номер этапа(этап 1, этап 12 и т.д.)
            if (query.lower() == ' '.join(key.lower().split()[:2])[:-1] or
                    query.lower() in key.lower() or query.lower() in data):
                result = f'🏁Нашли в календаре:\n {key}\n {data}'
                key = key.split('. ')[1]  # отделяем название города и страну
                try:
                    await context.bot.send_photo(chat_id=update.message.chat_id,
                                                 photo=f'photo/tracks/{TRACKS[key]}', caption=key)
                except (KeyError, BadRequest):
                    ...
                break
    elif category == 'pilots':
        if not os.path.exists('data/pilots.json'):
            await find_pilots(context)
        with open('data/pilots.json', 'r', encoding='utf-8') as f:
            pilots = json.load(f)
        for key, data in pilots.items():
            if query.lower() in key.lower():
                result = f'{key}\n'
                for parameter, value in data.items():
                    result += parameter + ': ' + value + '\n'
                result += PILOTS[key][1]  # добавляем интересных фактов
                try:
                    await context.bot.send_photo(chat_id=update.message.chat_id,
                                                 photo=f'photo/pilots/{PILOTS[key][0]}', caption=key)
                except (KeyError, BadRequest):
                    ...
                break
    elif category == 'teams':
        for name_team, data in TEAMS.items():
            if query.lower() in name_team.lower():
                result = data[1]  # добавляем интересных фактов
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
    """Обработка команд во время поиска"""
    command = update.message.text
    if command == '/cancel':
        return await cancel(update, context)
    await update.message.reply_text(
        "❗Во время поиска доступна только команда /cancel\n"
        "Введите текст для поиска или /cancel для выхода"
    )
    return WAITING_FOR_QUERY
