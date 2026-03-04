from unittest.mock import patch

from app.core.logging import setup_logging


def test_setup_logging() -> None:
    with patch("logging.basicConfig") as mock_config:
        setup_logging()
        mock_config.assert_called_once()
