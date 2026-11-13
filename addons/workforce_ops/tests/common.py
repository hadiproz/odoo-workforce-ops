from odoo.tests.common import TransactionCase


class WorkforceCase(TransactionCase):
    """Shared fixtures for the addon test suite."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.fixture_partner = cls.env['res.partner'].create({
            'name': 'PT Fixture Client',
            'is_company': True,
        })
        cls.fixture_worker = cls.env['workforce.worker'].create({
            'name': 'Fixture Worker',
            'job_position': 'Operator',
        })
        cls.fixture_order = cls.env['workforce.job.order'].create({
            'client_id': cls.fixture_partner.id,
            'position_title': 'Fixture Operator',
            'headcount_required': 2,
        })

    @classmethod
    def make_user(cls, login, group_xmlids, password='test-pass-123'):
        groups = [cls.env.ref(xmlid) for xmlid in group_xmlids]
        partner = cls.env['res.partner'].create({'name': login})
        return cls.env['res.users'].create({
            'name': login,
            'login': login,
            'password': password,
            'partner_id': partner.id,
            'group_ids': [(6, 0, [group.id for group in groups])],
        })

    def make_order(self, **vals):
        data = {
            'client_id': self.fixture_partner.id,
            'position_title': 'Test Operator',
            'headcount_required': 2,
        }
        data.update(vals)
        return self.env['workforce.job.order'].create(data)

    def make_worker(self, name='Test Worker', **vals):
        data = {'name': name}
        data.update(vals)
        return self.env['workforce.worker'].create(data)

    def make_placement(self, order=None, worker=None, **vals):
        data = {
            'job_order_id': (order or self.fixture_order).id,
            'worker_id': (worker or self.fixture_worker).id,
            'start_date': '2026-12-01',
        }
        data.update(vals)
        return self.env['workforce.placement'].create(data)
