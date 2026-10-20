from datetime import date

import pytest
import requests
import responses

from haze_ingest.firms import FirmsError, fetch_hotspots
from haze_ingest.session import make_session

URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv/KEY123/VIIRS_SNPP_NRT/95,-11,141,6/3/2026-10-17"
HEADER = "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight"
ROW_1 = "-2.5,113.9,330.1,0.4,0.4,2026-10-17,518,N,VIIRS,n,2.0NRT,295.0,4.4,D"
ROW_2 = "-2.6,113.8,331.0,0.4,0.4,2026-10-18,5,N,VIIRS,h,2.0NRT,296.0,5.1,N"


def fetch():
    return fetch_hotspots(make_session(), "KEY123", date(2026, 10, 17), 3)


@responses.activate
def test_parses_rows_and_pads_acq_time():
    responses.get(URL, body=f"{HEADER}\n{ROW_1}\n{ROW_2}\n")
    rows = fetch()
    assert [r.acq_time for r in rows] == ["0518", "0005"]
    assert rows[0].acq_date == date(2026, 10, 17)
    assert rows[1].confidence == "h"


@responses.activate
def test_header_only_returns_empty_list():
    responses.get(URL, body=HEADER)
    assert fetch() == []


@responses.activate
def test_http_error_raises_without_key():
    responses.get(URL, status=400, body="Invalid MAP_KEY.")
    with pytest.raises(FirmsError) as exc:
        fetch()
    assert "Invalid MAP_KEY." in str(exc.value)
    assert "KEY123" not in str(exc.value)


@responses.activate
def test_connection_error_hides_url_and_chain():
    responses.get(URL, body=requests.ConnectionError(f"Max retries exceeded with url: {URL}"))
    with pytest.raises(FirmsError) as exc:
        fetch()
    assert "KEY123" not in str(exc.value)
    assert exc.value.__cause__ is None and exc.value.__suppress_context__


@responses.activate
def test_non_csv_body_raises():
    responses.get(URL, body="<html>maintenance</html>")
    with pytest.raises(FirmsError):
        fetch()


@responses.activate
def test_invalid_row_names_line_number():
    responses.get(URL, body=f"{HEADER}\n{ROW_1.replace(',n,', ',x,')}\n")
    with pytest.raises(FirmsError, match="line 2"):
        fetch()


@responses.activate
def test_bad_acq_time_rejected():
    responses.get(URL, body=f"{HEADER}\n{ROW_1.replace(',518,', ',2460,')}\n")
    with pytest.raises(FirmsError):
        fetch()
