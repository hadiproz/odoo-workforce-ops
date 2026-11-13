from odoo.tools import config
from odoo.tests import tagged

from .common import WorkforceCase


@tagged('standard', 'post_install', '-at_install')
class TestWorkforceDemo(WorkforceCase):
    DEMO_XMLIDS = [
        'demo_client_nusantara',
        'demo_client_garuda',
        'demo_client_cakrawala',
        'demo_worker_dewi',
        'demo_worker_budi',
        'demo_worker_rizky',
        'demo_worker_siti',
        'demo_worker_andi',
        'demo_order_warehouse',
        'demo_order_production',
        'demo_order_store',
        'demo_placement_dewi',
        'demo_placement_budi',
    ]

    def test_demo_records_follow_install_mode(self):
        found = [
            xmlid for xmlid in self.DEMO_XMLIDS
            if self.env.ref(f'workforce_ops.{xmlid}', raise_if_not_found=False)
        ]
        demo_count = self.env['ir.model.data'].search_count([
            ('module', '=', 'workforce_ops'),
            ('name', 'like', 'demo_%'),
        ])
        if not config['with_demo']:
            self.assertEqual(found, [])
            self.assertEqual(demo_count, 0)
            return

        self.assertEqual(len(found), 13)
        self.assertEqual(demo_count, 13)

        warehouse = self.env.ref('workforce_ops.demo_order_warehouse')
        self.assertEqual(warehouse.state, 'in_progress')
        self.assertEqual(warehouse.headcount_filled, 1)
        self.assertAlmostEqual(warehouse.progress, 33.33, places=1)

        production = self.env.ref('workforce_ops.demo_order_production')
        self.assertEqual(production.state, 'confirmed')
        self.assertEqual(production.headcount_filled, 0)

        store = self.env.ref('workforce_ops.demo_order_store')
        self.assertEqual(store.state, 'draft')
        self.assertEqual(store.headcount_filled, 0)

        self.assertEqual(self.env.ref('workforce_ops.demo_worker_dewi').status, 'placed')
        self.assertEqual(self.env.ref('workforce_ops.demo_worker_budi').status, 'available')
        self.assertEqual(self.env.ref('workforce_ops.demo_worker_rizky').status, 'available')
        self.assertEqual(self.env.ref('workforce_ops.demo_worker_siti').status, 'available')
        self.assertEqual(self.env.ref('workforce_ops.demo_worker_andi').status, 'inactive')
