# -*- coding: utf-8 -*-
# © 2015 Michael Telahun Makonnen <mmakonnen@gmail.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import time
import logging

from datetime import datetime
from dateutil.relativedelta import relativedelta
from openerp.exceptions import Warning as UserError
            
from odoo import api, models, fields
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT

_l = logging.getLogger(__name__)


class AdvancePayment(models.Model):
    _name = 'hr.advance.payment'
    employee_id = fields.Many2one(
        'hr.employee',
        "Employee",
        required=True,
        readonly=True,
        states={
            'draft': [('readonly', False)]
        },
    )
    amount = fields.Float(
        'Monto de avance',
        digits=(16, 2),
        required=True,
        readonly=True,
        states={
            'draft': [('readonly', False)]
        },
    )
    numero_de_plazos = fields.Integer(
        'Plazos',
        required=True,
        readonly=True,
        states={
            'draft': [('readonly', False)]
        },
    )

    journal_id = fields.Many2one(
        'account.journal', 
        string='Payment Journal', 
        required=True, 
        domain=[('type', 'in', ('bank', 'cash'))],
        readonly=True,
        states={
            'draft': [('readonly', False)]
        })

    payment_ids = fields.One2many(
        'hr.advance.payment.line',
        'advance_payment_id',
        'Pagos',
        readonly=True,
        states={
            'draft': [('readonly', False)]
        },
    )
    payment_method_id = fields.Many2one('account.payment.method', string='Payment Method Type', required=True, oldname="payment_method")
    state = fields.Selection(
        [
            ('draft', 'Borrador'),
            ('confirm', 'Confirmado'),
            ('done', 'Completado')
        ],
        default='draft',
        string='State',
        readonly=True,
    )


    @api.one
    def calcularMontoPlazos(self):
        todayDate = datetime.now()
        month = todayDate.month
        year = todayDate.year
        day = 1
        self.payment_ids = None
        for line in range(self.numero_de_plazos):
            
            self.payment_ids |= self.env['hr.advance.payment.line'].create({'date':str(day)+'/'+str(month)+'/'+str(year), 'amount':(self.amount/self.numero_de_plazos)})
            
            if month== 12:
                month = 0
                year+=1
            month+=1

    @api.one
    def confirmar(self):

        if  self.amount > self.employee_id.contract_id.anticipo_sueldo:
            raise UserError('El anticipo permitido para este empleado es '+str(self.employee_id.contract_id.anticipo_sueldo))
        self.write({'state':'confirm'})
    @api.one
    def generarOrdenDePago(self):
        # try:
        self.env['account.payment'].create({
            'payment_type': 'outbound', 
            'partner_type': 'supplier',
            'partner_id':self.employee_id.address_home_id.id,
            'amount':self.amount,
            'journal_id':self.journal_id.id,
            'payment_method_id':self.payment_method_id.id
            })
        self.write({'state':'done'})
        # except:
            # raise UserError('Algo ha ocurrido mal')

        

class PaymentLine(models.Model):
    _name = 'hr.advance.payment.line'
    _order = 'date ASC'
    date = fields.Date('Fecha que aplica', required=True)
    advance_payment_id = fields.Many2one('hr.advance.payment')
    amount = fields.Float(
        'Valor',
        digits=(16, 2)
    )
