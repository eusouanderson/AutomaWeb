from app.schemas.common import Message


def test_message_schema() -> None:
    msg = Message(message="Test message")
    assert msg.message == "Test message"


def test_message_schema_dict() -> None:
    msg = Message(message="Hello")
    assert msg.model_dump() == {"message": "Hello"}
