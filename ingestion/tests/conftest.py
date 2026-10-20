from dataclasses import dataclass, field

import pytest


@dataclass
class LoadCall:
    rows: list
    destination: str
    job_config: object
    timeout: float | None = None


@dataclass
class FakeJob:
    call: LoadCall

    def result(self, timeout=None):
        self.call.timeout = timeout


@dataclass
class FakeClient:
    loads: list = field(default_factory=list)
    deleted: list = field(default_factory=list)
    created: list = field(default_factory=list)
    exists_ok: bool | None = None

    def create_table(self, table, exists_ok=False):
        self.created.append(table)
        self.exists_ok = exists_ok
        return table

    def load_table_from_json(self, rows, destination, job_config=None):
        call = LoadCall(list(rows), destination, job_config)
        self.loads.append(call)
        return FakeJob(call)

    def delete_table(self, table, not_found_ok=False):
        self.deleted.append((table, not_found_ok))


@pytest.fixture
def fake():
    return FakeClient()
