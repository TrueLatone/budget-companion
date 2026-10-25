import re
from datetime import date

from app.modules.expenses import services


USER = services.DEMO_USER_ID


def _payload(**overrides):
    values = {
        "title": "Khoản chi bất ngờ",
        "amount": "50000",
        "expense_date": "2026-10-20",
        "category": "Khác",
        "note": "",
    }
    values.update(overrides)
    return values


def test_same_idempotency_key_does_not_create_duplicate(app):
    first = services.create_unexpected_record(
        USER, _payload(idempotency_key="form-token-1")
    )
    second = services.create_unexpected_record(
        USER,
        _payload(
            idempotency_key="form-token-1",
            title="Payload gửi lại",
            amount="999999",
            expense_date="2026-10-25",
        ),
    )

    assert second.record_id == first.record_id
    records = services.list_records(
        USER, date(2026, 10, 1), date(2026, 10, 31)
    )
    assert len(records) == 1
    assert records[0].amount == 50000


def test_same_amount_and_date_with_different_keys_are_both_kept(app):
    first = services.create_unexpected_record(
        USER, _payload(idempotency_key="form-token-a")
    )
    second = services.create_unexpected_record(
        USER, _payload(idempotency_key="form-token-b")
    )

    assert first.record_id != second.record_id
    records = services.list_records(
        USER, date(2026, 10, 1), date(2026, 10, 31)
    )
    assert len(records) == 2


def test_unexpected_form_has_token_and_replay_does_not_duplicate(client):
    page = client.get("/expenses?view=day&date=2026-10-05")
    body = page.data.decode("utf-8")
    match = re.search(
        r'name="idempotency_key" value="([0-9a-f]+)"', body
    )
    assert match is not None

    data = _payload(
        idempotency_key=match.group(1),
        view="day",
        date="2026-10-05",
    )
    client.post("/expenses/records", data=data, follow_redirects=True)
    replay = client.post(
        "/expenses/records", data=data, follow_redirects=True
    )

    assert "không tạo bản ghi trùng" in replay.data.decode("utf-8")
    records = services.list_records(
        USER, date(2026, 10, 1), date(2026, 10, 31)
    )
    assert len(records) == 1
