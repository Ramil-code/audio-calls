# backend/rooms.py — POST /rooms
import os, json, time, secrets, string, uuid
import boto3
from common_jwt import sign

ddb = boto3.resource('dynamodb')
rooms_table = ddb.Table(os.environ['TABLE_ROOMS'])
invites_table = ddb.Table(os.environ['TABLE_INVITES'])

JWT_SECRET = os.environ['JWT_SECRET']
ADMIN_API_KEY = os.environ['ADMIN_API_KEY']

INVITE_TTL_MINUTES_DEFAULT = int(os.getenv('InviteTTLMinutes', '45'))
ROOM_TTL_DAYS_DEFAULT = int(os.getenv('RoomTTLDays', '1'))

def _short_id(n=8):
    alphabet = string.ascii_lowercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(n))

def _new_invite(room_id: str, role: str, invite_minutes: int):
    now = int(time.time())
    invite_id = _short_id(12)
    exp = now + invite_minutes * 60
    ttl = exp + 3600  
    invites_table.put_item(Item={
        'inviteId': invite_id,
        'roomId': room_id,
        'role': role,
        'exp': exp,
        'used': False,
        'ttl': ttl,
    })
    token = sign({
        'roomId': room_id,
        'inviteId': invite_id,
        'role': role,
        'nonce': str(uuid.uuid4()),
    }, JWT_SECRET, exp_seconds=invite_minutes * 60)
    return {'inviteId': invite_id, 'token': token, 'exp': exp}

def handler(event, context):
    admin_key = event.get('headers', {}).get('X-Admin-Key') or event.get('headers', {}).get('x-admin-key')
    if not admin_key or admin_key != ADMIN_API_KEY:
        return {"statusCode": 401, "body": "Unauthorized"}

    try:
        body = json.loads(event.get('body') or '{}')
    except Exception:
        body = {}

    invite_minutes = int(body.get('inviteMinutes', INVITE_TTL_MINUTES_DEFAULT))
    room_ttl_days = int(body.get('roomTtlDays', ROOM_TTL_DAYS_DEFAULT))

    now = int(time.time())
    room_id = _short_id(10)
    room_ttl = now + room_ttl_days * 86400

    rooms_table.put_item(Item={
        'roomId': room_id,
        'status': 'active',
        'createdAt': now,
        'ttl': room_ttl,
    })

    host_inv = _new_invite(room_id, 'host', invite_minutes)
    guest_inv = _new_invite(room_id, 'guest', invite_minutes)

    resp = {
        'roomId': room_id,
        'invites': {
            'host': host_inv,
            'guest': guest_inv
        }
    }

    return {
        "statusCode": 200,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Content-Type": "application/json"
        },
        "body": json.dumps(resp)
    }
