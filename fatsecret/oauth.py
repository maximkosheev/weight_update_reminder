import time
import uuid
import hmac
import base64

from hashlib import sha1


def percent_encoding(string) -> str:
    result = ''
    accepted = [c for c in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._~'.encode('utf-8')]
    for char in string.encode('utf-8'):
        result += chr(char) if char in accepted else '%{}'.format(hex(char)[2:]).upper()
    return result


def calc_signature(http_method: str, url: str, request_params: dict, consumer_secret: str, signature_key: str):
    normalized_request_params = []
    for k, v in request_params.items():
        normalized_request_params.append("{}={}".format(k, percent_encoding(v)))
    normalized_request_params.sort()
    normalized_request_params_string = '&'.join(normalized_request_params)
    signature_base_string = '&'.join([http_method,
                                      percent_encoding(url),
                                      percent_encoding(normalized_request_params_string)])
    signature_key = '&'.join([consumer_secret, signature_key])
    hashed = hmac.new(signature_key.encode("utf-8"), signature_base_string.encode("utf-8"), sha1)
    signature = base64.encodebytes(hashed.digest()).decode('utf-8').rstrip("\n")
    return signature


class OAuthRequest:
    def __init__(self, http_method, url, request_params, consumer_key, consumer_secret, oauth_secret):
        self.request_params = request_params
        self.request_params['oauth_consumer_key'] = consumer_key
        self.request_params['oauth_signature_method'] = 'HMAC-SHA1'
        self.request_params['oauth_timestamp'] = str(int(time.time()))
        self.request_params['oauth_nonce'] = uuid.uuid4().hex
        self.request_params['oauth_version'] = '1.0'
        signatory_key = oauth_secret if oauth_secret is not None else ""
        self.request_params['oauth_signature'] = calc_signature(http_method,
                                                                url,
                                                                self.request_params,
                                                                consumer_secret,
                                                                oauth_secret)


class OAuthHelper:
    @staticmethod
    def build_request(http_method, url, request_params, consumer_key, consumer_secret, oauth_secret) -> OAuthRequest:
        return OAuthRequest(http_method, url, request_params, consumer_key, consumer_secret, oauth_secret)
