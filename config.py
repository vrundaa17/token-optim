from pydantic_settings import BaseSettings,SettingsConfigDict
import os
ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
class Setting(BaseSettings):
    groq_api_key:str
    db_path:str
    embedder:str
    
    model_config = SettingsConfigDict(
        env_file=ENV_PATH,
        extra= "ignore"
    )

settings = Setting()

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))