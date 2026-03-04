from app.db.base import Base


def test_base_class() -> None:
    assert Base is not None
    assert hasattr(Base, "metadata")
