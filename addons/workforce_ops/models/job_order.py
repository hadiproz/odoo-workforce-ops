from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class WorkforceJobOrder(models.Model):
    _name = 'workforce.job.order'
    _description = 'Workforce Job Order'
    _rec_name = 'position_title'
    _order = 'deadline asc, id desc'

    client_id = fields.Many2one(
        'res.partner', string='Client', required=True, index=True, ondelete='restrict',
    )
    position_title = fields.Char(string='Position Title', required=True)
    headcount_required = fields.Integer(string='Headcount Required', required=True, default=1)
    headcount_filled = fields.Integer(
        string='Headcount Filled',
        compute='_compute_headcount_filled',
        store=True,
        readonly=True,
        copy=False,
        compute_sudo=True,
    )
    progress = fields.Float(
        string='Progress (%)',
        compute='_compute_progress',
        store=True,
        digits=(16, 2),
        readonly=True,
        copy=False,
        compute_sudo=True,
    )
    deadline = fields.Date(string='Deadline', index=True)
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('in_progress', 'In Progress'),
            ('done', 'Done'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        required=True,
        default='draft',
        index=True,
        copy=False,
    )
    placement_ids = fields.One2many(
        'workforce.placement', 'job_order_id', string='Placements', readonly=True, copy=False,
    )

    _headcount_required_positive = models.Constraint(
        'CHECK (headcount_required > 0)',
        'Headcount required must be greater than zero.',
    )

    _STATE_TRANSITIONS = {
        'draft': {'confirmed', 'cancelled'},
        'confirmed': {'in_progress', 'cancelled'},
        'in_progress': {'done', 'cancelled'},
        'done': set(),
        'cancelled': set(),
    }

    @api.depends('placement_ids', 'placement_ids.state')
    def _compute_headcount_filled(self):
        for order in self:
            order.headcount_filled = len(
                order.placement_ids.filtered(lambda placement: placement.state == 'placed')
            )

    @api.depends('headcount_required', 'headcount_filled')
    def _compute_progress(self):
        for order in self:
            if order.headcount_required and order.headcount_required > 0:
                order.progress = 100.0 * order.headcount_filled / order.headcount_required
            else:
                order.progress = 0.0

    @api.depends('client_id', 'client_id.name', 'position_title')
    def _compute_display_name(self):
        for order in self:
            client = order.client_id.name or ''
            title = order.position_title or ''
            order.display_name = f'{client} — {title}' if client and title else (client or title or '')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('state', 'draft') != 'draft':
                raise UserError('New job orders must start in the draft state.')
            if any(field in vals for field in ('headcount_filled', 'progress')):
                raise UserError('Derived job order values cannot be set directly.')
            required = vals.get('headcount_required', 1)
            if required is not None and required <= 0:
                raise ValidationError('Headcount required must be greater than zero.')
        return super().create(vals_list)

    def write(self, vals):
        if any(field in vals for field in ('headcount_filled', 'progress')):
            raise UserError('Derived job order values cannot be updated directly.')
        new_state = vals.get('state')
        if new_state is not None:
            if new_state not in dict(self._fields['state'].selection):
                raise UserError('Invalid job order state.')
            for order in self:
                if new_state != order.state and new_state not in self._STATE_TRANSITIONS[order.state]:
                    raise UserError(
                        f'Cannot change job order state from {order.state} to {new_state}.'
                    )
        return super().write(vals)

    def _ensure_state(self, allowed_states, action_label):
        for order in self:
            if order.state not in allowed_states:
                raise UserError(
                    f'{action_label} is not allowed while the job order is {order.state}.'
                )

    def action_confirm(self):
        self._ensure_state({'draft'}, 'Confirm')
        self.write({'state': 'confirmed'})
        return True

    def action_start(self):
        self._ensure_state({'confirmed'}, 'Start')
        self.write({'state': 'in_progress'})
        return True

    def action_done(self):
        self._ensure_state({'in_progress'}, 'Mark Done')
        self.write({'state': 'done'})
        return True

    def action_cancel(self):
        self._ensure_state({'draft', 'confirmed', 'in_progress'}, 'Cancel')
        self.write({'state': 'cancelled'})
        return self.env['ir.actions.actions']._for_xml_id(
            'workforce_ops.action_workforce_job_orders'
        )
