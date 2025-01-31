PLATFORM_URL = 'https://platform.fatsecret.com/rest/server.api'


class FatSecretError(Exception):
    def __init__(self, *args):
        if args:
            self.message = args[0]
        else:
            self.message = None

    def __str__(self):
        if self.message:
            return "FatSecret integration error: {0}".format(self.message)
        else:
            return "FatSecret integration error: unknown"


class FatSecretContext:
    def __init__(self, consumer_key, consumer_secret):
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
