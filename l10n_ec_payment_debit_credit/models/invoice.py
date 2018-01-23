# -*- coding: utf-8 -*-
# © <2016> <Cristian Salamea>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import (
    api,
    models,
    _,
    fields
)
from odoo.tools.float_utils import float_compare


class AccountPayment(models.Model):

    _inherit = 'account.payment'
    debit = fields.Monetary(related="partner_id.debit")
    credit = fields.Monetary(related="partner_id.credit")