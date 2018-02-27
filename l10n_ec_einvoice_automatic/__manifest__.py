# -*- coding: utf-8 -*-


{
    "name": "Einvoice Automatico",
    "version": "1.0",
    "author": "RubikSoft",
    'website': 'http://www.facebook.com/RubikSoft15.com',
    "description": """Modulo revisa las ordenes en el punto de venta y las factura""",

    "depends": ['point_of_sale', 'l10n_ec_einvoice'],
    "data": [

        'einvoice_cron/einvoice_cron.xml',

    ],
    'qweb': [],
    "demo": [],
    "active": False,
    "installable": True,
    "certificate": "",
    'application': True,
}
