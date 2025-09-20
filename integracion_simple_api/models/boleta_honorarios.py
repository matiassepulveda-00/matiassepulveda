# -*- coding: utf-8 -*-
import requests
import json
import base64
import time
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)

def _mask_key(key: str, show_start: int = 6, show_end: int = 4) -> str:
    """
    Enmascara una API Key, dejando ver los primeros y últimos caracteres.
    Evita exponer secretos completos en logs en producción.
    """
    try:
        if not key:
            return ''
        ks = str(key)
        if len(ks) <= show_start + show_end:
            return '*' * len(ks)
        return f"{ks[:show_start]}{'*' * 6}{ks[-show_end:]}"
    except Exception:
        return '******'

class BoletaHonorarios(models.Model):
    _name = 'boleta.honorarios'
    _description = 'Boleta de Honorarios SimpleAPI'
    _order = 'fecha_emision desc'
    _rec_name = 'numero_boleta'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # Campos básicos
    numero_boleta = fields.Char('Número de Boleta', readonly=True, tracking=True)
    fecha_emision = fields.Date('Fecha Emisión', default=fields.Date.today, required=True, tracking=True)
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('processing', 'Procesando'),
        ('emitted', 'Emitida'),
        ('downloaded', 'Descargada'),
        ('error', 'Error'),
        ('cancelled', 'Anulada')
    ], string='Estado', default='draft', tracking=True)

    # Datos del emisor
    rut_usuario = fields.Char('RUT Usuario', required=True, help='RUT del usuario que emite la boleta')
    password_sii = fields.Char('Password SII', required=True, help='Contraseña del SII')
    direccion_emisor = fields.Selection([
        ('0', 'Dirección Principal'),
        ('1', 'Dirección Secundaria')
    ], string='Dirección Emisor', default='0', required=True)

    # Configuración de retención
    retencion = fields.Selection([
        ('0', 'Sin Retención'),
        ('1', 'Con Retención (10%)')
    ], string='Retención', default='1', required=True)

    # Datos del receptor
    partner_id = fields.Many2one('res.partner', string='Receptor', tracking=True)
    receptor_rut = fields.Char('RUT Receptor', required=True, tracking=True)
    receptor_nombre = fields.Char('Nombre Receptor', required=True, tracking=True)
    receptor_direccion = fields.Text('Dirección Receptor', required=True)
    receptor_region = fields.Selection([
        ('1', 'Tarapacá'), ('2', 'Antofagasta'), ('3', 'Atacama'), ('4', 'Coquimbo'),
        ('5', 'Valparaíso'), ('6', "O'Higgins"), ('7', 'Maule'), ('8', 'Biobío'),
        ('9', 'Araucanía'), ('10', 'Los Lagos'), ('11', 'Aysén'), ('12', 'Magallanes'),
        ('13', 'Metropolitana'), ('14', 'Los Ríos'), ('15', 'Arica y Parinacota'), ('16', 'Ñuble')
    ], string='Región Receptor', default='13', required=True)
    receptor_comuna = fields.Char('Comuna Receptor', required=True)

    # Detalles de la prestación
    descripcion_servicio = fields.Text('Descripción del Servicio', required=True)
    valor_bruto = fields.Monetary('Valor Bruto', required=True, currency_field='currency_id', tracking=True)
    currency_id = fields.Many2one('res.currency', string='Moneda', default=lambda self: self.env.company.currency_id)

    # Respuesta y archivo
    response_data = fields.Text('Respuesta API')
    pdf_file = fields.Binary('Archivo PDF', attachment=True)
    pdf_filename = fields.Char('Nombre Archivo PDF')

    # Envío por correo
    email_destinatario = fields.Char('Correo destinatario', help='Correo al que se enviará la boleta al emitir')

    # Seguimiento
    error_message = fields.Text('Mensaje de Error')
    fecha_procesamiento = fields.Datetime('Fecha Procesamiento')
    intentos = fields.Integer('Intentos', default=0)

    # Motivo de anulación para endpoint con path params
    motivo_anulacion = fields.Selection([
        ('1', '1: No se efectuó el pago'),
        ('2', '2: No se efectuó la prestación'),
        ('3', '3: Error en la digitación'),
    ], string='Motivo de anulación', help='Motivo exigido por el endpoint de anulación')

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.partner_id:
            partner = self.partner_id
            self.receptor_rut = partner.vat or ''
            self.receptor_nombre = partner.name or ''
            self.receptor_direccion = partner.street or ''
            if partner.state_id:
                region_mapping = {'Santiago': '13', 'Valparaíso': '5', 'Concepción': '8'}
                self.receptor_region = region_mapping.get(partner.state_id.name, '13')
            if partner.city:
                self.receptor_comuna = partner.city
            if not self.email_destinatario and partner.email:
                self.email_destinatario = partner.email

    @api.onchange('receptor_rut', 'receptor_nombre')
    def _onchange_receptor_data(self):
        if self.receptor_rut and not self.partner_id:
            partner = self.env['res.partner'].search([('vat', '=', self.receptor_rut)], limit=1)
            if partner:
                self.partner_id = partner
                self._onchange_partner_id()

    @api.model
    def get_simpleapi_config(self):
        config = self.env['ir.config_parameter'].sudo()
        api_key = config.get_param('boleta_honorarios.simpleapi_api_key', '4648-N330-6392-2590-9354')
        base_url = config.get_param('boleta_honorarios.simpleapi_base_url', 'https://servicios.simpleapi.cl/api')
        timeout = int(config.get_param('boleta_honorarios.simpleapi_timeout', '30'))
        _logger.info(f"[BHE] Config SimpleAPI base_url={base_url} api_key={_mask_key(api_key)} timeout={timeout}")
        return {
            'api_key': api_key,
            'base_url': base_url,
            'timeout': timeout
        }  # [1][3]

    def action_emitir_boleta(self):
        for record in self:
            try:
                record.state = 'processing'
                record.intentos += 1
                record.fecha_procesamiento = fields.Datetime.now()
                record.message_post(body="Iniciando emisión de boleta de honorarios...")
                if not record.descripcion_servicio:
                    raise UserError(_('Debe agregar una descripción del servicio'))
                if record.valor_bruto <= 0:
                    raise UserError(_('El valor bruto debe ser mayor a cero'))
                if not record.email_destinatario or '@' not in record.email_destinatario:
                    raise UserError(_('Debe indicar un correo destinatario válido (ej: correo@dominio.cl)'))
                data = record._prepare_api_data()
                response = record._call_simpleapi(data)
                if response.get('success') or response.get('numeroDocumento') or response.get('numero') or response.get('folio'):
                    record._process_successful_response(response)
                else:
                    record._process_error_response(response)
            except Exception as e:
                _logger.error(f"Error emitiendo boleta {record.id}: {str(e)}")
                record.state = 'error'
                record.error_message = str(e)
                record.message_post(body=f"Error emitiendo boleta: {str(e)}", message_type='comment')

    def _prepare_api_data(self):
        self.ensure_one()
        return {
            'RutUsuario': self.rut_usuario.replace('.', '').replace('-', ''),
            'PasswordSII': self.password_sii,
            'Retencion': int(self.retencion),
            'FechaEmision': self.fecha_emision.strftime('%d-%m-%Y'),
            'Emisor': {'Direccion': self.direccion_emisor},
            'Receptor': {
                'Rut': self.receptor_rut.replace('.', '').replace('-', ''),
                'Nombre': self.receptor_nombre,
                'Direccion': self.receptor_direccion,
                'Region': int(self.receptor_region),
                'Comuna': self.receptor_comuna
            },
            'Detalles': [{'Nombre': self.descripcion_servicio, 'Valor': int(self.valor_bruto)}]
        }  # [3]

    def _call_simpleapi(self, data):
        config = self.get_simpleapi_config()
        try:
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'Authorization': config['api_key']
            }
            url = f"{config['base_url']}/bhe/emitir"
            _logger.info(f"🚀 [BHE] POST emitir -> {url} key={_mask_key(headers['Authorization'])}")
            resp = requests.post(url, json=data, headers=headers, timeout=config['timeout'])
            _logger.info(f"[BHE] emitir status={resp.status_code} body={resp.text[:300]}")
            if resp.status_code == 200:
                return resp.json()
            raise UserError(_(f"Error en API: {resp.status_code} - {resp.text}"))
        except UserError:
            raise
        except Exception as e:
            raise UserError(_(f"Error inesperado llamando SimpleAPI: {str(e)}"))  # [1][3]

    def _send_mail_via_simpleapi(self, folio: str, anio: int, email: str, wait_seconds: int = 1):
        self.ensure_one()
        if wait_seconds:
            time.sleep(wait_seconds)
        config = self.get_simpleapi_config()
        url = f"{config['base_url']}/bhe/mail/{folio}/{anio}"
        headers = {
            'Authorization': config['api_key'],
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'User-Agent': 'odoo-18-bhe'
        }
        payload = {
            'RutUsuario': self.rut_usuario.replace('.', '').replace('-', ''),
            'PasswordSII': self.password_sii,
            'Correo': email
        }
        _logger.info(f"✉️ [BHE] POST mail {url} key={_mask_key(headers['Authorization'])} -> {payload}")
        resp = requests.post(url, json=payload, headers=headers, timeout=config['timeout'])
        _logger.info(f"Mail status={resp.status_code} ct={resp.headers.get('Content-Type')} body={resp.text[:300]}")
        if resp.status_code in (200, 202):
            self.message_post(body=f"Correo solicitado a SimpleAPI (folio {folio}): {email}", message_type='notification')
            return True
        self.message_post(
            body=f"No se pudo solicitar envío por correo (POST). Status {resp.status_code}. Body: {resp.text[:300]}",
            message_type='comment'
        )
        return False  # [3]

    def _process_successful_response(self, response):
        self.ensure_one()
        self.response_data = json.dumps(response, indent=2)
        folio = (response.get('folio') or response.get('numeroDocumento') or
                 response.get('numero_boleta') or response.get('numeroBoleta') or response.get('numero'))
        if folio:
            self.numero_boleta = str(folio)
            self.state = 'emitted'
            self.error_message = False
            self.message_post(body=f"Boleta emitida exitosamente. Número: {self.numero_boleta}", message_type='notification')
            # Año de emisión
            anio = None
            for k in ('anio', 'anioFolio', 'year', 'anio_emision', 'anioFolioEmitido'):
                if response.get(k):
                    try:
                        anio = int(str(response.get(k))[:4]); break
                    except Exception:
                        pass
            if not anio and self.fecha_emision:
                anio = fields.Date.from_string(self.fecha_emision).year
            # Enviar por correo
            if anio and self.email_destinatario:
                try:
                    self._send_mail_via_simpleapi(self.numero_boleta, anio, self.email_destinatario, wait_seconds=1)
                except Exception as e:
                    _logger.exception(f"Fallo envío de correo por SimpleAPI: {e}")
                    self.message_post(body=f"Error solicitando envío por correo: {e}", message_type='comment')
        else:
            self.state = 'error'
            self.error_message = "Respuesta exitosa pero sin número de boleta"
            self.message_post(body=f"Respuesta exitosa sin folio. Response: {self.response_data}", message_type='comment')  # [3]

    def _process_error_response(self, response):
        self.ensure_one()
        self.state = 'error'
        error_msg = (response.get('error') or response.get('mensaje') or response.get('message') or
                     response.get('descripcion') or response.get('detalle') or 'Error desconocido')
        self.error_message = error_msg
        self.response_data = json.dumps(response, indent=2)
        self.message_post(body=f"Error en emisión: {error_msg}", message_type='comment')  # [3]

    # Se remueven descargas/cron del viewer
    def _schedule_pdf_download(self):
        return

    def action_download_pdf(self):
        return

    # LEGACY: anulación sin path (se conserva y se robustece)
    def action_anular_boleta(self):
        for record in self:
            if record.state not in ['emitted', 'downloaded']:
                raise UserError(_('Solo se pueden anular boletas emitidas'))
            try:
                config = record.get_simpleapi_config()
                headers = {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'Authorization': config['api_key']
                }
                data = {
                    'numeroDocumento': record.numero_boleta,
                    'rutEmisor': record.rut_usuario.replace('.', '').replace('-', ''),
                    'passwordSII': record.password_sii
                }
                url = f"{config['base_url']}/bhe/anular"
                _logger.info(f"[BHE] POST legacy {url} key={_mask_key(headers['Authorization'])}")
                resp = requests.post(url, json=data, headers=headers, timeout=config['timeout'])
                body_preview = resp.text[:300] if hasattr(resp, 'text') else str(resp)[:300]
                if resp.status_code == 200:
                    ok = False
                    try:
                        j = resp.json()
                        if isinstance(j, dict) and not j.get('error'):
                            ok = True
                    except Exception:
                        txt = (resp.text or '').lower()
                        ok = 'anulada' in txt or 'correctamente' in txt
                    if ok:
                        record.state = 'cancelled'
                        record.message_post(body=f"Boleta {record.numero_boleta} anulada exitosamente (legacy). Resp: {body_preview}",
                                            message_type='notification')
                        continue
                raise UserError(_('Error anulando boleta: %s') % body_preview)
            except Exception as e:
                raise UserError(_('Error anulando boleta: %s') % str(e))  # [4][3]

    # NUEVO: Anulación con {folio}/{motivo} y body con credenciales, manejando texto plano
    def action_anular_boleta_path(self):
        for record in self:
            if record.state not in ['emitted', 'downloaded']:
                raise UserError(_('Solo se pueden anular boletas emitidas o descargadas'))
            if not record.numero_boleta:
                raise UserError(_('No existe folio para anular'))
            if record.motivo_anulacion not in ('1', '2', '3'):
                raise UserError(_('Debe seleccionar un motivo válido (1, 2 o 3)'))
            try:
                config = record.get_simpleapi_config()
                headers = {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'Authorization': config['api_key'],
                    'User-Agent': 'odoo-18-bhe'
                }
                folio = str(record.numero_boleta).strip()
                motivo = record.motivo_anulacion
                url = f"{config['base_url']}/bhe/anular/{folio}/{motivo}"
                payload = {
                    "RutUsuario": record.rut_usuario.replace('.', '').replace('-', ''),
                    "PasswordSII": record.password_sii
                }
                _logger.info(f"🧻 [BHE] POST {url} key={_mask_key(headers['Authorization'])} -> body={{'RutUsuario':'***','PasswordSII':'***'}}")
                resp = requests.post(url, json=payload, headers=headers, timeout=config['timeout'])
                body_preview = resp.text[:300] if hasattr(resp, 'text') else str(resp)[:300]
                _logger.info(f"[BHE] Anular status={resp.status_code} body={body_preview}")

                if resp.status_code in (200, 202):
                    # Intentar JSON
                    data = None
                    try:
                        data = resp.json()
                    except Exception:
                        data = None

                    if isinstance(data, dict):
                        success_flag = str(data.get('success', 'true')).lower() in ('true', '1', 'yes')
                        has_error = bool(data.get('error'))
                        if success_flag and not has_error:
                            record.state = 'cancelled'
                            record.message_post(
                                body=f"Boleta {folio} anulada exitosamente (motivo {motivo}). Resp: {data}",
                                message_type='notification'
                            )
                            continue
                        raise UserError(_('Error anulando boleta: %s') % (data.get('error') or data))
                    else:
                        # Texto plano
                        txt = (resp.text or '').strip()
                        if txt and ('anulada' in txt.lower() or 'correctamente' in txt.lower()):
                            record.state = 'cancelled'
                            record.message_post(
                                body=f"Boleta {folio} anulada exitosamente (motivo {motivo}). Resp: {txt}",
                                message_type='notification'
                            )
                            continue
                        # 200 sin JSON ni palabra clave: marcar cancelado pero dejar evidencia
                        record.state = 'cancelled'
                        record.message_post(
                            body=f"Boleta {folio} anulada (HTTP {resp.status_code}) sin JSON; cuerpo: {txt[:300]}",
                            message_type='notification'
                        )
                        continue

                # Status distinto de 200/202
                raise UserError(_('Error anulando boleta: %s - %s') % (resp.status_code, body_preview))
            except UserError:
                raise
            except Exception as e:
                _logger.warning(f"[BHE] Error inesperado anulando boleta {record.numero_boleta}: {e}")
                raise UserError(_('Error inesperado anulando boleta: %s') % str(e))  # [4][3]

    @api.model
    def cron_download_pending_pdfs(self):
        return

    @api.constrains('valor_bruto')
    def _check_valor_bruto(self):
        for rec in self:
            if rec.valor_bruto <= 0:
                raise ValidationError(_('El valor bruto debe ser mayor a cero'))

    @api.constrains('rut_usuario')
    def _check_rut_usuario(self):
        for rec in self:
            if rec.rut_usuario and not self._validate_rut(rec.rut_usuario):
                raise ValidationError(_('El RUT del usuario no es válido'))

    @api.constrains('receptor_rut')
    def _check_receptor_rut(self):
        for rec in self:
            if rec.receptor_rut and not self._validate_rut(rec.receptor_rut):
                raise ValidationError(_('El RUT del receptor no es válido'))

    def _validate_rut(self, rut):
        if not rut:
            return False
        rut = rut.replace('.', '').replace('-', '').upper()
        if len(rut) < 8:
            return False
        numero, dv = rut[:-1], rut[-1]
        if not numero.isdigit():
            return False
        suma, mult = 0, 2
        for d in reversed(numero):
            suma += int(d) * mult
            mult = mult + 1 if mult < 7 else 2
        resto = suma % 11
        dv_calc = '0' if resto == 0 else 'K' if resto == 1 else str(11 - resto)
        return dv == dv_calc