# -*- coding: utf-8 -*-

import base64
import StringIO
import os
import logging
from itertools import groupby
from operator import itemgetter

from lxml import etree
from lxml.etree import DocumentInvalid
from jinja2 import Environment, FileSystemLoader

from openerp import fields, models, api

from .utils import convertir_fecha, get_date_value
from odoo.exceptions import (
    ValidationError,
    Warning as UserError
)



tpIdProv = {
    'ruc': '01',
    'cedula': '02',
    'pasaporte': '03',
}

tpIdCliente = {
    'ruc': '04',
    'cedula': '05',
    'pasaporte': '06'
    }
tipoPersona = {
    '6': '01',
    '9': '02',
    '0': '02'
    }


class AccountAts(dict):
    """
    representacion del ATS
    >>> ats.campo = 'valor'
    >>> ats['campo']
    'valor'
    """

    def __getattr__(self, item):
        try:
            return self.__getitem__(item)
        except KeyError:
            raise AttributeError(item)

    def __setattr__(self, item, value):
        if item in self.__dict__:
            dict.__setattr__(self, item, value)
        else:
            self.__setitem__(item, value)


class WizardAts(models.TransientModel):

    _name = 'wizard.ats'
    _description = 'Anexo Transaccional Simplificado'
    __logger = logging.getLogger(_name)

    @api.multi
    def _get_period(self):
        return self.env['account.period'].find()

    @api.multi
    def _get_company(self):
        return self.env.user.company_id.id

    def act_cancel(self):
        return {'type': 'ir.actions.act_window_close'}

    def process_lines(self, lines):
        """
        @temp: {'332': {baseImpAir: 0,}}
        @data_air: [{baseImpAir: 0, ...}]
        """


        # <codRetAir>ret_ir</codRetAir> eso esta mal

        data_air = []
        temp = {}
        for line in lines:
            if line.group_id.code in ['ret_ir', 'no_ret_ir']:
                if not temp.get(line.group_id.code):
                    temp[line.group_id.code] = {
                        'baseImpAir': 0,
                        'valRetAir': 0
                    }
                
                temp[line.group_id.code]['codRetAir'] = line.tax_id.description  # noqa
                temp[line.group_id.code]['baseImpAir'] += line.base
                temp[line.group_id.code]['porcentajeAir'] = int(line.tax_id.percent_report)  # noqa
                temp[line.group_id.code]['valRetAir'] += abs(line.amount)
        for k, v in temp.items():
            data_air.append(v)
        return data_air


    def process_paids(self, inv):
        # raise UserError(inv.amount_pay)
        if inv.amount_pay <= self.pay_limit:
            return False
        data_formaPag = []
        if len(inv.payment_ids) == 0:
            data_formaPag.append({'formaPago':'01'})
        for line in inv.payment_ids:
            data_formaPag.append({'formaPago':line.journal_id.epayment_id.code})
        return data_formaPag

    @api.model
    def _get_ventas(self, mes,anio):
        sql_ventas = "SELECT type, sum(amount_vat+amount_vat_cero+amount_novat) AS base \
                      FROM account_invoice \
                      WHERE type IN ('out_invoice', 'out_refund') \
                      AND state IN ('open','paid') \
                      and to_char(date_invoice, 'MM') = '{0}'\
                      and to_char(date_invoice, 'yyyy') = '{1}'". format(mes, anio)


        sql_ventas += " GROUP BY type"
        self.env.cr.execute(sql_ventas)
        res = self.env.cr.fetchall()
        resultado = sum(map(lambda x: x[0] == 'out_refund' and x[1] * -1 or x[1], res))  # noqa
        return resultado

    def _get_ret_iva(self, invoice):
        """
        Return (valRetBien10, valRetServ20,
        valorRetBienes,
        valorRetServicios, valorRetServ100)
        """
        retBien10 = 0
        retServ20 = 0
        retBien = 0
        retServ50 = 0
        retServ = 0
        retServ100 = 0
        for tax in invoice.tax_line_ids:
            if tax.group_id.code == 'ret_vat_b':
                if tax.percent_report == '10':
                    retBien10 += abs(tax.amount)
                else:
                    retBien += abs(tax.amount)
            if tax.group_id.code == 'ret_vat_srv':
                if tax.percent_report == '100':
                    retServ100 += abs(tax.amount)
                if tax.percent_report == '50':
                    retServ50 += abs(tax.amount)
                elif tax.percent_report == '20':
                    retServ20 += abs(tax.amount)
                else:
                    retServ += abs(tax.amount)


        return retBien10, retServ20, retBien, retServ50, retServ, retServ100

    def get_withholding(self, wh):
        return {
            'estabRetencion1': wh.auth_id.serie_entidad,
            'ptoEmiRetencion1': wh.auth_id.serie_emision,
            'secRetencion1': wh.name[6:15],
            'autRetencion1': wh.auth_id.name,
            'fechaEmiRet1': convertir_fecha(wh.date)
        }

    def get_refund(self, invoice):
        # refund = self.env['account.invoice'].search([
        #     ('invoice_number', '=', invoice.origin),
        #     ('state', 'in', ['open', 'paid']),
        #     ('type', 'in', ['in_invoice', 'liq_purchase']) 
        # ])


        refund  = invoice.refund_invoice_id
        if refund:
            auth = refund.auth_inv_id
            return {
                'docModificado': '01',
                'estabModificado': refund.invoice_number[0:3],
                'ptoEmiModificado': refund.invoice_number[3:6],
                'secModificado': refund.invoice_number[6:15],
                'autModificado': refund.auth_number,
            }
        else:
            auth = refund.auth_inv_id
            return {
                'docModificado': auth.type_id.code,
                'estabModificado': auth.serie_entidad,
                'ptoEmiModificado': auth.serie_emision,
                'secModificado': refund.invoice_number[6:15],
                'autModificado': refund.auth_number
            }

    def get_reembolsos(self, invoice):

        if not invoice.auth_inv_id.type_id.code == '41':
            return False
        res = []
        for r in invoice.refund_invoice_ids:
            res.append({
                'tipoComprobanteReemb': r.doc_id.code,
                'tpIdProvReemb': tpIdProv[r.partner_id.type_identifier],
                'idProvReemb': r.partner_id.identifier,
                'establecimientoReemb': r.auth_id.serie_entidad,
                'puntoEmisionReemb': r.auth_id.serie_emision,
                'secuencialReemb': r.secuencial,
                'fechaEmisionReemb': convertir_fecha(r.date),
                'autorizacionReemb': r.auth_id.name,
                'baseImponibleReemb': '0.00',
                'baseImpGravReemb': '0.00',
                'baseNoGravReemb': '%.2f' % r.amount,
                'baseImpExeReemb': '0.00',
                'montoIceRemb': '0.00',
                'montoIvaRemb': '%.2f' % r.tax
            })
        return res

    def read_compras(self, mes, anio):
        """
        Procesa:
          * facturas de proveedor
          * liquidaciones de compra
        """
        inv_obj = self.env['account.invoice']
        # raise AttributeError("item")
        dmn_purchase = [
            ('state', 'in', ['open', 'paid']),
            # ("to_char(fecha, 'Month')", '=', '11'),

            # ('period_id', '=', period.id),
            ('type', 'in', ['in_invoice', 'liq_purchase', 'in_refund'])  # noqa
        ]
        sql_compras = "SELECT id \
                      FROM account_invoice \
                      WHERE type IN ('in_invoice', 'liq_purchase','in_refund') \
                      AND state IN ('open','paid') \
                      and to_char(date_invoice, 'MM') = '{0}'\
                      and to_char(date_invoice, 'yyyy') = '{1}'". format(mes, anio)
        self.env.cr.execute(sql_compras)
        res = self.env.cr.fetchall()

        resultado = map(lambda x: x[0], res)
        # print "hola"
        # print str(resultado)
        # print "hola"
        # # raise UserError(res)
        # raise UserError(inv_obj.browse(resultado))
       
        compras = []
        for inv in inv_obj.browse(resultado):
            if not inv.partner_id.type_identifier == 'pasaporte':
                detallecompras = {}
                auth = inv.auth_inv_id
                valRetBien10, valRetServ20, valorRetBienes, valRetServ50,valorRetServicios, valRetServ100 = self._get_ret_iva(inv)  # noqa
                t_reeb = 0.0
                if not inv.auth_inv_id.type_id.code == '41':
                    t_reeb = 0.00
                else:
                    if inv.type == 'liq_purchase':
                        t_reeb = 0.0
                    else:
                        t_reeb = inv.amount_untaxed
                detallecompras.update({
                    'codSustento': inv.sustento_id.code,
                    'tpIdProv': tpIdProv[inv.partner_id.type_identifier],
                    'idProv': inv.partner_id.identifier,
                    'tipoComprobante': inv.type == 'liq_purchase' and '03' or auth.type_id.code,  # noqa
                    'parteRel': 'NO',
                    'fechaRegistro': convertir_fecha(inv.date_invoice),
                    'establecimiento': inv.invoice_number[:3],
                    'puntoEmision': inv.invoice_number[3:6],
                    'secuencial': inv.invoice_number[6:15],
                    'fechaEmision': convertir_fecha(inv.date_invoice),
                    'autorizacion': inv.auth_number,
                    'baseNoGraIva': '%.2f' % inv.amount_novat,
                    'baseImponible': '%.2f' % inv.amount_vat_cero,
                    'baseImpGrav': '%.2f' % inv.amount_vat,
                    'baseImpExe': '0.00',
                    'total': inv.amount_pay,
                    'montoIce': '0.00',
                    'montoIva': '%.2f' % inv.amount_tax,
                    'valRetBien10': '%.2f' % valRetBien10,
                    'valRetServ20': '%.2f' % valRetServ20,
                    'valorRetBienes': '%.2f' % valorRetBienes,
                    'valRetServ50': '0.00',
                    'valorRetServicios': '%.2f' % valorRetServicios,
                    'valRetServ100': '%.2f' % valRetServ100,
                    'totbasesImpReemb': '%.2f' % t_reeb,
                    'pagoExterior': {
                        'pagoLocExt': '01',
                        'paisEfecPago': 'NA',
                        'aplicConvDobTrib': 'NA',
                        'pagExtSujRetNorLeg': 'NA'
                    },
                    'formasDePago': self.process_paids(inv),#inv.epayment_id.code,
                    'detalleAir': self.process_lines(inv.tax_line_ids)
                })
                if tpIdProv[inv.partner_id.type_identifier] == '03':
                    detallecompras.update({'tipoProv': tipoPersona[inv.partner_id.tipo_persona]})
                    detallecompras.update({'denoProv': inv.partner_id.name})

                if inv.retention_id:
                    detallecompras.update({'retencion': True})
                    detallecompras.update(self.get_withholding(inv.retention_id))  # noqa
                if inv.type in ['out_refund', 'in_refund']:
                    refund = self.get_refund(inv)
                    if refund:
                        detallecompras.update({'es_nc': True})
                        detallecompras.update(refund)
                detallecompras.update({
                    'reembolsos': self.get_reembolsos(inv)
                })
                compras.append(detallecompras)
        return compras

    def process_paids_venta(self, inv):
        # raise UserError(inv.amount_pay)
        # if inv.amount_pay <= self.pay_limit:
        #     return False
        data_formaPag = []
        # print inv.payment_ids
        if len(inv.payment_ids) == 0:
            # print '01'
            data_formaPag.append('01')
        for line in inv.payment_ids:
            # print line.journal_id.epayment_id.code
            data_formaPag.append(line.journal_id.epayment_id.code)
        # print data_formaPag

        return data_formaPag

    @api.multi
    def read_ventas(self, mes,anio):
        dmn = [
            ('state', 'in', ['open', 'paid']),
            # ('period_id', '=', period.id),
            ('type', '=', 'out_invoice'),
            ('auth_inv_id.is_electronic', '!=', True)
        ]
        ventas = []



        sql_ventas = "SELECT inv.id \
                      FROM account_invoice inv, account_authorisation auth\
                      WHERE inv.auth_inv_id = auth.id \
                      and inv.type IN ('out_invoice') \
                      and auth.is_electronic !=  true \
                      AND inv.state IN ('open','paid') \
                      and to_char(inv.date_invoice, 'MM') = '{0}'\
                      and to_char(inv.date_invoice, 'yyyy') = '{1}'". format(mes, anio)
        self.env.cr.execute(sql_ventas)
        res = self.env.cr.fetchall()

        resultado = map(lambda x: x[0], res)

        for inv in self.env['account.invoice'].browse(resultado):
            detalleventas = {
                'tpIdCliente': tpIdCliente[inv.partner_id.type_identifier],
                # 'tipoCliente': tipoPersona[inv.partner_id.tipo_persona],
                'idCliente': inv.partner_id.identifier,
                'parteRelVtas': 'NO',
                'partner': inv.partner_id,
                'auth': inv.auth_inv_id,
                'tipoComprobante': inv.auth_inv_id.type_id.code,
                'tipoEmision': inv.auth_inv_id.is_electronic and 'E' or 'F',
                'numeroComprobantes': 1,
                'baseNoGraIva': inv.amount_novat,
                'baseImponible': inv.amount_vat_cero,
                'baseImpGrav': inv.amount_vat,
                'montoIva': inv.amount_tax,
                'montoIce': '0.00',
                'valorRetIva': (abs(inv.taxed_ret_vatb) + abs(inv.taxed_ret_vatsrv)),  # noqa
                'valorRetRenta': abs(inv.taxed_ret_ir),
                'formasDePago': self.process_paids_venta(inv)
            }
            ventas.append(detalleventas)


        ventas = sorted(ventas, key=itemgetter('idCliente'))
        ventas_end = []
        for ruc, grupo in groupby(ventas, key=itemgetter('idCliente')):
            # print "Otro Cliente"
            # print ruc
            # i = sorted(grupo, key=itemgetter('tipoComprobante'))
            grupo = sorted(grupo, key=itemgetter('tipoComprobante'))
            for tipoComprobante, grupo2 in groupby(grupo, key=itemgetter('tipoComprobante')):
                # print "Otro tipo"
                # print tipoComprobante
                baseimp = 0
                nograviva = 0
                montoiva = 0
                retiva = 0
                impgrav = 0
                retrenta = 0
                numComp = 0
                partner_temp = False
                auth_temp = False
                formasDePago = []
                for i in grupo2:
                    # print str(i['formasDePago'])
                    nograviva += i['baseNoGraIva']
                    baseimp += i['baseImponible']
                    impgrav += i['baseImpGrav']
                    montoiva += i['montoIva']
                    retiva += i['valorRetIva']
                    retrenta += i['valorRetRenta']
                    numComp += 1
                    formasDePago += i['formasDePago']
                    partner_temp = i['partner']
                    auth_temp = i['auth']
                detalle = {
                    'tpIdCliente': tpIdCliente[partner_temp.type_identifier],
                    'idCliente': ruc,
                    'parteRelVtas': 'NO',
                    'tipoComprobante': auth_temp.type_id.code,
                    'tipoEmision': auth_temp.is_electronic and 'E' or 'F',
                    'numeroComprobantes': numComp,
                    'baseNoGraIva': '%.2f' % nograviva,
                    'baseImponible': '%.2f' % baseimp,
                    'baseImpGrav': '%.2f' % impgrav,
                    'montoIva': '%.2f' % montoiva,
                    'montoIce': '0.00',
                    'valorRetIva': '%.2f' % retiva,
                    'valorRetRenta': '%.2f' % retrenta,
                    'formasDePagoTemp': formasDePago
                }
                if tpIdCliente[inv.partner_id.type_identifier] == '06':
                    detalle.update({'tipoCliente': tipoPersona[inv.partner_id.tipo_persona]})
                    detalle.update({'denoCli': inv.partner_id.name})
                    

                formasDePago = []
                for line in list(set(detalle['formasDePagoTemp'])):
                    formasDePago.append({'formaPago':line})
                detalle.update({'formasDePago':formasDePago})
                ventas_end.append(detalle)
        
        return ventas_end

    @api.multi
    def read_anulados(self, mes,anio):
        dmn = [
            ('state', '=', 'cancel'),
            # ('period_id', '=', period.id),
            ('type', 'in', ['out_invoice', 'liq_purchase'])
        ]



        sql_anulados = "SELECT id \
                      FROM account_invoice \
                      WHERE type IN ('out_invoice', 'liq_purchase') \
                      AND state = 'cancel' \
                      and to_char(date_invoice, 'MM') = '{0}'\
                      and to_char(date_invoice, 'yyyy') = '{1}'". format(mes, anio)
        self.env.cr.execute(sql_anulados)
        res = self.env.cr.fetchall()

        resultado = map(lambda x: x[0], res)
 

        anulados = []
        for inv in self.env['account.invoice'].browse(resultado):
            auth = inv.auth_inv_id
            aut = auth.is_electronic and inv.numero_autorizacion or auth.name
            detalleanulados = {
                'tipoComprobante': auth.type_id.code,
                'establecimiento': auth.serie_entidad,
                'ptoEmision': auth.serie_emision,
                'secuencialInicio': inv.invoice_number[6:9],
                'secuencialFin': inv.invoice_number[6:9],
                'autorizacion': aut
            }
            anulados.append(detalleanulados)

        dmn_ret = [
            ('state', '=', 'cancel'),
            # ('period_id', '=', period.id),
            ('in_type', '=', 'ret_in_invoice')
        ]


        sql_retencion = "SELECT id \
                      FROM account_retention \
                      WHERE type IN ('ret_in_invoice') \
                      AND state = 'cancel' \
                      and to_char(date, 'MM') = '{0}'\
                      and to_char(date, 'yyyy') = '{1}'". format(mes, anio)
        self.env.cr.execute(sql_retencion)
        res = self.env.cr.fetchall()

        resultado = map(lambda x: x[0], res)


        for ret in self.env['account.retention'].browse(resultado):
            auth = ret.auth_id
            aut = auth.is_electronic and inv.numero_autorizacion or auth.name
            detalleanulados = {
                'tipoComprobante': auth.type_id.code,
                'establecimiento': auth.serie_entidad,
                'ptoEmision': auth.serie_emision,
                'secuencialInicio': ret.name[6:9],
                'secuencialFin': ret.name[6:9],
                'autorizacion': aut
            }
            anulados.append(detalleanulados)
        return anulados

    @api.multi
    def render_xml(self, ats):
        tmpl_path = os.path.join(os.path.dirname(__file__), 'templates')
        env = Environment(loader=FileSystemLoader(tmpl_path))
        # raise UserError(str(tmpl_path))

        ats_tmpl = env.get_template('ats.xml')

        return ats_tmpl.render(ats)

    @api.multi
    def validate_document(self, ats, error_log=False):
        file_path = os.path.join(os.path.dirname(__file__), 'XSD/ats.xsd')
        schema_file = open(file_path)
        xmlschema_doc = etree.parse(schema_file)
        xmlschema = etree.XMLSchema(xmlschema_doc)
        root = etree.fromstring(ats)
        ok = True
        if not self.no_validate:
            try:
                xmlschema.assertValid(root)
            except DocumentInvalid:
                ok = False
        return ok, xmlschema

    @api.multi
    def act_export_ats(self):
        ats = AccountAts()
        period = self.period_id

        mes = self.mes_sel
        anio = self.anio_sel

        ruc = self.company_id.partner_id.identifier
        ats.TipoIDInformante = 'R'
        ats.IdInformante = ruc
        ats.razonSocial = self.company_id.name.upper()
        ats.Anio = anio #get_date_value(period.date_start, '%Y')
        ats.Mes = mes #get_date_value(period.date_start, '%m')
        ats.numEstabRuc = self.num_estab_ruc.zfill(3)
        ats.AtstotalVentas = '%.2f' % self._get_ventas(mes,anio)#self._get_ventas(period.id)
        ats.totalVentas = '%.2f' % self._get_ventas(mes,anio)#self._get_ventas(period.id)
        ats.codigoOperativo = 'IVA'
        ats.compras = self.read_compras(mes,anio)
        ats.ventas = self.read_ventas(mes,anio)
        ats.codEstab = self.num_estab_ruc
        ats.ventasEstab = '%.2f' % self._get_ventas(mes,anio)
        ats.ivaComp = '0.00'
        ats.anulados = self.read_anulados(mes,anio)
        ats_rendered = self.render_xml(ats)
        ok, schema = self.validate_document(ats_rendered)
        buf = StringIO.StringIO()
        buf.write(ats_rendered)
        out = base64.encodestring(buf.getvalue())
        buf.close()
        buf_erro = StringIO.StringIO()
        buf_erro.write(schema.error_log)
        out_erro = base64.encodestring(buf_erro.getvalue())
        buf_erro.close()
        name = "%s%s%s.XML" % (
            "AT",
            mes,
            anio
        )
        data2save = {
            'state': ok and 'export' or 'export_error',
            'data': out,
            'fcname': name
        }
        if not ok:
            data2save.update({
                'error_data': out_erro,
                'fcname_errores': 'ERRORES.txt'
            })
        print ats
        self.write(data2save)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'wizard.ats',
            'view_mode': ' form',
            'view_type': ' form',
            'res_id': self.id,
            'views': [(False, 'form')],
            'target': 'new',
        }

    fcname = fields.Char('Nombre de Archivo', size=50, readonly=True)
    fcname_errores = fields.Char('Archivo Errores', size=50, readonly=True)
    period_id = fields.Many2one(
        'account.period',
        'Periodo'
        # default=_get_period
    )
    mes_sel = fields.Selection(
        (
            ('01', '01'),
            ('02', '02'),
            ('03', '03'),
            ('04', '04'),
            ('05', '05'),
            ('06', '06'),
            ('07', '07'),
            ('08', '08'),
            ('09', '09'),
            ('10', '10'),
            ('11', '11'),
            ('12', '12'),
        ),
        string = "Mes",
        default='11'

    )
    anio_sel = fields.Selection(
        (
            ('2010', '2010'),
            ('2011', '2011'),
            ('2012', '2012'),
            ('2013', '2013'),
            ('2014', '2014'),
            ('2015', '2015'),
            ('2016', '2016'),
            ('2017', '2017'),
            ('2018', '2018'),
            ('2019', '2019'),
            ('2020', '2020'),
            ('2021', '2021'),
            ('2022', '2022'),
            ('2023', '2023'),
        ), 
        string = 'Año',
        default = '2017'

    )
    company_id = fields.Many2one(
        'res.company',
        'Compania',
        default=_get_company
    )
    num_estab_ruc = fields.Char(
        'Num. de Establecimientos',
        size=3,
        required=True,
        default='001'
    )
    pay_limit = fields.Float('Limite de Pago', default=1000)
    data = fields.Binary('Archivo XML')
    error_data = fields.Binary('Archivo de Errores')
    no_validate = fields.Boolean('No Validar')
    state = fields.Selection(
        (
            ('choose', 'Elegir'),
            ('export', 'Generado'),
            ('export_error', 'Error')
        ),
        string='Estado',
        default='choose'
    )
