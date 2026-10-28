"""Boundary tests prove isolation, exact-money invariants and retry behavior."""
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from app import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB_PATH', str(tmp_path / 'test.sqlite'))
    main.initialize()
    with TestClient(main.app) as client:
        yield client


def account(client, name='alice'):
    response = client.post('/api/v2/auth/register', json={'username': name, 'password': 'test-passphrase-123'})
    assert response.status_code == 201, response.text
    return {'Authorization': 'Bearer ' + response.json()['token']}


def order(client, auth, key='one', **overrides):
    return client.post('/api/v2/orders', headers={**auth, 'Idempotency-Key': key},
                       json={'symbol': 'RELIANCE', 'side': 'BUY', 'quantity': 1, **overrides})


def snapshot(client, auth):
    return client.get('/api/v2/snapshot', headers=auth).json()


def test_isolation_retry_and_cents(client):
    alice, bob = account(client), account(client, 'bob')
    first = order(client, alice)
    assert first.status_code == 201
    replay = order(client, alice)
    assert replay.status_code == 200
    assert first.json() == replay.json()
    state = snapshot(client, alice)
    assert state['cash'] == 998715.50
    assert state['positions'][0]['quantity'] == 1
    assert len(state['orders']) == 1
    assert snapshot(client, bob)['cash'] == 1000000
    assert snapshot(client, bob)['orders'] == []
    assert order(client, alice, quantity=2).status_code == 409
    assert snapshot(client, alice) == state


def test_failed_orders_do_not_mutate(client):
    auth = account(client)
    before = snapshot(client, auth)
    for payload, code in [({'quantity': 0}, 422), ({'quantity': True}, 422),
                          ({'quantity': 1.5}, 422), ({'quantity': 1000000}, 409),
                          ({'side': 'SELL'}, 409), ({'symbol': 'UNKNOWN'}, 404),
                          ({'side': 'HACK'}, 422), ({'price': 0}, 422)]:
        assert order(client, auth, **payload).status_code == code
    assert snapshot(client, auth) == before


def test_buy_sell_round_trip_and_average(client):
    auth = account(client)
    assert order(client, auth).status_code == 201
    assert order(client, auth, key='two', quantity=2).status_code == 201
    state = snapshot(client, auth)
    assert state['positions'] == [{'symbol': 'RELIANCE', 'quantity': 3, 'averageCost': 1284.50}]
    assert order(client, auth, key='sell', quantity=3, side='SELL').status_code == 201
    state = snapshot(client, auth)
    assert state['cash'] == 1000000
    assert state['positions'] == []


def test_parallel_retry_executes_once(client):
    auth = account(client)
    with ThreadPoolExecutor(max_workers=6) as pool:
        statuses = list(pool.map(lambda _: order(client, auth).status_code, range(6)))
    assert statuses.count(201) == 1
    assert statuses.count(200) == 5
    assert len(snapshot(client, auth)['orders']) == 1


def test_sessions_logout_expiry_and_deletion(client):
    auth = account(client)
    assert client.get('/api/v2/snapshot').status_code == 401
    assert client.post('/api/v2/auth/login', json={'username': 'alice', 'password': 'incorrect-long-password'}).status_code == 401
    logged_in = client.post('/api/v2/auth/login', json={'username': 'alice', 'password': 'test-passphrase-123'})
    assert logged_in.status_code == 200
    other = {'Authorization': 'Bearer ' + logged_in.json()['token']}
    assert client.post('/api/v2/auth/logout', headers=auth).status_code == 204
    assert client.get('/api/v2/snapshot', headers=auth).status_code == 401
    assert order(client, other).status_code == 201
    assert client.put('/api/v2/watchlist/TCS', headers=other).status_code == 204
    assert client.delete('/api/v2/account', headers=other).status_code == 204
    assert client.get('/api/v2/snapshot', headers=other).status_code == 401
    with main.transaction() as db:
        assert db.execute('SELECT count(*) FROM users').fetchone()[0] == 0
        for table in ['sessions', 'positions', 'orders', 'watchlist']:
            assert db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] == 0


def test_watchlist_is_private_and_idempotent(client):
    a, b = account(client), account(client, 'bob')
    for _ in range(2):
        assert client.put('/api/v2/watchlist/TCS', headers=a).status_code == 204
    assert snapshot(client, a)['watchlist'] == ['TCS']
    assert snapshot(client, b)['watchlist'] == []
    assert client.delete('/api/v2/watchlist/TCS', headers=a).status_code == 204
    assert snapshot(client, a)['watchlist'] == []


def test_rate_limit_and_private_headers(client):
    for _ in range(15):
        assert client.post('/api/v2/auth/login', json={'username': 'missing', 'password': 'incorrect-long-password'}).status_code == 401
    assert client.post('/api/v2/auth/login', json={'username': 'missing', 'password': 'incorrect-long-password'}).status_code == 429
    response = client.get('/health')
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'


def test_expired_session_is_rejected(client):
    auth = account(client)
    with main.transaction() as db:
        db.execute('UPDATE sessions SET expires=0')
    assert client.get('/api/v2/snapshot', headers=auth).status_code == 401


def test_validation_does_not_echo_password(client):
    secret = 'sensitive'
    response = client.post('/api/v2/auth/register', json={'username': 'alice', 'password': secret})
    assert response.status_code == 422
    assert secret not in response.text


def test_database_stores_hashes_not_credentials(client):
    auth = account(client)
    with main.transaction() as db:
        row = db.execute('SELECT password,salt FROM users').fetchone()
        assert row['password'] != 'test-passphrase-123'
        assert len(row['salt']) == 32
        token = auth['Authorization'].removeprefix('Bearer ')
        digest = db.execute('SELECT digest FROM sessions').fetchone()[0]
        assert token != digest


def test_concurrent_distinct_orders_cannot_overspend(client):
    auth = account(client)
    with ThreadPoolExecutor(max_workers=3) as pool:
        statuses = list(pool.map(lambda i: order(client, auth, key=f'buy-{i}', quantity=500).status_code, range(3)))
    assert statuses.count(201) == 1
    assert statuses.count(409) == 2
    state = snapshot(client, auth)
    assert state['cash'] == 357750
    assert state['positions'][0]['quantity'] == 500
