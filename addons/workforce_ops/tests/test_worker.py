from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import WorkforceCase


@tagged('standard', 'post_install', '-at_install')
class TestWorker(WorkforceCase):

    def test_new_worker_is_available(self):
        worker = self.make_worker()
        self.assertEqual(worker.status, 'available')

    def test_draft_placement_does_not_place_worker(self):
        worker = self.make_worker()
        self.make_placement(worker=worker)
        self.assertEqual(worker.status, 'available')

    def test_archive_and_unarchive(self):
        worker = self.make_worker()
        worker.action_archive()
        self.assertEqual(worker.status, 'inactive')
        worker.action_unarchive()
        self.assertEqual(worker.status, 'available')

    def test_archived_worker_with_placed_record_stays_placed(self):
        worker = self.make_worker()
        placement = self.make_placement(worker=worker)
        placement.action_place()
        worker.action_archive()
        self.assertEqual(worker.status, 'placed')
        placement.action_finish()
        self.assertEqual(worker.status, 'inactive')
        worker.action_unarchive()
        self.assertEqual(worker.status, 'available')

    def test_status_cannot_be_written(self):
        worker = self.make_worker()
        with self.assertRaises(UserError):
            worker.write({'status': 'placed'})
