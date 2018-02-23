# -*- coding: utf-8 -*-
# © <2016> <Cristian Salamea>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    'name': 'Reporte Anexo transaxional',
    'version': '10.0.0.0.0',
    'author': 'Adrian Morales',
    'category': 'Localization',
    'complexity': 'normal',
    'license': 'AGPL-3',
    'data': [
        'wizard/withholding_wizard.xml',
        'views/account_journal.xml',
        'data/account.epayment.csv',
        # 'security/ir.model.access.csv'
    ],
    'depends': [
        'l10n_ec_withholding',
        # 'l10n_ec_einvoice',
        'account'
    ]
}
