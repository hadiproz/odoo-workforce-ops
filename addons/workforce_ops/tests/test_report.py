from odoo.tests import tagged

from .common import WorkforceCase


@tagged('standard', 'post_install', '-at_install')
class TestAssignmentLetter(WorkforceCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.report_worker = cls.env['workforce.worker'].create({
            'name': 'Dewi <script> & Anggraini',
            'job_position': 'Warehouse Operator',
        })
        cls.report_order = cls.env['workforce.job.order'].create({
            'client_id': cls.fixture_partner.id,
            'position_title': 'Warehouse Operator',
            'headcount_required': 3,
        })
        cls.report_placement = cls.env['workforce.placement'].create({
            'job_order_id': cls.report_order.id,
            'worker_id': cls.report_worker.id,
            'start_date': '2026-11-01',
        })

    def test_report_action_configuration(self):
        report = self.env.ref('workforce_ops.action_report_placement_assignment')
        self.assertEqual(report.name, 'Placement Assignment Letter')
        self.assertEqual(report.model, 'workforce.placement')
        self.assertEqual(
            report.report_name, 'workforce_ops.report_placement_assignment_letter',
        )
        self.assertEqual(report.report_type, 'qweb-pdf-wkhtmltopdf')
        self.assertEqual(report.binding_view_types, 'form')
        self.assertFalse(report.multi)
        self.assertEqual(report.binding_model_id.model, 'workforce.placement')
        self.assertIn(
            self.env.ref('workforce_ops.group_workforce_user'), report.group_ids,
        )

    def test_report_renders_required_content_and_escapes_text(self):
        html = self.env['ir.actions.report']._render_qweb_html(
            'workforce_ops.report_placement_assignment_letter',
            self.report_placement.ids,
        )[0]
        self.assertIn(b'Placement Assignment Letter', html)
        self.assertIn(b'PT Fixture Client', html)
        self.assertIn(b'Warehouse Operator', html)
        self.assertIn(b'Not specified', html)
        self.assertIn(b'Authorized representative', html)
        self.assertIn(b'Dewi &lt;script&gt; &amp; Anggraini', html)
        self.assertNotIn(b'Dewi <script>', html)

    def test_report_renders_end_date(self):
        placement = self.env['workforce.placement'].create({
            'job_order_id': self.report_order.id,
            'worker_id': self.report_worker.id,
            'start_date': '2026-11-01',
            'end_date': '2027-04-30',
        })
        html = self.env['ir.actions.report']._render_qweb_html(
            'workforce_ops.report_placement_assignment_letter',
            placement.ids,
        )[0]
        self.assertIn(b'2027', html)
        self.assertNotIn(b'Not specified', html)
