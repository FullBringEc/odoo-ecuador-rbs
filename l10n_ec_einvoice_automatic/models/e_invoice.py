# from openerp import models, fields, api
from io import BytesIO
import base64
from odoo import api, fields, models, _
import cStringIO
import logging
from odoo.exceptions import UserError
_logger = logging.getLogger(__name__)

class pos_oder_heredado(models.Model):
    _inherit = "pos.order"

    @api.model
    def cron_verificar_einvoice(self):
        # today = fields.Date.today()
        pos_order_ids = self.with_context(cron=True).search([
            ('state', '=', 'paid')
        ])
        for line in pos_order_ids:
            if line.amount_total >= 0:
                line.action_pos_order_invoice()
            if line.amount_total < 0:
                line.action_pos_order_invoice_refund()

        # _logger = logging.getLogger("pedidos normales"+str(pos_order_ids))

        # for pos_order_ids_line in pos_order_ids:

        #     pos_order_ids_line.invoice_id.action_generate_einvoice()

        # pos_order_refund_ids = self.with_context(cron=True).search([
        #     ('state', '=', 'paid'), ('amount_total', '<', 0)
        # ])
        # pos_order_refund = []
        # for line in pos_order_refund_ids:
        #     if line.amount_total >= 0:
        #         pos_order_refund |= line
        # _logger = logging.getLogger("pedidos refund" + str(pos_order_refund_ids))
        # pos_order_refund.action_pos_order_invoice_refund()

        # for pos_order_refund_ids_line in pos_order_refund_ids:

        #     pos_order_refund_ids_line.invoice_id.action_generate_einvoice()

    @api.multi
    def action_pos_order_invoice_refund(self):
        Invoice = self.env['account.invoice']

        for order in self:
            # Force company for all SUPERUSER_ID action
            local_context = dict(self.env.context, force_company=order.company_id.id, company_id=order.company_id.id)
            if order.invoice_id:
                Invoice += order.invoice_id
                continue
            # _logger.warning("In class %s, field %r overriding an existing value", self, str(order.partner_id))
            if not order.partner_id:
                raise UserError(_('Please provide a partner for the sale.'))

            invoice = Invoice.new(order._prepare_refund())
            invoice._onchange_partner_id()
            invoice.fiscal_position_id = order.fiscal_position_id
            # _logger.warning("In class %s, field %r overriding an existing value", self, str(order.fiscal_position_id))
            inv = invoice._convert_to_write({name: invoice[name] for name in invoice._cache})

            # _logger.warning("In class %s, field %r overriding an existing value", self, str(inv))
            new_invoice = Invoice.with_context(local_context).sudo().create(inv)
            new_invoice._onchange_partner_id()
            new_invoice._onchange_journal_id()
            invoice.fiscal_position_id = order.fiscal_position_id
            # raise UserError(_(str(inv)+'------------------------'+str(new_invoice.read())))
            message = _("This invoice has been created from the point of sale session: <a href=# data-oe-model=pos.order data-oe-id=%d>%s</a>") % (order.id, order.name)
            new_invoice.message_post(body=message)
            order.write({'invoice_id': new_invoice.id, 'state': 'invoiced'})
            Invoice += new_invoice

            for line in order.lines:
                self.with_context(local_context)._action_create_invoice_line_refund(line, new_invoice.id)

            new_invoice.with_context(local_context).sudo().compute_taxes()
            order.sudo().write({'state': 'invoiced'})
            # this workflow signal didn't exist on account.invoice -> should it have been 'invoice_open' ? (and now method .action_invoice_open())
            # shouldn't the created invoice be marked as paid, seing the customer paid in the POS?
            # new_invoice.sudo().signal_workflow('validate')
            new_invoice.action_invoice_open()

        if not Invoice:
            return {}


        return {
            'name': _('Customer Invoice'),
            'view_type': 'form',
            'view_mode': 'form',
            'view_id': self.env.ref('account.invoice_form').id,
            'res_model': 'account.invoice',
            'context': "{'type':'out_refund'}",
            'type': 'ir.actions.act_window',
            'nodestroy': True,
            'target': 'current',
            'res_id': Invoice and Invoice.ids[0] or False,
        }

    def _prepare_refund(self):
        """
        Prepare the dict of values to create the new invoice for a pos order.
        """
        return {
            'name': self.name,
            'origin': self.name,
            'account_id': self.partner_id.property_account_receivable_id.id,
            'journal_id': self.session_id.config_id.invoice_journal_id.id,
            'company_id': self.company_id.id,
            'type': 'out_refund',
            'reference': self.name,
            'partner_id': self.partner_id.id,
            'comment': self.note or '',
            # considering partner's sale pricelist's currency
            'currency_id': self.pricelist_id.currency_id.id,
            'user_id': self.env.uid,
        }

    def _action_create_invoice_line_refund(self, line=False, invoice_id=False):
            InvoiceLine = self.env['account.invoice.line']
            inv_name = line.product_id.name_get()[0][1]
            inv_line = {
                'invoice_id': invoice_id,
                'product_id': line.product_id.id,
                'quantity': -line.qty,
                'account_analytic_id': self._prepare_analytic_account(line),
                'name': inv_name,
            }
            # Oldlin trick
            invoice_line = InvoiceLine.sudo().new(inv_line)
            invoice_line._onchange_product_id()
            invoice_line.invoice_line_tax_ids = invoice_line.invoice_line_tax_ids.filtered(lambda t: t.company_id.id == line.order_id.company_id.id).ids
            fiscal_position_id = line.order_id.fiscal_position_id
            if fiscal_position_id:
                invoice_line.invoice_line_tax_ids = fiscal_position_id.map_tax(invoice_line.invoice_line_tax_ids, line.product_id, line.order_id.partner_id)
            invoice_line.invoice_line_tax_ids = invoice_line.invoice_line_tax_ids.ids
            # We convert a new id object back to a dictionary to write to
            # bridge between old and new api
            inv_line = invoice_line._convert_to_write({name: invoice_line[name] for name in invoice_line._cache})
            inv_line.update(price_unit=line.price_unit, discount=line.discount)
            return InvoiceLine.sudo().create(inv_line)
