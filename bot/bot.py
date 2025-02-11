import html
import json
import logging
import os
import traceback
from datetime import datetime as dt

import requests
from dotenv import load_dotenv
from telegram import InputFile, ParseMode
from telegram.ext import CommandHandler, Defaults, Updater

logger = logging.getLogger(__name__)
logging.getLogger('urllib3').setLevel(logging.WARNING)

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
BOT_USERS_CHAT_ID = os.getenv('BOT_USERS_CHAT_ID').split(',')
BOT_ADMIN_CHAT_ID = os.getenv('BOT_ADMIN_CHAT_ID').split(',')
LK_CHECK_INTERVAL = int(os.getenv('LK_CHECK_INTERVAL', 30))
ENTRY_FILE = os.getenv('ENTRY_FILE')

COOKIES = {
    'SessionId': os.getenv('TOKEN'),
}

HEADERS = {
    'user-agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 YaBrowser/24.1.0.0 Safari/537.36'
    ),
}

params = {
    'page': '1',
}


def start(update, context):
    """
    Обработчик команды /start.
    """
    chat_id = update.effective_chat.id
    text = (
        f"""Ваш <b>chat_id = {chat_id}</b>.
        Для получения уведомлений передайте
        его администратору бота.\n"""
    )
    context.bot.send_message(chat_id=chat_id, text=text)


def notify_users(context, publish_at, text, file_name=None):
    """
    Отправка сообщения с или без вложения.
    :param publish_at: Дата время публикации.
    :param text: Текст сообщения.
    :param file_name: Имя файла (необязательно).
    """
    message = (
        f"""❗️Обновление в МАЯК❗️\n
        <b>{dt.fromisoformat(publish_at).date()}
        {dt.fromisoformat(publish_at).time()}</b>
        {str(text)}\n"""
    )
    logger.info('Отправляю сообщение...')

    for chat_id in BOT_USERS_CHAT_ID:
        try:
            if file_name:
                with open(file_name, "rb") as file:
                    context.bot.send_document(
                        chat_id, document=InputFile(file), caption=message)
                    logger.info('Успешно отправлен файл')
            else:
                context.bot.send_message(
                    chat_id=chat_id,
                    text=message)
        except Exception as e:
            logger.info(f'Произошла ошибка при отправке сообщения в Telegram: {e}')

    if file_name:
        os.remove(str(file_name))


def error_handler(update, context):
    """
    Сообщение о возникших ошибках.
    :param update: The telegram Update class object which caused the error.
    :param context: The telegram CallbackContext class object.
    """
    tb_list = traceback.format_exception(
        None, context.error, context.error.__traceback__
    )
    tb_string = ''.join(tb_list)

    if update:
        logger.error(msg='Exception while handling an update:',
                     exc_info=context.error)
        text = (
            f"""An exception was raised while handling an update\n
            <pre>update = {html.escape(
                json.dumps(update.to_dict(), indent=2, ensure_ascii=False)
            )}
            </pre>\n\n
            <pre>context.chat_data = {html.escape(
                str(context.chat_data)
            )}</pre>\n\n
            <pre>context.user_data = {html.escape(
                str(context.user_data)
            )}</pre>\n\n
            <pre>{html.escape(tb_string)}</pre>"""
        )
    else:
        logger.error(msg='Exception was raised:', exc_info=context.error)
        text = f"""An exception was raised\n\n
        <pre>{html.escape(tb_string)}</pre>"""
    for chat_id in BOT_ADMIN_CHAT_ID:
        context.bot.send_message(chat_id=chat_id, text=text)


def file_down(id, guid, file_name):
    """
    Скачивание файла.
    :param id: id новости.
    :param guid: guid файла.
    :param file_name: Полное имя файла.
    """
    logger.info(
        f'https://ekis.moscow/lk/api/v1/newsfeeds/download/{id}/{guid}'
        )
    file_data = requests.get(
        url='https://ekis.moscow/lk/api/v1/newsfeeds/download/'
        f'{id}/{guid}', cookies=COOKIES, headers=HEADERS
        )
    logger.info(file_data.status_code)
    open(str(file_name), 'wb').write(file_data.content)
    return file_name


def req_news_ids(params):
    """
    Получение страницы новостей, возвращает список всех айди новостей.
    :param params: параметры запроса, номер страницы.
    """
    # Множество содержащие id
    news_ids = set()
    # Получаем json всех новостей, информация хранится в data
    data = requests.get(
        'https://ekis.moscow/lk/api/v1/newsfeeds/list',
        params=params, cookies=COOKIES, headers=HEADERS
        ).json().get('data')
    # Получаем id каждой новости из data и добавляем во множество
    for news in data:
        news_ids.add(news.get('id'))

    return news_ids  # Возвращаем множество с id новостей.


def req_news(context, id):
    """
    Получение информации по айди новости,
    отправка уведомления в зависимости от типа(с вложением или без).
    :param params: параметры запроса, айди новости.
    """

    # Получение информации по конкретному id новости.
    data = requests.get(('https://ekis.moscow/lk/api/v1/newsfeeds/' + str(id)),
                        cookies=COOKIES, headers=HEADERS).json().get('data')

    # Дата и время публикации.
    publish_at = data.get('publish_at')
    # Вывод в лог - дата и время публикации.
    logger.info(publish_at)
    # Заголовок публикации.
    text = data.get('title')
    # Вывод в лог - заголовок публикации.
    logger.info(text)

    # Проверяем есть ли вложения.
    if 'attachments' in data:
        # Скачиваем каждое
        for attachment in data.get('attachments'):
            # Вызов функции скачивания и передача необходимых данных.
            file = file_down(str(id), attachment.get('guid'),
                             attachment.get('file_full_name'))
            # Вызов функции отправки сообщения вместе с вложением.
            notify_users(context, publish_at, text, file)

    # Если нет вложений отправляем только сообщение с текстом.
    else:
        # Вызов функции отправки сообщения.
        notify_users(context, publish_at, text)


def req_news_up(id):
    """
    Обновление статуса новости (проставление 'Прочитана').
    :param params: параметры запроса, айди новости.
    """

    data = '{"id":' + str(id) + '}'
    upd = requests.post('https://ekis.moscow/lk/api/v1/newsfeeds/update',
                        cookies=COOKIES, headers=HEADERS, data=data).json()
    logger.info(f'Обновление статуса(прочитано): {upd}')


def check_for_updates(context):
    """
    Проверка на обновления.
    :param context: The telegram CallbackContext class object.
    """
    # Вывод токена в лог
    logger.info(f'***ТОКЕН*** {COOKIES}')

    # Получаем все айди
    news_ids = req_news_ids(params)
    logger.info(f'***ПОЛУЧЕННЫЕ АЙДИ*** {news_ids}')

    # Проверяем наличие файла с айди новостей, если нет,
    # создаем записываем в него полученные ранее айди
    if not os.path.isfile(ENTRY_FILE):
        with open(ENTRY_FILE, 'w') as f:
            json.dump(list(news_ids), f)

    # Открываем файл с айди новостей
    with open(ENTRY_FILE, 'r+') as f:
        prev_news_ids = set(json.load(f))

    # Выводим предыдущие айди
    logger.info(f'***ПРЕДЫДУЩИЕ АЙДИ*** {prev_news_ids}')
    news_diff = sorted(news_ids.difference(prev_news_ids))
    # Сравниваем, выводим разницу
    logger.info('***НОВЫЕ(РАЗНИЦА)*** '
                f'{news_diff}')

    # Для каждого айди из полученого сравнения доп запрос
    # на получение доп информации и отправки сообщений
    for diff_id in news_diff:
        req_news(context, diff_id)
        req_news_up(diff_id)

    # Добавляем к предыдущий айди разницу с новыми айди
    prev_news_ids.update(news_diff)

    # Выводим обновленный список айди
    logger.info('***ДОБАВИЛИ К ПРЕДЫДДУЩИМ НОВЫЕ АЙДИ*** '
                f'{prev_news_ids}')

    # Переводим в список, сортируем
    prev_news_ids = list(prev_news_ids)
    prev_news_ids.sort(reverse=True)

    # Проверяем длину списка и обрезаем его до 30 элементов
    if len(prev_news_ids) >= 30:
        prev_news_ids = prev_news_ids[:30]
    logger.info(f'***20 ПОСЛЕДНИХ АЙДИ*** {prev_news_ids}')

    # После всех операций записываем обновленный список айди
    with open(ENTRY_FILE, 'w') as f:
        json.dump(prev_news_ids, f)


def main():
    defaults = Defaults(parse_mode=ParseMode.HTML)

    updater = Updater(token=BOT_TOKEN, defaults=defaults)

    dispatcher = updater.dispatcher
    dispatcher.add_error_handler(error_handler)

    dispatcher.add_handler(CommandHandler('start', start))

    j = updater.job_queue
    j.run_repeating(check_for_updates, interval=LK_CHECK_INTERVAL, first=0)

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    __version__ = '0.0.1'
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO,
    )
    main()
