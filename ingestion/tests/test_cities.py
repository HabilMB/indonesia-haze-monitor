from haze_ingest.cities import City, load_cities


def test_load_cities_reads_shared_seed():
    cities = load_cities()
    assert len(cities) == 8
    assert City("Jakarta", "DKI Jakarta", -6.21, 106.85) in cities
    assert len({c.name for c in cities}) == 8
