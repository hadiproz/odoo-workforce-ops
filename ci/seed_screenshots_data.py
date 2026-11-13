"""Sample data for the README screenshots.

Executed with ``odoo shell`` against the demo database right after the
workforce_ops module is installed. Everything goes through the ORM, so the
workflow guards and the active-placement unique index still apply. None of
this is part of the addon or its demo data.
"""

import logging

_logger = logging.getLogger('screenshots.seed')

admin = env.ref('base.user_admin')
manager_group = env.ref('workforce_ops.group_workforce_manager')
if manager_group not in admin.group_ids:
    admin.write({'group_ids': [(4, manager_group.id)]})

JobOrder = env['workforce.job.order']
Worker = env['workforce.worker']
Placement = env['workforce.placement']

if JobOrder.search_count([]) > 3:
    _logger.info('screenshot sample data already present; nothing to do')
else:
    nusantara = env.ref('workforce_ops.demo_client_nusantara')
    garuda = env.ref('workforce_ops.demo_client_garuda')
    cakrawala = env.ref('workforce_ops.demo_client_cakrawala')

    def make_order(client, title, required, deadline, target_state):
        order = JobOrder.create({
            'client_id': client.id,
            'position_title': title,
            'headcount_required': required,
            'deadline': deadline,
        })
        if target_state in ('confirmed', 'in_progress', 'done'):
            order.action_confirm()
        if target_state in ('in_progress', 'done'):
            order.action_start()
        if target_state == 'done':
            order.action_done()
        if target_state == 'cancelled':
            order.action_cancel()
        return order

    def make_worker(name, position, active=True):
        return Worker.create({
            'name': name,
            'job_position': position,
            'phone': '+62 812 0000 %04d' % (2000 + Worker.search_count([]) + 1),
            'email': '%s@example.com' % name.lower().replace(' ', '.'),
            'active': active,
        })

    def make_placement(worker, order, start_date, end_date, target_state):
        placement = Placement.create({
            'worker_id': worker.id,
            'job_order_id': order.id,
            'start_date': start_date,
            'end_date': end_date,
        })
        if target_state in ('placed', 'finished'):
            placement.action_place()
        if target_state == 'finished':
            placement.action_finish()
        if target_state == 'cancelled':
            placement.action_cancel()
        return placement

    forklift = make_order(nusantara, 'Forklift Operator', 2, '2027-01-10', 'draft')
    quality = make_order(garuda, 'Quality Control Inspector', 2, '2026-12-28', 'in_progress')
    cashier = make_order(cakrawala, 'Cashier', 4, '2027-01-05', 'draft')
    packing = make_order(nusantara, 'Packing Operator', 6, '2026-12-22', 'in_progress')
    machine = make_order(garuda, 'Machine Operator', 3, '2027-01-18', 'confirmed')
    sales = make_order(cakrawala, 'Sales Assistant', 2, '2026-12-12', 'confirmed')
    supervisor = make_order(nusantara, 'Warehouse Supervisor', 1, '2026-11-30', 'done')
    make_order(cakrawala, 'Stock Clerk', 2, '2027-01-25', 'draft')

    agus = make_worker('Agus Setiawan', 'Packing Operator')
    rina = make_worker('Rina Kartika', 'Quality Control Inspector')
    bayu = make_worker('Bayu Nugroho', 'Packing Operator')
    fitri = make_worker('Fitri Handayani', 'Packing Operator')
    dedi = make_worker('Dedi Kurniawan', 'Machine Operator')
    maya = make_worker('Maya Sari', 'Sales Assistant')
    hendra = make_worker('Hendra Wijaya', 'Warehouse Supervisor')
    nur = make_worker('Nur Aisyah', 'Cashier')

    make_placement(rina, quality, '2026-11-10', '2027-05-09', 'placed')
    make_placement(agus, packing, '2026-11-15', None, 'placed')
    make_placement(bayu, packing, '2026-12-01', None, 'placed')
    make_placement(dedi, machine, '2026-11-20', None, 'placed')
    make_placement(hendra, supervisor, '2026-08-01', '2026-10-31', 'finished')
    make_placement(maya, sales, '2027-01-02', None, 'draft')
    make_placement(nur, cashier, '2027-01-12', None, 'draft')
    make_placement(
        fitri, env.ref('workforce_ops.demo_order_warehouse'), '2026-11-25', None, 'placed',
    )
    make_placement(
        env.ref('workforce_ops.demo_worker_siti'),
        env.ref('workforce_ops.demo_order_store'),
        '2026-12-05', None, 'cancelled',
    )

    _logger.info('created screenshot sample data')

expected_orders = 11
expected_workers = 13
expected_placements = 11
orders = JobOrder.search_count([])
workers = Worker.with_context(active_test=False).search_count([])
placements = Placement.search_count([])
print(
    'SEED_COUNTS job_orders=%s workers=%s placements=%s admin_manager=%s'
    % (orders, workers, placements, manager_group in admin.group_ids)
)
assert (orders, workers, placements) == (
    expected_orders, expected_workers, expected_placements,
), 'screenshot sample data is incomplete'
env.cr.commit()
print('SEED_OK')
