import json
import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    LICENSE_KEY = os.getenv("LICENSE_KEY")

    PLAY_GAMES = os.getenv("PLAY_GAMES", "True")
    POINTS = json.loads(os.getenv("POINTS", "[200, 300]"))

    USE_RANDOM_DELAY_IN_RUN = os.getenv("USE_RANDOM_DELAY_IN_RUN", "True")
    RANDOM_DELAY_IN_RUN = json.loads(os.getenv("RANDOM_DELAY_IN_RUN", "[3, 15]"))

    USE_REF = os.getenv("USE_REF", "False")
    REF_ID = os.getenv("REF_ID")

    USE_PROXY_FROM_FILE = os.getenv("USE_PROXY_FROM_FILE", "False")


settings = Settings()
