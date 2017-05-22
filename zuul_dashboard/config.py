server = {
    'port': '8080',
    'host': '0.0.0.0'
}

app = {
    'root': 'zuul_dashboard.controllers.RootController',
    'modules': ['zuul_dashboard'],
    'debug': True,
}

logging = {
    'root': {'level': 'INFO'},
}

zuul = {
    # Set this to sql reporter database
    'dburi': 'sqlite:///data/zuul.sqlite',
}
