from __future__ import annotations

import json

import httpx
import pytest

from src.bilibili_client import BilibiliClient
from src.lottery_actions import repost_dynamic


@pytest.fixture
def mock_client(monkeypatch):
    # Never read real account credentials or contact Bilibili in these tests.
    monkeypatch.setattr('src.bilibili_client._load_cookie_string', lambda: None)
    monkeypatch.setattr('src.bilibili_client.acquire_bilibili_request_slot', lambda: None)
    clients = []

    def create(handler):
        client = BilibiliClient(warmup=False)
        client._client.close()
        client._client = httpx.Client(transport=httpx.MockTransport(handler))
        clients.append(client)
        return client

    yield create
    for client in clients:
        client.close()


def submit(client, content='好运😀！'):
    return repost_dynamic(client, dynamic_id='1252602820816797718', my_uid=123,
                          csrf='csrf-test-secret', referer='https://t.bilibili.com/1252602820816797718',
                          content=content)


@pytest.mark.parametrize('content, expected', [('好运😀！', '好运😀！'), ('', '转发动态'), ('奖' * 240, '奖' * 233)])
def test_repost_uses_new_json_contract(mock_client, content, expected):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={'code': 0, 'data': {'result': 0}})

    result = submit(mock_client(handler), content)
    assert result.ok
    assert len(requests) == 1
    request = requests[0]
    assert request.method == 'POST'
    assert str(request.url).split('?')[0] == 'https://api.bilibili.com/x/dynamic/feed/create/dyn'
    assert dict(request.url.params) == {'csrf': 'csrf-test-secret', 'platform': 'web'}
    assert request.headers['content-type'] == 'application/json'
    assert request.headers['referer'].startswith('https://t.bilibili.com/')
    body = json.loads(request.content)
    assert body['web_repost_src']['dyn_id_str'] == '1252602820816797718'
    assert body['dyn_req']['scene'] == 4
    assert body['dyn_req']['content']['contents'] == [{'raw_text': expected, 'type': 1, 'biz_id': ''}]
    assert 'dynamic_id' not in body and 'csrf' not in body


@pytest.mark.parametrize('payload, ok', [
    ({'code': 0, 'data': {'result': 0}}, True),
    ({'code': 0, 'data': {'dyn_id_str': '1252602820816797719'}}, True),
    ({'code': 0, 'data': {'result': 1, 'dyn_id_str': '1252602820816797719'}}, False),
    ({'code': -101, 'message': '已退出登录'}, False),
    ({'code': 1101008, 'message': '操作太频繁'}, False),
    ({'code': -352, 'message': '风控'}, False),
    ({'message': '重复'}, False),
])
def test_repost_checks_business_result(mock_client, payload, ok):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=payload)

    assert submit(mock_client(handler)).ok is ok
    assert len(requests) == 1


@pytest.mark.parametrize('payload', [{'code': 0}, {'code': 0, 'data': {}}, {'code': 0, 'data': {'dyn_id_str': '0'}}, []])
def test_repost_does_not_claim_ambiguous_success(mock_client, payload):
    with pytest.raises(RuntimeError, match='核对'):
        submit(mock_client(lambda request: httpx.Response(200, json=payload)))


@pytest.mark.parametrize('failure', ['timeout', 'disconnect', 'invalid-json', 404, 429, 500])
def test_repost_never_retries_ambiguous_submission(mock_client, failure):
    requests = []

    def handler(request):
        requests.append(request)
        if failure == 'timeout':
            raise httpx.ReadTimeout('timeout', request=request)
        if failure == 'disconnect':
            raise httpx.RemoteProtocolError('disconnect', request=request)
        if failure == 'invalid-json':
            return httpx.Response(200, text='<html>not JSON</html>')
        return httpx.Response(failure, text='failure')

    with pytest.raises(RuntimeError, match='未自动重试') as caught:
        submit(mock_client(handler))
    assert len(requests) == 1
    assert 'csrf-test-secret' not in str(caught.value)
