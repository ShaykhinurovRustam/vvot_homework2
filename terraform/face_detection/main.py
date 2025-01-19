import boto3
import os
import json
import cv2

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
        response = s3.get_object(Bucket=PHOTOS_BUCKET_NAME, Key=object_key)
        image_data = response['Body'].read()

        local_image_path = f'/tmp/{object_key}'
        with open(local_image_path, 'wb') as f:
            f.write(image_data)
            
        image = cv2.imread(local_image_path)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        face_coordinates = []
        
        if list(faces):
            faces = list(faces)[0]
            x, y, w, h = faces
            face_coordinates = [int(x), int(y), int(x + w), int(y + h)]
            
        task = {
            'original_photo_key': object_key,
            'face_coordinates': face_coordinates,
        }
        sqs.send_message(QueueUrl=QUEUE_URL, MessageBody=json.dumps(task))

    return {'statusCode': 200, 'body': 'OK'}