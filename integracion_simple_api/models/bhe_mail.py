# -*- coding: utf-8 -*-
import requests
from odoo import models, fields, _
from odoo.exceptions import UserError, ValidationError
import time


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
        help="Correo al cual SimpleAPI enviará la boleta PDF"
    )
    wait_seconds = fields.Integer(
        string='Esperar (seg.)',
        default=1,
        help="Tiempo de espera (segundos) antes de llamar a la API. "
             "Útil si acabas de emitir una boleta y quieres dar tiempo a SimpleAPI."
    )

    # ------------------------
    # ACCIÓN PRINCIPAL
    # ------------------------
    def action_send(self):
        """
        Acción del botón 'Enviar'.
        1. Valida la boleta activa.
        2. Construye la URL con folio y año.
        3. Llama a SimpleAPI para pedir envío de correo.
        4. Deja trazabilidad en el chatter de la boleta.
        """
        self.ensure_one()  # Asegura que se ejecuta sobre un solo wizard.

        # 1) Buscar boleta activa (contexto de donde se abrió el wizard)
        active_id = self.env.context.get('active_id')
        if not active_id:
            raise UserError(_("No se encontró la boleta activa."))
        boleta = self.env['boleta.honorarios'].browse(active_id)
        if not boleta.exists():
            raise UserError(_("La boleta no existe."))

        # 2) Validaciones previas de negocio
        if boleta.state not in ('emitted', 'downloaded'):
            raise ValidationError(_("Solo se puede solicitar correo para boletas emitidas o descargadas."))
        if not boleta.numero_boleta:
            raise ValidationError(_("La boleta no tiene folio."))
        if not self.email or '@' not in self.email:
            raise ValidationError(_("Debe indicar un correo válido."))
        if not boleta.fecha_emision:
            raise ValidationError(_("La boleta no tiene fecha de emisión."))

        # 3) Pequeña espera opcional (para dar tiempo a SimpleAPI)
        if self.wait_seconds:
            time.sleep(self.wait_seconds)

        # 4) Año desde la fecha de emisión (requerido por SimpleAPI en la ruta)
        anio = boleta.fecha_emision.year

        # 5) Configuración de SimpleAPI desde Settings
        config = boleta.get_simpleapi_config()

        # Construcción de la URL con folio y año
        url = f"{config['base_url']}/bhe/mail/{boleta.numero_boleta}/{anio}"

        # Headers de autenticación y tipo de contenido
        headers = {
            'Authorization': config['api_key'],
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

        # Payload que SimpleAPI requiere
        payload = {
            'RutUsuario': boleta.rut_usuario.replace('.', '').replace('-', ''),
            'PasswordSII': boleta.password_sii,
            'Correo': self.email
        }

        # 6) Llamada POST a SimpleAPI
        resp = requests.post(url, json=payload, headers=headers, timeout=config['timeout'])

        # 7) Validación de respuesta HTTP
        if resp.status_code not in (200, 202):
            # Mostrar un error claro en Odoo si falla
            raise UserError(_("Error en API (HTTP %s): %s") % (resp.status_code, resp.text[:200]))

        # 8) Intentar parsear JSON, si no es posible se guarda texto plano
        try:
            data = resp.json()
        except Exception:
            data = {'message': resp.text}

        # 9) Dejar trazabilidad en el chatter de la boleta
        boleta.message_post(
            body=_("Solicitud de envío de correo a %s realizada.") % self.email,
            message_type='notification'
        )

        # 10) Cerrar el wizard (acción estándar de Odoo)
        return {'type': 'ir.actions.act_window_close'}