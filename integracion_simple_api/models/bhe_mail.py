# -*- coding: utf-8 -*-
import time
import logging
import requests

from odoo import models, fields, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class BHEMailWizard(models.TransientModel):
    """
    Wizard para solicitar a SimpleAPI que reenvíe una boleta de honorarios
    por correo electrónico, usando el endpoint:
        POST /api/bhe/mail/{folio}/{año}
    """
    _name = 'bhe.mail.wizard'
    _description = 'Solicitar envío de boleta por correo (SimpleAPI)'

    # ------------------------
    # CAMPOS DEL WIZARD
    # ------------------------
    email = fields.Char(
        string='Correo destinatario',
        required=True,
        help="Correo al cual SimpleAPI enviará la boleta PDF",
    )
    wait_seconds = fields.Integer(
        string='Esperar (seg.)',
        default=1,
        help="Tiempo de espera (segundos) antes de llamar a la API. "
             "Útil si acabas de emitir una boleta y quieres dar tiempo a SimpleAPI.",
    )

    # ------------------------
    # ACCIÓN PRINCIPAL
    # ------------------------
    def action_send(self):
        """
        1) Obtiene la boleta activa.
        2) Valida datos esenciales (folio, email, fecha).
        3) Llama al endpoint de SimpleAPI para enviar por correo.
        4) Registra trazabilidad en el chatter.
        """
        self.ensure_one()

        # 1) Boleta activa
        active_id = self.env.context.get('active_id')
        if not active_id:
            raise UserError(_("No se encontró la boleta activa."))

        boleta = self.env['boleta.honorarios'].browse(active_id).exists()
        if not boleta:
            raise UserError(_("La boleta no existe."))

        # 2) Validaciones mínimas (permitimos cualquier estado)
        if not boleta.numero_boleta:
            raise ValidationError(_("La boleta no tiene folio."))

        if not self.email or '@' not in self.email:
            raise ValidationError(_("Debe indicar un correo válido."))

        if not boleta.fecha_emision:
            raise ValidationError(_("La boleta no tiene fecha de emisión."))

        # Espera opcional
        if (self.wait_seconds or 0) > 0:
            time.sleep(self.wait_seconds)

        anio = boleta.fecha_emision.year

        # 3) Configuración
        cfg = boleta.get_simpleapi_config()
        base_url = (cfg.get('base_url') or '').rstrip('/')
        api_key = cfg.get('api_key') or ''
        timeout = int(cfg.get('timeout') or 30)

        url = f"{base_url}/bhe/mail/{boleta.numero_boleta}/{anio}"
        headers = {
            'Authorization': api_key,
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'odoo-18-bhe',
        }
        payload = {
            'RutUsuario': (boleta.rut_usuario or '').replace('.', '').replace('-', ''),
            'PasswordSII': boleta.password_sii or '',
            'Correo': self.email,
        }

        _logger.info(
            "[BHE][MAIL] POST %s -> to=%s (folio=%s, anio=%s)",
            url, self.email, boleta.numero_boleta, anio
        )

        # 4) Llamada y manejo de respuesta
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
            body_preview = (resp.text or '')[:300]
            _logger.info("[BHE][MAIL] status=%s body=%s", resp.status_code, body_preview)

            if resp.status_code in (200, 202):
                # Éxito normal
                boleta.message_post(
                    body=_("Correo solicitado a SimpleAPI (folio %s): %s")
                         % (boleta.numero_boleta, self.email),
                    message_type='notification',
                )
                return {'type': 'ir.actions.act_window_close'}

            if resp.status_code == 500:
                # Soft-success: el proveedor a veces devuelve 500 aunque el SII envíe el mail
                boleta.message_post(
                    body=_("SimpleAPI devolvió HTTP 500 al solicitar el envío por correo, "
                           "pero es posible que el SII lo haya enviado de todas formas. "
                           "Revise su bandeja. Respuesta: %s") % body_preview,
                    message_type='comment',
                )
                _logger.warning("[BHE][MAIL] HTTP 500 recibido; tratamos como 'soft-success'.")
                return {'type': 'ir.actions.act_window_close'}

            # Otros códigos se tratan como error real
            raise UserError(_("Error en API (HTTP %s): %s") % (resp.status_code, body_preview))

        except requests.Timeout:
            raise UserError(_("La solicitud a SimpleAPI excedió el tiempo de espera (%ss).") % timeout)
        except Exception as e:
            raise UserError(_("Error inesperado llamando a SimpleAPI: %s") % str(e))