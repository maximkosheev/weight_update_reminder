import logging
import requests

from fatsecret import PLATFORM_URL, FatSecretError, FatSecretContext
from fatsecret.oauth import OAuthHelper

logger = logging.getLogger(__name__)


class FatSecretProfile:
    def __init__(self, token, secret, fat_secret_context: FatSecretContext):
        self.token = token
        self.secret = secret
        self.context = fat_secret_context

    def get_status(self):
        profile_data = self._fetch("GET", "profile.get",
                                   self.context.consumer_key, self.context.consumer_secret)
        return profile_data["profile"]

    def _fetch(self,
               http_method: str,
               platform_method: str,
               consumer_key: str,
               consumer_secret: str,
               platform_method_params: dict = None) -> dict:
        """
        Получение данных, привязанных к профилю пользователю FatSecret
        :param http_method: тип метода в запросе GET, POST, DELETE и пр.
        :param platform_method: платформенный метод, например, profile.get
        :param platform_method_params: параметры платформенного метода
        :return:
        """
        request_params = {
            "method": platform_method,
            "format": "json",
            "oauth_token": self.token
        }
        if platform_method_params is not None:
            for param in platform_method_params:
                request_params[param] = platform_method_params[param]
        request = OAuthHelper.build_request(http_method,
                                            PLATFORM_URL,
                                            request_params,
                                            consumer_key,
                                            consumer_secret,
                                            self.secret)
        response = requests.get(PLATFORM_URL, params=request.request_params)
        if response.ok:
            body = response.json()
            if "error" in body:
                logger.error(f"FatSecret return error:{body['error']}")
                raise FatSecretError(f"FatSecret return error with code {body['error']['code']}")
            else:
                return body
        else:
            logger.error(f"FatSecret server error. Code: {response.status_code}, Reason: {response.reason}")
            raise FatSecretError(f"FatSecretServer error: {response.status_code}")
