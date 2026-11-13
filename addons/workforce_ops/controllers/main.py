import json
import re
from datetime import datetime

from odoo import http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request

_DATE_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}$')
_REQUIRED_KEYS = {'job_order_id', 'worker_id', 'start_date'}


class WorkforceApi(http.Controller):

    @staticmethod
    def _error(code, message, status):
        return request.make_json_response(
            {'error': {'code': code, 'message': message}}, status=status,
        )

    @staticmethod
    def _has_workforce_role():
        user = request.env.user
        return (
            user.has_group('workforce_ops.group_workforce_user')
            or user.has_group('workforce_ops.group_workforce_manager')
        )

    @http.route('/api/workforce/job_orders', type='http', auth='user', methods=['GET'])
    def list_job_orders(self, **kwargs):
        if kwargs:
            return self._error('invalid_request', 'Query parameters are not supported.', 400)
        if not self._has_workforce_role():
            return self._error('forbidden', 'You need a Workforce Ops role to use this endpoint.', 403)
        orders = request.env['workforce.job.order'].search(
            [('state', '!=', 'cancelled')], order='id asc',
        )
        payload = [
            {
                'id': order.id,
                'client_name': order.client_id.name or '',
                'position': order.position_title or '',
                'required': order.headcount_required,
                'filled': order.headcount_filled,
                'state': order.state,
            }
            for order in orders
        ]
        return request.make_json_response(payload)

    @http.route(
        '/api/workforce/placements', type='http', auth='user',
        methods=['POST'], csrf=False,
    )
    def create_placement(self, **kwargs):
        if not self._has_workforce_role():
            return self._error('forbidden', 'You need a Workforce Ops role to use this endpoint.', 403)
        if request.httprequest.mimetype != 'application/json':
            return self._error(
                'unsupported_media_type', 'Content-Type must be application/json.', 415,
            )
        if kwargs:
            return self._error('invalid_request', 'Query parameters are not supported.', 400)
        try:
            payload = request.get_json_data()
        except (TypeError, ValueError):
            return self._error('invalid_request', 'Request body must be valid JSON.', 400)
        if not isinstance(payload, dict):
            return self._error('invalid_request', 'Request body must be a JSON object.', 400)
        if set(payload) != _REQUIRED_KEYS:
            return self._error(
                'invalid_request',
                'Body must contain exactly job_order_id, worker_id and start_date.',
                400,
            )

        job_order_id = payload['job_order_id']
        worker_id = payload['worker_id']
        start_date = payload['start_date']
        for field_name, value in (('job_order_id', job_order_id), ('worker_id', worker_id)):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                return self._error(
                    'invalid_request', f'{field_name} must be a positive integer.', 400,
                )
        if not isinstance(start_date, str) or not _DATE_PATTERN.match(start_date):
            return self._error(
                'invalid_request', 'start_date must be a valid YYYY-MM-DD date.', 400,
            )
        try:
            datetime.strptime(start_date, '%Y-%m-%d')
        except ValueError:
            return self._error(
                'invalid_request', 'start_date must be a valid YYYY-MM-DD date.', 400,
            )

        try:
            order = request.env['workforce.job.order'].search(
                [('id', '=', job_order_id)], limit=1,
            )
            worker = request.env['workforce.worker'].with_context(active_test=False).search(
                [('id', '=', worker_id)], limit=1,
            )
        except AccessError:
            return self._error('forbidden', 'You are not allowed to read those records.', 403)
        if not order or not worker:
            return self._error(
                'reference_not_found',
                'The referenced job order or worker was not found.',
                404,
            )

        try:
            with request.env.cr.savepoint():
                placement = request.env['workforce.placement'].create({
                    'job_order_id': order.id,
                    'worker_id': worker.id,
                    'start_date': start_date,
                })
                request.env.flush_all()
        except AccessError:
            return self._error('forbidden', 'You are not allowed to create placements.', 403)
        except ValidationError as exc:
            return self._error('validation_error', str(exc), 400)
        except UserError as exc:
            return self._error('validation_error', str(exc), 400)
        return request.make_json_response({'id': placement.id}, status=201)
