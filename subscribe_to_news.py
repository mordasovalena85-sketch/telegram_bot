import json
import os
from urllib.parse import urljoin

import aiohttp

from bs4 import BeautifulSoup

from finding_data import get_headers


async def subscribe_to_news(update, context):
    """Подписка на новости"""
    chat_id = update.effective_chat.id

    await update.message.reply_text(
        '✅Ты подписался на новостную рассылку!\n🚫Чтобы отписаться напиши /unsubscribe_from_news')

    # удаление старых задач
    jobs = context.job_queue.get_jobs_by_name(f'news_{str(chat_id)}')
    if jobs:
        for job in jobs:
            job.schedule_removal()
    context.job_queue.run_repeating(newsletter, interval=600, first=5,
                                    data={"chat_id": chat_id}, name=f'news_{str(chat_id)}')
    context.user_data['subscribe_to_news'] = True  # сохранение информации о подписке


async def newsletter(context):
    """Парсинг сайта для проверки новостей раз в 10 минут,
    отправление новостей"""
    job_data = context.job.data
    chat_id = job_data.get("chat_id")

    url = 'https://www.f1news.ru'
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=get_headers()) as response:
            res = await response.text()
    soup = BeautifulSoup(res, 'lxml')

    link = soup.find(class_='b-news-list__title')
    absolute_link = ''
    # получаем из сайта ссылку на новость
    if link:
        link = link.get('href')
        absolute_link = urljoin(url, link)
    if absolute_link:
        # парсим новость по этой абсолютной ссылке
        async with aiohttp.ClientSession() as session:
            async with session.get(absolute_link, headers=get_headers()) as response:
                res = await response.text()
        soup = BeautifulSoup(res, 'lxml')

        try:
            title = soup.find('div', class_='post_head').text
            text = soup.find('div', class_='post_content').text
        except AttributeError:
            return

        if os.path.exists('data/last_news.json'):
            with open('data/last_news.json', 'r', encoding='utf-8') as f:
                last_news_dict = json.load(f)
        else:
            last_news_dict = {}

        title = [line.strip() for line in title.splitlines() if line.strip()]
        text = '\n\n'.join(text.split('\n'))

        last_title_for_user = last_news_dict.get(str(chat_id), '')

        if last_title_for_user != title[0]:
            await context.bot.send_message(
                    chat_id=chat_id,
                    text='\n'.join(title[:-1]) + text
                )
            last_news_dict[str(chat_id)] = title[0]
            with open('data/last_news.json', 'w', encoding='utf-8') as f:
                    json.dump(last_news_dict, f, ensure_ascii=False, indent=4)


async def unsubscribe_from_news(update, context):
    """Отписка от новостной рассылки"""
    context.user_data['subscribe_to_news'] = False

    chat_id = update.effective_chat.id
    name = f'news_{str(chat_id)}'
    jobs = context.job_queue.get_jobs_by_name(name)
    if jobs:
        for job in jobs:
            job.schedule_removal()
        await update.message.reply_text('🔕Подписка на новости отключена!')
    else:
        await update.message.reply_text('❗Вы не были подписаны на новостную рассылку')
