import boto3
import os
import json
from io import BytesIO
from PIL import Image
import uuid
import ydb
import logging

logging.basicConfig(level=logging.DEBUG)

PHOTOS_BUCKET_NAME = os.getenv('PHOTOS_BUCKET_NAME')
FACES_BUCKET_NAME = os.getenv('FACES_BUCKET_NAME')
DB_URL = os.getenv('DB_URL').split('/?database=')
DB_ENDPOINT = DB_URL[0]
DB_DATABASE = DB_URL[1]
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')

s3 = boto3.client(
    's3',
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name='ru-central1',
    endpoint_url='https://storage.yandexcloud.net',
)


def handler(event, context):
    credentials = ydb.iam.MetadataUrlCredentials()
    driver_config = ydb.DriverConfig(
        endpoint=DB_ENDPOINT,
        database=DB_DATABASE,
        credentials=credentials,
    )
    driver = ydb.Driver(driver_config)
    driver.wait(timeout=5)

    for record in event['messages']:
        task = json.loads(record['details']['message']['body'])
        original_key = task['original_photo_key']
        # top, right, bottom, left = task['face_coordinates']

        response = s3.get_object(Bucket=PHOTOS_BUCKET_NAME, Key=original_key)
        image = Image.open(BytesIO(response['Body'].read()))

        # cropped_face = image.crop((left, top, right, bottom))
        cropped_face = image

        face_key = f'{uuid.uuid4()}.jpg'
        cropped_face.save(fp=f'/function/storage/faces/{face_key}', format='JPEG')
        
        session = driver.table_client.session().create()

        query = '''
            DECLARE $face_id AS Utf8;
            DECLARE $image_id AS Utf8;

            INSERT INTO image_faces (face_id, image_id)
            VALUES ($face_id, $image_id);
        '''
        params = {
            "$face_id": face_key,
            "$image_id": original_key
        }
        session.transaction().execute(query, parameters=params, commit_tx=True)
        
        driver.stop()

    return {'statusCode': 200, 'body': 'OK'}