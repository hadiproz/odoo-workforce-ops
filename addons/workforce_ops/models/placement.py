import psycopg2

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class WorkforcePlacement(models.Model):
    _name = 'workforce.placement'
    _description = 'Workforce Placement'
    _rec_name = 'worker_id'
    _order = 'start_date desc, id desc'

    job_order_id = fields.Many2one(
        'workforce.job.order', string='Job Order', required=True, index=True, ondelete='restrict',
    )
    worker_id = fields.Many2one(
        'workforce.worker', string='Worker', required=True, index=True, ondelete='restrict',
    )
    start_date = fields.Date(
        string='Start Date', required=True, default=fields.Date.context_today, index=True,
    )
    end_date = fields.Date(string='End Date')
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('placed', 'Placed'),
            ('finished', 'Finished'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        required=True,
        default='draft',
        index=True,
        copy=False,
    )

    _worker_active_unique = models.UniqueIndex(
        "(worker_id) WHERE state = 'placed'",
        'A worker can have at most one active placement.',
    )

    _STATE_TRANSITIONS = {
        'draft': {'placed', 'cancelled'},
        'placed': {'finished', 'cancelled'},
        'finished': set(),
        'cancelled': set(),
    }

    @api.constrains('start_date', 'end_date')
    def _check_dates(self):
        for placement in self:
            if placement.start_date and placement.end_date and placement.end_date < placement.start_date:
                raise ValidationError('The end date cannot be earlier than the start date.')

    @api.constrains('worker_id', 'state')
    def _check_single_active_placement(self):
        for placement in self:
            if placement.state != 'placed' or not placement.worker_id:
                continue
            conflict = self.sudo().search_count([
                ('worker_id', '=', placement.worker_id.id),
                ('state', '=', 'placed'),
                ('id', '!=', placement.id),
            ])
            if conflict:
                raise ValidationError('A worker can have at most one active placement.')

    @api.depends(
        'worker_id', 'worker_id.name',
        'job_order_id', 'job_order_id.display_name',
        'start_date',
    )
    def _compute_display_name(self):
        for placement in self:
            parts = []
            if placement.worker_id:
                parts.append(placement.worker_id.name)
            if placement.job_order_id:
                parts.append(placement.job_order_id.display_name)
            if placement.start_date:
                parts.append(fields.Date.to_string(placement.start_date))
            placement.display_name = ' — '.join(parts)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('state', 'draft') != 'draft':
                raise UserError('New placements must start in the draft state.')
        try:
            with self.env.cr.savepoint():
                placements = super().create(vals_list)
                self.env.flush_all()
        except psycopg2.errors.UniqueViolation as exc:
            constraint = getattr(exc.diag, 'constraint_name', None)
            if constraint != 'workforce_placement_worker_active_unique':
                raise
            raise ValidationError('A worker can have at most one active placement.') from exc
        return placements

    def write(self, vals):
        new_state = vals.get('state')
        if new_state is not None:
            if new_state not in dict(self._fields['state'].selection):
                raise UserError('Invalid placement state.')
            for placement in self:
                if (
                    new_state != placement.state
                    and new_state not in self._STATE_TRANSITIONS[placement.state]
                ):
                    raise UserError(
                        f'Cannot change placement state from {placement.state} to {new_state}.'
                    )
        try:
            with self.env.cr.savepoint():
                result = super().write(vals)
                self.env.flush_all()
        except psycopg2.errors.UniqueViolation as exc:
            constraint = getattr(exc.diag, 'constraint_name', None)
            if constraint != 'workforce_placement_worker_active_unique':
                raise
            raise ValidationError('A worker can have at most one active placement.') from exc
        if new_state == 'placed' or 'worker_id' in vals:
            self._check_single_active_placement()
        return result

    def _ensure_state(self, allowed_states, action_label):
        for placement in self:
            if placement.state not in allowed_states:
                raise UserError(
                    f'{action_label} is not allowed while the placement is {placement.state}.'
                )

    def action_place(self):
        self._ensure_state({'draft'}, 'Place')
        self.write({'state': 'placed'})
        return True

    def action_finish(self):
        self._ensure_state({'placed'}, 'Finish')
        self.write({'state': 'finished'})
        return True

    def action_cancel(self):
        self._ensure_state({'draft', 'placed'}, 'Cancel')
        self.write({'state': 'cancelled'})
        return self.env['ir.actions.actions']._for_xml_id(
            'workforce_ops.action_workforce_placements'
        )
