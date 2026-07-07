from pydantic_settings import BaseSettings

class Env(BaseSettings):
    IP_ADDR: str
    
    class Config:
        env_file = ".env"

env = Env()