from app.domain.email import Email


def test_email_maps_from_and_to_fields():
    email = Email.model_validate(
        {
            "id": "abc",
            "from": "cliente@exemplo.pt",
            "to": "encomendas@ferrapex.pt",
            "received_at": "2026-09-01T10:00:00Z",
            "subject": "Encomenda",
            "body": "...",
            "attachments": [],
        }
    )

    assert email.sender == "cliente@exemplo.pt"
    assert email.recipient == "encomendas@ferrapex.pt"
    assert email.model_dump(by_alias=True)["from"] == "cliente@exemplo.pt"


def test_catalog_csv_is_parsed():
    """Formato real da API: cabeçalhos em português."""
    from decimal import Decimal
    from pathlib import Path

    from app.api.ferrapex_client import parse_catalog_csv

    products = parse_catalog_csv((Path(__file__).parents[1] / "fixtures" / "catalog.csv").read_text())

    assert len(products) == 42
    dob = next(p for p in products if p.reference == "DOB-080-ZNC")
    assert dob.description == "Dobradica 80x60 zincada"
    assert dob.family == "Ferragens porta"
    assert dob.unit == "par"
    assert dob.price_eur == Decimal("2.95")
