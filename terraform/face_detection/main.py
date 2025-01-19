import boto3
import os
import json
from io import BytesIO
# import face_recognition

PHOTOS_BUCKET_NAME = os.getenv('PHOTOS_BUCKET_NAME')
QUEUE_URL = os.getenv('QUEUE_URL')
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')

s3 = boto3.client(
    's3',
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name='ru-central1',
    endpoint_url='https://storage.yandexcloud.net',
)
sqs = boto3.client(
    'sqs',
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name='ru-central1',
    endpoint_url='https://message-queue.api.cloud.yandex.net'
)

def handler(event, context):
    for record in event['messages']:
        object_key = record['details']['object_id']

        # response = s3.get_object(Bucket=BUCKET_NAME, Key=object_key)
        # image = face_recognition.load_image_file(BytesIO(response['Body'].read()))

        # face_locations = face_recognition.face_locations(image)
        # for face in face_locations:
        task = {
            'original_photo_key': object_key,
            'face_coordinates': [0, 0, 0, 0],
        }
        sqs.send_message(QueueUrl=QUEUE_URL, MessageBody=json.dumps(task))

    return {'statusCode': 200, 'body': 'OK'}