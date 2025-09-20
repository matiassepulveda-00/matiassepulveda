# -*- coding: utf-8 -*-
import base64
from odoo import http
from odoo.http import request

class BoletaHonorariosController(http.Controller):

    @http.route('/boleta_honorarios/webhook', type='json', auth='none', methods=['POST'], csrf=False)
    def webhook_simpleapi(self, **kwargs):
        # placeholder: si algún día SimpleAPI hace callbacks
        data = request.jsonrequest
        return {'status': 'ok'}

    @http.route('/boleta_honorarios/download/<int:boleta_id>', type='http', auth='user')
    def download_pdf(self, boleta_id, **kwargs):
        boleta = request.env['boleta.honorarios'].browse(boleta_id)
        if not boleta.exists() or not boleta.pdf_file:
            return request.not_found()
        return request.make_response(
            base64.b64decode(boleta.pdf_file),
            headers=[
                ('Content-Type', 'application/pdf'),
                ('Content-Disposition', f'inline; filename="{boleta.pdf_filename or "boleta.pdf"}"'),
            ]
        )

    # Opcional: expone anulación vía ruta interna
    @http.route('/boleta_honorarios/anular/<int:boleta_id>/<motivo>', type='json', auth='user', methods=['POST'], csrf=False)
    def anular_boleta_api(self, boleta_id, motivo, **kwargs):
        rec = request.env['boleta.honorarios'].browse(boleta_id).sudo()
        rec.motivo_anulacion = motivo
        rec.action_anular_boleta_path()
        return {'status': 'ok', 'state': rec.state, 'folio': rec.numero_boleta}