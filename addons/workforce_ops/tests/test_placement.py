from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from .common import WorkforceCase


@tagged('standard', 'post_install', '-at_install')
class TestPlacement(WorkforceCase):

    def test_filled_count_when_placed(self):
        order = self.make_order(headcount_required=2)
        placement = self.make_placement(order=order)
        self.assertEqual(order.headcount_filled, 0)
        placement.action_place()
        self.assertEqual(placement.state, 'placed')
        self.assertEqual(order.headcount_filled, 1)
        self.assertAlmostEqual(order.progress, 50.0)
        self.assertEqual(placement.worker_id.status, 'placed')
        placement.action_finish()
        self.assertEqual(placement.state, 'finished')
        self.assertEqual(order.headcount_filled, 0)
        self.assertEqual(placement.worker_id.status, 'available')

    def test_worker_has_at_most_one_active_placement(self):
        worker = self.make_worker()
        first = self.make_placement(order=self.fixture_order, worker=worker)
        first.action_place()
        self.assertEqual(first.state, 'placed')

        second_order = self.make_order(position_title='Second Order')
        second = self.make_placement(order=second_order, worker=worker)
        with self.assertRaises(ValidationError):
            with self.env.cr.savepoint():
                second.action_place()
        second.invalidate_recordset()
        self.assertEqual(second.state, 'draft')
        self.assertEqual(self.fixture_order.headcount_filled, 1)
        self.assertEqual(second_order.headcount_filled, 0)

    def test_multiple_drafts_are_allowed(self):
        worker = self.make_worker()
        self.make_placement(order=self.fixture_order, worker=worker)
        self.make_placement(order=self.make_order(position_title='Other'), worker=worker)
        self.assertEqual(
            self.env['workforce.placement'].search_count(
                [('worker_id', '=', worker.id), ('state', '=', 'draft')]
            ),
            2,
        )

    def test_finish_releases_worker_for_replacement(self):
        worker = self.make_worker()
        first = self.make_placement(order=self.fixture_order, worker=worker)
        first.action_place()
        first.action_finish()
        second_order = self.make_order(position_title='Replacement Order')
        second = self.make_placement(order=second_order, worker=worker)
        second.action_place()
        self.assertEqual(second.state, 'placed')
        self.assertEqual(second_order.headcount_filled, 1)

    def test_end_date_before_start_date_is_rejected(self):
        with self.assertRaises(ValidationError):
            with self.env.cr.savepoint():
                self.make_placement(start_date='2026-12-10', end_date='2026-12-01')

    def test_new_placement_must_start_in_draft(self):
        with self.assertRaises(UserError):
            self.make_placement(state='placed')

    def test_placement_state_jumps_are_rejected(self):
        placement = self.make_placement()
        with self.assertRaises(UserError):
            placement.write({'state': 'finished'})

    def test_reassigning_order_recomputes_both_orders(self):
        first_order = self.make_order(position_title='First')
        second_order = self.make_order(position_title='Second')
        placement = self.make_placement(order=first_order)
        placement.action_place()
        self.assertEqual(first_order.headcount_filled, 1)
        self.assertEqual(second_order.headcount_filled, 0)
        placement.write({'job_order_id': second_order.id})
        self.assertEqual(first_order.headcount_filled, 0)
        self.assertEqual(second_order.headcount_filled, 1)

    def test_partial_unique_index_exists(self):
        self.env.cr.execute(
            "SELECT indexdef FROM pg_indexes "
            "WHERE tablename = 'workforce_placement' "
            "AND indexname = 'workforce_placement_worker_active_unique'"
        )
        row = self.env.cr.fetchone()
        self.assertTrue(row, 'partial unique index is missing')
        definition = row[0]
        self.assertIn('UNIQUE', definition)
        self.assertIn('worker_id', definition)
        self.assertIn('state', definition)
        self.assertIn('placed', definition)

    def test_hidden_placed_record_blocks_duplicate(self):
        user = self.make_user('wf_hidden_user', ['workforce_ops.group_workforce_user'])
        worker = self.make_worker()
        visible_order = self.make_order(position_title='Visible Order')
        visible_order.action_confirm()
        visible_order.action_start()
        hidden_placement = self.make_placement(order=visible_order, worker=worker)
        hidden_placement.action_place()
        self.assertEqual(worker.status, 'placed')

        visible_order.action_cancel()
        with self.assertRaises(AccessError):
            hidden_placement.with_user(user).read(['id'])

        second_order = self.make_order(position_title='New Order')
        second = self.make_placement(order=second_order, worker=worker)
        with self.assertRaises(ValidationError):
            with self.env.cr.savepoint():
                second.action_place()
        self.assertEqual(worker.status, 'placed')
