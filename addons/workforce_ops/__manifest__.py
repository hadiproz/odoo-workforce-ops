{
    'name': 'Workforce Ops',
    'version': '20.0.1.0.0',
    'author': 'Hadi Sutomo Wonosantoso',
    'category': 'Human Resources',
    'summary': 'Workforce placement operations for outsourcing companies',
    'description': """
Workforce Ops
=============

A small portfolio module for an outsourcing company that places workers at
client companies. It manages staffing requests (job orders), placeable
workers, and placements between them, with guarded workflows, native Odoo 20
access controls, a printable assignment letter, and two JSON HTTP endpoints.

The original addon source and this repository are released under the MIT
license (see LICENSE); the manifest license label is Odoo's broader
"Other OSI approved licence" metadata value.
""",
    'license': 'Other OSI approved licence',
    'depends': ['base', 'web', 'base_report_wkhtmltox'],
    'data': [
        'security/workforce_security.xml',
        'security/ir.access.csv',
        'report/placement_report.xml',
        'views/job_order_views.xml',
        'views/worker_views.xml',
        'views/placement_views.xml',
        'views/workforce_menus.xml',
    ],
    'demo': [
        'demo/demo.xml',
    ],
    'application': True,
    'installable': True,
    'auto_install': False,
}
