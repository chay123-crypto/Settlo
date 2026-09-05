"""
Central configuration. Loaded once from .env via pydantic-settings.

Money note: every *_paise field elsewhere in this codebase is an integer.
Never use float for money -- floats cannot represent paise amounts exactly
and will eventually produce off-by-one-paise reconciliation errors.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_base_url: str = "https://api.razorpay.com/v1"

    llm_api_key: str = ""
    llm_provider: str = "groq"          # "groq" or "anthropic"
    llm_model: str = "llama-3.3-70b-versatile"  # default to Groq model


    api_timeout_seconds: int = 20
    max_api_attempts: int = 3
    amount_tolerance_paise: int = 0
    probable_match_threshold_days: int = 3
    settlement_sla_days: int = 5

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def razorpay_mock_mode(self) -> bool:
        """True whenever real Razorpay Test Mode credentials aren't set.

        This lets the whole app run and be demoed before you have a
        Razorpay account -- swap in real RAZORPAY_KEY_ID/SECRET in .env
        and this flips to False automatically, no code changes needed.
        """
        return not (self.razorpay_key_id and self.razorpay_key_secret)

    @property
    def llm_mock_mode(self) -> bool:
        """True whenever no LLM API key is configured. The agent falls
        back to a rule-based canned-explanation mode in this case."""
        return not self.llm_api_key


settings = Settings()
