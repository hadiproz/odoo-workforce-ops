from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import WorkforceCase


@tagged('standard', 'post_install', '-at_install')
class TestWorkforceSecurity(WorkforceCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wf_user = cls.make_user('wf_user', ['workforce_ops.group_workforce_user'])
        cls.wf_manager = cls.make_user('wf_manager', ['workforce_ops.group_workforce_manager'])
        cls.outsider = cls.make_user('wf_outsider', ['base.group_user'])
        cls.portal = cls.make_user('wf_portal', ['base.group_portal'])

    def test_user_can_create_and_write_job_order(self):
        order = self.env['workforce.job.order'].with_user(self.wf_user).create({
            'client_id': self.fixture_partner.id,
            'position_title': 'User Created Order',
            'headcount_required': 1,
        })
        self.assertEqual(order.state, 'draft')
        order.write({'position_title': 'User Updated Order'})
        self.assertEqual(order.position_title, 'User Updated Order')

    def test_user_cannot_unlink_records(self):
        order = self.make_order()
        worker = self.make_worker()
        placement = self.make_placement()
        with self.assertRaises(AccessError):
            order.with_user(self.wf_user).unlink()
        with self.assertRaises(AccessError):
            worker.with_user(self.wf_user).unlink()
        with self.assertRaises(AccessError):
            placement.with_user(self.wf_user).unlink()

    def test_manager_has_full_crud(self):
        order = self.make_order()
        order.with_user(self.wf_manager).write({'position_title': 'Manager Edit'})
        self.assertEqual(order.position_title, 'Manager Edit')
        worker = self.make_worker()
        placement = self.make_placement()
        worker.with_user(self.wf_manager).unlink()
        self.assertFalse(worker.exists())
        placement.with_user(self.wf_manager).unlink()
        self.assertFalse(placement.exists())

    def test_internal_user_without_role_is_denied(self):
        with self.assertRaises(AccessError):
            self.env['workforce.job.order'].with_user(self.outsider).search([])
        with self.assertRaises(AccessError):
            self.env['workforce.worker'].with_user(self.outsider).search([])

    def test_public_user_is_denied(self):
        public_user = self.env.ref('base.public_user')
        with self.assertRaises(AccessError):
            self.env['workforce.job.order'].with_user(public_user).search([])

    def test_portal_user_is_denied(self):
        with self.assertRaises(AccessError):
            self.env['workforce.job.order'].with_user(self.portal).search([])

    def test_cancelled_order_hidden_from_user_but_visible_to_manager(self):
        order = self.make_order()
        order.action_cancel()
        self.assertFalse(
            self.env['workforce.job.order'].with_user(self.wf_user).search([('id', '=', order.id)])
        )
        with self.assertRaises(AccessError):
            order.with_user(self.wf_user).read(['position_title'])
        self.assertTrue(
            self.env['workforce.job.order'].with_user(self.wf_manager).search([('id', '=', order.id)])
        )

    def test_placement_hidden_when_parent_order_is_cancelled(self):
        order = self.make_order()
        order.action_confirm()
        order.action_start()
        placement = self.make_placement(order=order)
        placement.action_place()
        order.action_cancel()
        self.assertFalse(
            self.env['workforce.placement'].with_user(self.wf_user).search([('id', '=', placement.id)])
        )
        with self.assertRaises(AccessError):
            placement.with_user(self.wf_user).read(['id'])
        self.assertTrue(
            self.env['workforce.placement'].with_user(self.wf_manager).search([('id', '=', placement.id)])
        )

    def test_cancel_navigates_back_to_list(self):
        order = self.make_order()
        action = order.with_user(self.wf_user).action_cancel()
        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'workforce.job.order')
        self.assertFalse(
            self.env['workforce.job.order'].with_user(self.wf_user).search([('id', '=', order.id)])
        )

    def test_user_can_read_active_orders(self):
        order = self.make_order()
        found = self.env['workforce.job.order'].with_user(self.wf_user).search([('id', '=', order.id)])
        self.assertEqual(found, order)
