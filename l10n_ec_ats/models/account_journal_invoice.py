# -*- coding: utf-8 -*-

import base64
import StringIO
from datetime import datetime

from openerp import api, fields, models
from openerp.exceptions import Warning as UserError
from openerp.tools import DEFAULT_SERVER_DATETIME_FORMAT


class AccountEpayment(models.Model):
    _name = 'account.epayment'

    code = fields.Char('Código')
    name = fields.Char('Forma de Pago')
    
class AccountJournal(models.Model):
	_inherit = 'account.journal'

	epayment_id = fields.Many2one('account.epayment', 'Forma de Pago')

class AccountInvoice(models.Model):
	_inherit = 'account.invoice'
	refund_invoice_ids = fields.One2many('account.invoice','refund_invoice_id',string="Facturas reembolsadas")
	# epayment_id = fields.Many2one('account.epayment', 'Forma de Pago')