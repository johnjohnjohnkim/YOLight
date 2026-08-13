# Centralized runtime configuration. Loads required settings from a local
# `.env` file (via pydantic-settings) so secrets/host-specific values stay
# out of source control. Currently unused elsewhere in the project, but
# import `env` from here to access validated config values.

from pydantic_settings import BaseSettings

class Env(BaseSettings):
    # IP address of the machine running this app, read from IP_ADDR in .env.
    IP_ADDR: str
    GOVEE_API: str

    class Config:
        env_file = ".env"

env = Env()