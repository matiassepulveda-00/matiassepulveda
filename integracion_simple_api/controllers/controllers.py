# -*- coding: utf-8 -*-
# from odoo import http


# class IntegracionSimpleApi(http.Controller):
#     @http.route('/integracion_simple_api/integracion_simple_api', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/integracion_simple_api/integracion_simple_api/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('integracion_simple_api.listing', {
#             'root': '/integracion_simple_api/integracion_simple_api',
#             'objects': http.request.env['integracion_simple_api.integracion_simple_api'].search([]),
#         })

#     @http.route('/integracion_simple_api/integracion_simple_api/objects/<model("integracion_simple_api.integracion_simple_api"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('integracion_simple_api.object', {
#             'object': obj
#         })

