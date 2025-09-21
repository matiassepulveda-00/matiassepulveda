# -*- coding: utf-8 -*-
{
    # CHANGE: nombre legible de la App
    'name': 'Boletas de Honorarios SimpleAPI',  # antes: "integracion_simple_api"

    # CHANGE: versión con formato Odoo 18
    'version': '18.0.1.0.0',  # antes: '0.1'

    # CHANGE: categoría coherente con contabilidad/localización
    'category': 'Accounting/Localization',  # antes: 'Uncategorized'

    # CHANGE: resumen claro
    'summary': 'Integración con SimpleAPI para emisión automática de boletas de honorarios',  # antes: resumen genérico

    # CHANGE: descripción ampliada (puedes ajustar texto/autor/empresa después)
    'description': """
        Módulo para la creación y autodescarga de boletas de honorarios
        mediante integración con SimpleAPI Chile.
        
        Características:
        - Emisión automática de boletas de honorarios
        - Descarga automática de PDF
        - Integración directa con SII Chile
        - Gestión de estados y seguimiento
    """,

    # CHANGE: autor y sitio (puedes poner tus datos reales)
    'author': 'Tu Empresa',  # antes: "My Company"
    'website': 'https://www.tuempresa.com',  # antes: yourcompany.com

    # CHANGE: licencia explícita
    'license': 'LGPL-3',  # antes: no definida

    # CHANGE: dependencias del proyecto del repo
    'depends': ['base', 'account', 'contacts', 'mail', 'web'],  # antes: ['base']

    # CHANGE: declaramos datos EXACTAMENTE como en el repo (los crearemos en el próximo paso)
    'data': [
        'security/ir.model.access.csv',         # nuevo
        'views/boleta_honorarios_views.xml',    # nuevo
        'views/bhe_mail_views.xml', #nuevo
        'views/res_config_settings_views.xml',  # nuevo
        # 'data/ir_cron_data.xml',              # opcional (lo dejamos comentado por ahora)
    ],

    # CHANGE: assets backend (dejamos la clave por compatibilidad; sin archivos por ahora)
    'assets': {
        'web.assets_backend': [
            # 'integracion_simple_api/static/src/js/preview_iframe.js',  # lo activaremos si lo usamos
        ],
    },

    # CHANGE: marcamos como instalable/aplicación
    'installable': True,
    'auto_install': False,
    'application': True,

    # CHANGE: quitamos 'demo' para no arrastrar data de ejemplo innecesaria
    # 'demo': [],
}