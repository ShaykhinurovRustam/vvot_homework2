import os
import ydb
import ydb.iam
import json
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.types import Update

logging.basicConfig(level=logging.DEBUG)

bot = Bot(token=os.getenv('TELEGRAM_API_KEY'))
dp = Dispatcher(bot)

DB_URL = os.getenv('DB_URL').split('/?database=')
DB_ENDPOINT = DB_URL[0]
DB_DATABASE = DB_URL[1]
GATEWAY_URL = os.getenv('GATEWAY_URL')


def get_driver():
    credentials = ydb.iam.MetadataUrlCredentials()
    driver_config = ydb.DriverConfig(
        endpoint=DB_ENDPOINT,
        database=DB_DATABASE,
        credentials=credentials
    )
    driver = ydb.Driver(driver_config)
    driver.wait(timeout=5)
    
    return driver


@dp.message_handler(commands=['getface'])
async def get_face(message: types.Message):
    result = None

    try:
        driver = get_driver()
        session = driver.table_client.session().create()
        
        query = '''
            SELECT i.face_id AS face_id
            FROM image_faces AS i
            LEFT JOIN face_names AS f ON i.face_id = f.face_id
            WHERE f.face_id IS NULL
            LIMIT 1;
        '''
        result = session.transaction().execute(query, commit_tx=True)
    except Exception as e:
        logging.error(f'Ошибка подключения к YDB: {e}')
    finally:
        driver.stop()
        
    if result:
        try:
            face_id = result[0].rows[0]['face_id'].decode('utf-8')
            photo_url = f'https://{GATEWAY_URL}?face={face_id}'
            await message.answer_photo(photo_url)
        except:
            await message.answer('Нет доступных лиц без имени.')
    else:
        await message.answer('Нет доступных лиц без имени.')


@dp.message_handler(commands=['find'])
async def find_faces(message: types.Message):
    name = message.get_args()
    results = None

    try:
        driver = get_driver()
        session = driver.table_client.session().create()
        
        query = f'''
            SELECT image_faces.image_id AS image_id
            FROM image_faces
            JOIN face_names ON image_faces.face_id = face_names.face_id
            WHERE face_names.face_name = '{name}';
        '''
        results = session.transaction().execute(query, commit_tx=True)
    except Exception as e:
        logging.error(f'Ошибка подключения к YDB: {e}')
    finally:
        driver.stop()

    if results and results[0].rows:
        for row in results[0].rows:
            image_id = row['image_id'].decode('utf-8')
            photo_url = f'https://{GATEWAY_URL}?photo={image_id}'
            await message.answer_photo(photo_url)
    else:
        await message.answer(f'Фотографии с именем {name} не найдены.')


@dp.message_handler()
async def default_handler(message: types.Message):
    if not message.reply_to_message:
        await message.answer('Ошибка.')
        return 

    if not message.reply_to_message.photo:
        await message.answer('Ошибка.')
        return 
    
    driver = get_driver()
    session = driver.table_client.session().create()
    
    query = '''
        SELECT i.face_id AS face_id
        FROM image_faces AS i
        LEFT JOIN face_names AS f ON i.face_id = f.face_id
        WHERE f.face_id IS NULL
        LIMIT 1;
    '''
    result = session.transaction().execute(query, commit_tx=True)
    
    if not result:
        await message.answer('Ошибка.')
        return

    try:
        face_id = result[0].rows[0]['face_id'].decode('utf-8')
        name = message.text
        query = f'''
            INSERT INTO face_names (face_id, face_name)
            VALUES ('{face_id}', '{name}');
        '''
        session.transaction().execute(query, commit_tx=True)
    except:
        await message.answer('Ошибка.')


async def process_update(update_data: dict):
    Bot.set_current(bot)
    Dispatcher.set_current(dp)
    
    update = Update.to_object(update_data)
    await dp.process_update(update)

def handler(event, context):
    if event.get('httpMethod') == 'POST':
        body = event.get('body')
        if not body:
            return {'statusCode': 400, 'body': 'No body received'}

        try:
            update_data = json.loads(body)
        except json.JSONDecodeError:
            return {'statusCode': 400, 'body': 'Invalid JSON'}

        asyncio.run(process_update(update_data))
        return {'statusCode': 200, 'body': 'OK'}

    return {'statusCode': 405, 'body': 'Method Not Allowed'}