# -*- coding: utf-8 -*-
#    Copyright (C) 2016 Adrian Morales <gemgaamg@gmail.com>
{
    'name': 'Advance Payment',
    'version': '10.0.0.1.0',
    'category': 'Generic Modules/Human Resources',
    'author': "Adrian Morales",
    # 'website': 'http://miketelahun.wordpress.com',
    'depends': [
        'hr_contract',
        'hr_holidays',
        'l10n_ec_hr_employee',
        'l10n_ec_hr_contract'
    ],
    "external_dependencies": {
        # 'python': ['dateutil'],
    },
    'data': [
        # 'security/ir.model.access.csv',
        # 'data/hr_data.xml',
        # 'data/hr.contract.commision.csv',
        # 'data/hr.contract.branch.csv',
        # 'data/hr.contract.code.csv',
        # 'data/hr_contract_cron.xml',
        # 'data/hr_contract_data.xml',
        # 'view/hr_contract_view.xml',
        'view/hr_advance_payment.xml',
        # 'view/res_config_view.xml'
    ]
}
