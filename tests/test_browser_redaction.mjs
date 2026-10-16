import test from 'node:test';
import assert from 'node:assert/strict';
import { redactSnapshot } from '../scripts/redact_snapshot.mjs';

test('credential page hides hex keys and both mixed-case client secrets', () => {
  const values = [
    '0123456789abcdef0123456789abcdef',
    'FakeLoginSecretAaBbCc0123456789Zz',
    'FakeBusinessSecretXyZ0123456789Qq',
  ];
  const snapshot = `heading REST API 키\n${values[0]}\n카카오 로그인 코드 ${values[1]}\n비즈니스 인증 코드 ${values[2]}`;
  const safe = redactSnapshot(snapshot);
  for (const value of values) assert.ok(!safe.includes(value));
  assert.match(safe, /credential page/);
});

test('whole-page suppression protects short and DOM-split credentials', () => {
  for (const label of ['클라이언트 시크릿', 'Client secret', 'client_secret', 'access_token', 'refresh-token', '인가 코드']) {
    assert.equal(redactSnapshot(`${label}\ngeneric: short\ngeneric: split\ngeneric: value`),
      '[REDACTED: credential page; report only verified non-secret status]');
  }
});

test('fallback masks mixed alphabets, base64, URL-safe tokens and JWTs', () => {
  const tokens = [
    '0123456789abcdef0123456789abcdef',
    'FakeMixedCaseTokenXyZ0123456789Ab',
    'Fake_url-safe_token-0123456789_ab',
    'Fake/base64+value0123456789ABCD==',
    'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJmYWtlLXRlc3QifQ.fakeSignature012345678901234',
  ];
  for (const token of tokens) assert.equal(redactSnapshot(`value: ${token}`), 'value: [REDACTED]');
});

test('known short secrets are removed literally, including regex punctuation', () => {
  assert.equal(redactSnapshot('values a.b+$ and abcdef and abc', { knownSecrets: ['abc', 'abcdef', 'a.b+$', ''] }),
    'values [REDACTED] and [REDACTED] and [REDACTED]');
});

test('non-secret status remains readable and masking is idempotent', () => {
  const status = '앱 1592683\n카카오 계정 연결됨\n기본 알림 연결됨';
  assert.equal(redactSnapshot(status), status);
  const safe = redactSnapshot('value: FakeMixedCaseTokenXyZ0123456789Ab');
  assert.equal(redactSnapshot(safe), safe);
});

test('invalid inputs fail instead of coercing an object into output', () => {
  assert.throws(() => redactSnapshot({ secret: 'fake' }), TypeError);
  assert.throws(() => redactSnapshot('test', { knownSecrets: ['fake', 123] }), TypeError);
});
