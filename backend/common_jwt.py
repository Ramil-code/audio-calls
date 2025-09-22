# Minimal HS256 JWT (no external deps)
import hmac, hashlib, json, time, base64

ALG = 'HS256'


def _b64url_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b'=').decode('ascii')


def _b64url_decode(s: str) -> bytes:
    s += '=' * (-len(s) % 4)
    return base64.urlsafe_b64decode(s.encode('ascii'))


def sign(payload: dict, secret: str, exp_seconds: int) -> str:
    header = {"alg": ALG, "typ": "JWT"}
    now = int(time.time())
    body = dict(payload)
    body.setdefault('iat', now)
    body.setdefault('nbf', now)
    body['exp'] = now + exp_seconds
    header_b64 = _b64url_encode(json.dumps(header, separators=(',', ':')).encode())
    payload_b64 = _b64url_encode(json.dumps(body, separators=(',', ':')).encode())
    signing_input = f"{header_b64}.{payload_b64}".encode()
    sig = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    token = f"{header_b64}.{payload_b64}.{_b64url_encode(sig)}"
    return token


def verify(token: str, secret: str) -> dict:
    try:
        header_b64, payload_b64, sig_b64 = token.split('.')
    except ValueError:
        raise ValueError('malformed token')
    signing_input = f"{header_b64}.{payload_b64}".encode()
    expected = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    actual = _b64url_decode(sig_b64)
    if not hmac.compare_digest(expected, actual):
        raise ValueError('bad signature')
    payload = json.loads(_b64url_decode(payload_b64))
    now = int(time.time())
    if 'nbf' in payload and now < int(payload['nbf']):
        raise ValueError('token not yet valid')
    if 'exp' in payload and now >= int(payload['exp']):
        raise ValueError('token expired')
    return payload
