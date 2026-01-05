import configparser
from pathlib import Path

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / 'config.ini'


def load_config(path: str | None = None) -> configparser.ConfigParser:
    """Load the application configuration from disk."""
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    config = configparser.ConfigParser()
    read_files = config.read(config_path)
    if not read_files:
        raise FileNotFoundError(f"Configuration file not found at {config_path}")
    return config


def get_db_params(config: configparser.ConfigParser) -> dict:
    """Extract psycopg connection parameters from the configuration."""
    db_config = config['Database']
    params = {
        'host': db_config['host'],
        'database': db_config['database'],
        'user': db_config['user'],
        'password': db_config['password'],
    }
    if db_config.get('port'):
        params['port'] = db_config.get('port')
    return params


def get_sqlalchemy_url(db_config: configparser.SectionProxy) -> str:
    """Build a SQLAlchemy compatible connection string from the DB section."""
    port = db_config.get('port', '5432')
    return (
        f"postgresql+psycopg2://{db_config['user']}:{db_config['password']}@"
        f"{db_config['host']}:{port}/{db_config['database']}"
    )


def get_paths(config: configparser.ConfigParser) -> configparser.SectionProxy:
    """Return the Paths section for convenience."""
    return config['Paths']
