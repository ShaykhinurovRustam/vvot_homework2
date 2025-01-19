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


@dp.message_handler(commands=['getface'])
async def get_face(message: types.Message):
    
    credentials = ydb.iam.MetadataUrlCredentials()
    driver_config = ydb.DriverConfig(
        endpoint=DB_ENDPOINT,
        database=DB_DATABASE,
        credentials=credentials
    )
    driver = ydb.Driver(driver_config)
    try:
        driver.wait(timeout=5)
        
        session = driver.table_client.session().create()
        
        query = '''
        SELECT face_id FROM image_faces LIMIT 1;
        '''
        result = session.transaction().execute(query, commit_tx=True)
    except Exception as e:
        result = None
        logging.debug(f'Ошибка подключения к YDB: {e}')
    finally:
        driver.stop()
        
    if result:
        face_id = result[0].rows[0]['face_id'].decode('utf-8')
        photo_url = f'https://{GATEWAY_URL}?face={face_id}'
        await message.answer_photo(photo_url)
    else:
        await message.answer('Нет доступных лиц без имени.')


@dp.message_handler(commands=['find'])
async def find_faces(message: types.Message):
    name = message.get_args()

    credentials = ydb.iam.MetadataUrlCredentials()
    driver_config = ydb.DriverConfig(
        endpoint=DB_ENDPOINT,
        database=DB_DATABASE,
        credentials=credentials
    )
    driver = ydb.Driver(driver_config)
    
    results = None

    try:
        driver.wait(timeout=5)

        with driver.table_client.session().create() as session:
            query = '''
                DECLARE $face_name AS Utf8;
                
                SELECT image_faces.image_id
                FROM image_faces
                JOIN face_names ON image_faces.face_id = image_faces.face_id
                WHERE face_names.face_name = %face_name
            '''
            
            params = {"$face_name": name}
            
            results = session.transaction().execute(query, params=params, commit_tx=True)
    except Exception as e:
        logging.debug(f'Ошибка подключения к YDB: {e}')
    finally:
        driver.stop()

    if results and results[0].rows:
        for row in results[0].rows:
            image_id = row["image_id"]
            photo_url = f'{GATEWAY_URL}?photo={image_id}'
            await message.answer_photo(photo_url)
    else:
        await message.answer(f'Фотографии с именем {name} не найдены.')


@dp.message_handler()
async def default_handler(message: types.Message):
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