import base64

def handler(event, context):
    query_params = event.get('queryStringParameters', {})
    face_key = query_params.get('face', '')
    if not face_key.endswith('.jpg'):
        return {
            'statusCode': 400,
            'body': 'Invalid face key',
        }
    local_path = f'/function/storage/faces/{face_key}'
    try:
        with open(local_path, 'rb') as f:
            content = f.read()
        return {
            'isBase64Encoded': True,
            'statusCode': 200,
            'headers': {
                'Content-Type': 'image/jpeg'
            },
            'body': base64.b64encode(content).decode('utf-8')
        }
    except FileNotFoundError:
        return {
            'statusCode': 404,
            'body': 'Not Found'
        }