import os, json, time
import boto3
from common_jwt import verify

chime = boto3.client('chime-sdk-meetings')
ddb = boto3.resource('dynamodb')
rooms_table = ddb.Table(os.environ['TABLE_ROOMS'])
invites_table = ddb.Table(os.environ['TABLE_INVITES'])

JWT_SECRET = os.environ['JWT_SECRET']
MEDIA_REGION = os.environ.get('MEDIA_REGION', 'eu-central-1')

def handler(event, context):
    try:
        room_id = event.get('pathParameters', {}).get('roomId')
        body = json.loads(event.get('body') or '{}')
        token = body.get('t')

        if not room_id or not token:
            return {"statusCode": 400, "body": "roomId and token required"}

        # Verify token
        payload = verify(token, JWT_SECRET)
        if payload.get('roomId') != room_id:
            return {"statusCode": 403, "body": "token/room mismatch"}
        invite_id = payload.get('inviteId')
        role = payload.get('role')

        # Fetch invite
        inv = invites_table.get_item(Key={'inviteId': invite_id}).get('Item')
        if not inv or inv.get('roomId') != room_id or inv.get('role') != role:
            return {"statusCode": 403, "body": "invalid invite"}
        if bool(inv.get('used')):
            return {"statusCode": 409, "body": "invite already used"}
        if int(inv.get('exp', 0)) <= int(time.time()):
            return {"statusCode": 410, "body": "invite expired"}

        # Get room
        room = rooms_table.get_item(Key={'roomId': room_id}).get('Item')
        if not room or room.get('status') != 'active':
            return {"statusCode": 404, "body": "room not active"}

        # Ensure meeting exists
        meeting_id = room.get('meetingId')
        if not meeting_id:
            ext_id = (room_id or '')[:64]
            meeting = chime.create_meeting(
                ClientRequestToken=room_id,
                MediaRegion=MEDIA_REGION,
                ExternalMeetingId=ext_id,
            )['Meeting']
            meeting_id = meeting['MeetingId']
            rooms_table.update_item(
                Key={'roomId': room_id},
                UpdateExpression='SET meetingId = :m',
                ExpressionAttributeValues={':m': meeting_id}
            )
        else:
            meeting = chime.get_meeting(MeetingId=meeting_id)['Meeting']

        # Create attendee
        attendee = chime.create_attendee(
            MeetingId=meeting_id,
            ExternalUserId=invite_id[:64]
        )['Attendee']

        # Mark invite as used (idempotent: only if not used)
        try:
            invites_table.update_item(
                Key={'inviteId': invite_id},
                UpdateExpression='SET #u = :true, usedAt = :now',
                ConditionExpression='attribute_not_exists(#u) OR #u = :false',
                ExpressionAttributeNames={'#u': 'used'},
                ExpressionAttributeValues={':true': True, ':false': False, ':now': int(time.time())}
            )
        except ddb.meta.client.exceptions.ConditionalCheckFailedException:  # type: ignore
            return {"statusCode": 409, "body": "invite already used"}

        return {
            "statusCode": 200,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            },
            "body": json.dumps({
                'meeting': meeting,
                'attendee': attendee,
                'role': role
            })
        }

    except Exception as e:
        return {"statusCode": 500, "body": str(e)}
