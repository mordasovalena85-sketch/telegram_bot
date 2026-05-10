import random

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler

from data.data import TRACKS

CHECKING_RESPONSE = 'checking_response'
WAITING_FOR_GAME = 'waiting_for_game'


async def send_new_question(update, context):
    """Генерирует новый вопрос и отправляет его пользователю"""
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
        caption="🧭В какой стране находится эта трасса?",
        reply_markup=reply_markup
    )


async def game_start(update, context):
    """Старт игры"""
    await update.message.reply_text(
        "🌍Твоя задача отгадать место, где находится трасса!\n"
        "🌄Я буду отправлять фотографии, а ты из предложенных вариантов должен выбрать правильный!"
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
        await query.edit_message_text("🏁Игра началась!")
        await send_new_question(update, context)
        return CHECKING_RESPONSE

    elif query.data == 'no':
        await query.edit_message_text("❌ Если захочешь поиграть, напиши /play")
        return ConversationHandler.END


async def checking_response(update, context):
    """Проверяет ответ пользователя и сразу задаёт следующий вопрос"""
    query = update.callback_query
    await query.answer()

    right_answer = context.user_data.get('right_answer')
    user_answer = query.data

    if user_answer == right_answer:
        await query.message.reply_text("✅Правильно!")
    else:
        await query.message.reply_text(f"❌Неправильно( Правильный ответ: {right_answer}")

    await send_new_question(update, context)
    return CHECKING_RESPONSE
