# -*- coding: utf-8 -*-
import requests
from odoo import models, fields, _
from odoo.exceptions import UserError, ValidationError
import time

class BHEMailWizard(models.TransientModel):
    _name = 'bhe.mail.wizard'
    _description = 'Solicitar envío de boleta por correo (SimpleAPI)'

    email = fields.Char(string='Correo destinatario', required=True)
    wait_seconds = fields.Integer(string='Esperar (seg.)', default=1)

    def action_send(self):
        self.ensure_one()
        active_id = self.env.context.get('active_id')
        if not active_id:
            raise UserError(_("No se encontró la boleta activa."))
        boleta = self.env['boleta.honorarios'].browse(active_id)
        if not boleta.exists():
            raise UserError(_("La boleta no existe."))

        if boleta.state not in ('emitted', 'downloaded'):
            raise ValidationError(_("Solo se puede solicitar correo para boletas emitidas o descargadas."))

        if not boleta.numero_boleta:
            raise ValidationError(_("La boleta no tiene folio."))

        if not self.email or '@' not in self.email:
            raise ValidationError(_("Debe indicar un correo válido."))

        if self.wait_seconds:
            time.sleep(self.wait_seconds)

        # Año
        if not boleta.fecha_emision:
            raise ValidationError(_("La boleta no tiene fecha de emisión."))
        anio = boleta.fecha_emision.year

        config = boleta.get_simpleapi_config()
        url = f"{config['base_url']}/bhe/mail/{boleta.numero_boleta}/{anio}"
        headers = {
            'Authorization': config['api_key'],
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        payload = {
            'RutUsuario': boleta.rut_usuario.replace('.', '').replace('-', ''),
            'PasswordSII': boleta.password_sii,
            'Correo': self.email
        }

        resp = requests.post(url, json=payload, headers=headers, timeout=config['timeout'])
        if resp.status_code not in (200, 202):
            raise UserError(_("Error en API (HTTP %s): %s") % (resp.status_code, resp.text[:200]))

        try:
            data = resp.json()
        except Exception:
            data = {'message': resp.text}

        boleta.message_post(body=_("Solicitud de envío de correo a %s realizada.") % self.email,
                            message_type='notification')
        return {'type': 'ir.actions.act_window_close'}