from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import WorkforceCase


@tagged('standard', 'post_install', '-at_install')
class TestJobOrder(WorkforceCase):

    def test_confirm_draft_job_order(self):
        order = self.make_order()
        self.assertEqual(order.state, 'draft')
        order.action_confirm()
        self.assertEqual(order.state, 'confirmed')
        order.action_start()
        self.assertEqual(order.state, 'in_progress')
        order.action_done()
        self.assertEqual(order.state, 'done')

    def test_state_jumps_are_rejected(self):
        order = self.make_order()
        with self.assertRaises(UserError):
            order.write({'state': 'done'})
        self.assertEqual(order.state, 'draft')
        with self.assertRaises(UserError):
            order.action_start()
        order.action_confirm()
        with self.assertRaises(UserError):
            order.action_confirm()

    def test_cancel_returns_list_action(self):
        order = self.make_order()
        action = order.action_cancel()
        self.assertEqual(order.state, 'cancelled')
        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'workforce.job.order')
        with self.assertRaises(UserError):
            order.action_confirm()

    def test_progress_tracks_required_headcount(self):
        order = self.make_order(headcount_required=2)
        placement = self.make_placement(order=order)
        placement.action_place()
        self.assertEqual(order.headcount_filled, 1)
        self.assertAlmostEqual(order.progress, 50.0)
        order.headcount_required = 4
        self.assertAlmostEqual(order.progress, 25.0)

    def test_headcount_required_must_be_positive(self):
        with self.assertRaises(ValidationError):
            self.make_order(headcount_required=0)

    def test_new_order_must_start_in_draft(self):
        with self.assertRaises(UserError):
            self.make_order(state='confirmed')

    def test_derived_values_cannot_be_written(self):
        order = self.make_order()
        with self.assertRaises(UserError):
            order.write({'headcount_filled': 2})
        with self.assertRaises(UserError):
            order.write({'progress': 100.0})
