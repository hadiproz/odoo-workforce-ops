import json
from urllib.parse import urlencode

from odoo.tests import tagged
from odoo.tests.common import HttpCase

REPORT_URL = '/report/pdf/workforce_ops.report_placement_assignment_letter/%s'


@tagged('standard', 'post_install', '-at_install')
class TestWorkforceHttp(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.fixture_partner = cls.env['res.partner'].create({
            'name': 'PT HTTP Client',
            'is_company': True,
        })
        cls.worker = cls.env['workforce.worker'].create({'name': 'HTTP Worker'})
        cls.order = cls.env['workforce.job.order'].create({
            'client_id': cls.fixture_partner.id,
            'position_title': 'HTTP Operator',
            'headcount_required': 3,
        })
        cls.report_placement = cls.env['workforce.placement'].create({
            'job_order_id': cls.order.id,
            'worker_id': cls.worker.id,
            'start_date': '2026-12-01',
        })
        cls.user = cls._make_user('wf_http_user', ['workforce_ops.group_workforce_user'])
        cls.manager = cls._make_user('wf_http_manager', ['workforce_ops.group_workforce_manager'])
        cls.outsider = cls._make_user('wf_http_outsider', ['base.group_user'])

    @classmethod
    def _make_user(cls, login, group_xmlids):
        groups = [cls.env.ref(xmlid) for xmlid in group_xmlids]
        partner = cls.env['res.partner'].create({'name': login})
        return cls.env['res.users'].create({
            'name': login,
            'login': login,
            'password': 'http-pass-123',
            'partner_id': partner.id,
            'group_ids': [(6, 0, [group.id for group in groups])],
        })

    def _login(self, login):
        # The helper patches credential checking for speed; the real JSON-RPC
        # session envelope is covered by test_real_session_authenticate_envelope.
        self.authenticate(login, 'http-pass-123')

    def test_real_session_authenticate_envelope(self):
        payload = {
            'jsonrpc': '2.0',
            'method': 'call',
            'params': {
                'db': self.env.cr.dbname,
                'login': 'wf_http_user',
                'password': 'http-pass-123',
            },
            'id': 1,
        }
        response = self.url_open('/web/session/authenticate', json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertNotIn('error', data)
        self.assertEqual(data['result']['uid'], self.user.id)

    def test_get_job_orders(self):
        self._login('wf_http_user')
        response = self.url_open('/api/workforce/job_orders')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIsInstance(payload, list)
        ids = [item['id'] for item in payload]
        self.assertEqual(ids, sorted(ids))
        row = next(item for item in payload if item['id'] == self.order.id)
        self.assertEqual(set(row), {'id', 'client_name', 'position', 'required', 'filled', 'state'})
        self.assertEqual(row['client_name'], 'PT HTTP Client')
        self.assertEqual(row['position'], 'HTTP Operator')
        self.assertEqual(row['required'], 3)
        self.assertEqual(row['filled'], 0)
        self.assertEqual(row['state'], 'draft')

    def test_unauthenticated_request_redirects_without_json(self):
        response = self.url_open('/api/workforce/job_orders', allow_redirects=False)
        self.assertIn(response.status_code, (302, 303))
        self.assertNotIn('application/json', response.headers.get('Content-Type', ''))

    def test_user_without_role_is_forbidden(self):
        self._login('wf_http_outsider')
        response = self.url_open('/api/workforce/job_orders')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['error']['code'], 'forbidden')

    def test_get_excludes_cancelled_orders_for_users_and_managers(self):
        cancelled = self.env['workforce.job.order'].create({
            'client_id': self.fixture_partner.id,
            'position_title': 'Cancelled Order',
            'headcount_required': 1,
        })
        cancelled.action_cancel()
        for login in ('wf_http_manager', 'wf_http_user'):
            self._login(login)
            payload = self.url_open('/api/workforce/job_orders').json()
            self.assertNotIn(cancelled.id, [item['id'] for item in payload])
            self.logout()

    def test_post_creates_draft_and_keeps_computations(self):
        self._login('wf_http_user')
        body = {
            'job_order_id': self.order.id,
            'worker_id': self.worker.id,
            'start_date': '2026-12-01',
        }
        first = self.url_open('/api/workforce/placements', json=body)
        self.assertEqual(first.status_code, 201)
        first_id = first.json()['id']
        second = self.url_open('/api/workforce/placements', json=body)
        self.assertEqual(second.status_code, 201)
        self.assertNotEqual(first_id, second.json()['id'])

        placement = self.env['workforce.placement'].browse(first_id)
        self.assertTrue(placement.exists())
        self.assertEqual(placement.state, 'draft')
        self.assertEqual(self.order.headcount_filled, 0)
        self.assertEqual(self.worker.status, 'available')

    def test_post_validation_errors(self):
        self._login('wf_http_user')
        url = '/api/workforce/placements'
        valid = {
            'job_order_id': self.order.id,
            'worker_id': self.worker.id,
            'start_date': '2026-12-01',
        }

        wrong_media = self.url_open(
            url, data='{}', method='POST', headers={'Content-Type': 'text/plain'},
        )
        self.assertEqual(wrong_media.status_code, 415)

        malformed = self.url_open(
            url, data='{not json', method='POST',
            headers={'Content-Type': 'application/json'},
        )
        self.assertEqual(malformed.status_code, 400)
        self.assertEqual(malformed.json()['error']['code'], 'invalid_request')

        missing_key = dict(valid)
        missing_key.pop('start_date')
        missing = self.url_open(url, json=missing_key)
        self.assertEqual(missing.status_code, 400)

        unknown_key = dict(valid, state='placed')
        unknown = self.url_open(url, json=unknown_key)
        self.assertEqual(unknown.status_code, 400)

        boolean_id = dict(valid, worker_id=True)
        boolean = self.url_open(url, json=boolean_id)
        self.assertEqual(boolean.status_code, 400)

        bad_date = dict(valid, start_date='2026-02-30')
        invalid_date = self.url_open(url, json=bad_date)
        self.assertEqual(invalid_date.status_code, 400)
        self.assertEqual(invalid_date.json()['error']['code'], 'invalid_request')

        missing_ref = dict(valid, job_order_id=99999999)
        not_found = self.url_open(url, json=missing_ref)
        self.assertEqual(not_found.status_code, 404)
        self.assertEqual(not_found.json()['error']['code'], 'reference_not_found')

    def test_post_without_role_is_forbidden(self):
        self._login('wf_http_outsider')
        response = self.url_open(
            '/api/workforce/placements',
            json={
                'job_order_id': self.order.id,
                'worker_id': self.worker.id,
                'start_date': '2026-12-01',
            },
        )
        self.assertEqual(response.status_code, 403)

    def _report_url(self):
        query = urlencode({'context': json.dumps({'force_report_rendering': True})})
        return f'{REPORT_URL % self.report_placement.id}?{query}'

    def test_assignment_letter_pdf(self):
        self._login('wf_http_user')
        response = self.url_open(self._report_url(), timeout=120)
        self.assertEqual(response.status_code, 200)
        self.assertIn('application/pdf', response.headers.get('Content-Type', ''))
        self.assertTrue(response.content.startswith(b'%PDF-'))

    def test_assignment_letter_denied_without_role_or_hidden_record(self):
        self._login('wf_http_outsider')
        response = self.url_open(self._report_url(), timeout=120)
        self.assertFalse(
            response.status_code == 200 and response.content.startswith(b'%PDF-')
        )

        self.order.action_cancel()
        self.logout()
        self._login('wf_http_user')
        response = self.url_open(self._report_url(), timeout=120)
        self.assertFalse(
            response.status_code == 200 and response.content.startswith(b'%PDF-')
        )
