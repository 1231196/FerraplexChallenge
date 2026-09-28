import httpx

from app.persistence.repositories import EmailRepository, OrderRepository
from app.services.import_orders import OrderImportService
from tests.conftest import FakeExtractor, FakeFerrapexClient, make_email


def all_orders(session_factory):
    with session_factory() as s:
        return OrderRepository(s).get_all()


async def test_processing_same_email_twice_creates_only_one_order(session_factory, catalog):
    client = FakeFerrapexClient([make_email(id="e1"), make_email(id="e1")], catalog)
    service = OrderImportService(client=client, session_factory=session_factory, llm_extractor=FakeExtractor())

    first = await service.sync()
    second = await service.sync()

    assert len(all_orders(session_factory)) == 1
    assert first.processed == 1 and first.skipped == 1
    assert second.processed == 0 and second.skipped == 2


async def test_failure_in_one_email_does_not_stop_next_email(session_factory, catalog):
    bad = make_email(id="bad", body="texto que o parser não entende")
    good = make_email(id="good")
    extractor = FakeExtractor({"bad": httpx.ReadTimeout("timeout")})
    service = OrderImportService(
        client=FakeFerrapexClient([bad, good], catalog), session_factory=session_factory, llm_extractor=extractor
    )

    result = await service.sync()

    assert result.failed == 1 and result.processed == 1
    assert [o.source_email_id for o in all_orders(session_factory)] == ["good"]
    with session_factory() as s:
        assert EmailRepository(s).get_by_id("bad").processing_status == "failed"


async def test_failed_email_is_retried_on_next_sync(session_factory, catalog):
    email = make_email(id="e1", body="texto que o parser não entende")
    extractor = FakeExtractor({"e1": httpx.ReadTimeout("timeout")})
    service = OrderImportService(
        client=FakeFerrapexClient([email], catalog), session_factory=session_factory, llm_extractor=extractor
    )
    await service.sync()

    from tests.unit.test_order_import_service import llm_order

    extractor.responses["e1"] = llm_order()
    result = await service.sync()

    assert result.processed == 1
    assert len(all_orders(session_factory)) == 1
