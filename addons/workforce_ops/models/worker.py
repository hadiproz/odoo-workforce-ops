from odoo import api, fields, models
from odoo.exceptions import UserError


class WorkforceWorker(models.Model):
    _name = 'workforce.worker'
    _description = 'Workforce Worker'
    _rec_name = 'name'
    _order = 'name asc, id asc'

    name = fields.Char(string='Name', required=True, index=True)
    phone = fields.Char(string='Phone')
    email = fields.Char(string='Email')
    job_position = fields.Char(string='Job Position')
    active = fields.Boolean(string='Active', default=True)
    status = fields.Selection(
        selection=[
            ('available', 'Available'),
            ('placed', 'Placed'),
            ('inactive', 'Inactive'),
        ],
        string='Status',
        compute='_compute_status',
        store=True,
        index=True,
        readonly=True,
        copy=False,
        compute_sudo=True,
    )
    placement_ids = fields.One2many(
        'workforce.placement', 'worker_id', string='Placements', readonly=True, copy=False,
    )

    @api.depends('active', 'placement_ids', 'placement_ids.state')
    def _compute_status(self):
        for worker in self:
            if any(placement.state == 'placed' for placement in worker.placement_ids):
                worker.status = 'placed'
            elif worker.active:
                worker.status = 'available'
            else:
                worker.status = 'inactive'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'status' in vals:
                raise UserError('Worker status is computed and cannot be set directly.')
        return super().create(vals_list)

    def write(self, vals):
        if 'status' in vals:
            raise UserError('Worker status is computed and cannot be updated directly.')
        return super().write(vals)
