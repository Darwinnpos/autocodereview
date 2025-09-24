#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import logging
from app import create_app

# Mn��
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def main():
    # ��Mn��
    config_name = os.environ.get('FLASK_ENV', 'development')

    # �Flask�(
    app = create_app(config_name)

    # ���L�p
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 5000))
    debug = config_name == 'development'

    print(f"Starting AutoCodeReview Server...")
    print(f"Environment: {config_name}")
    print(f"Host: {host}")
    print(f"Port: {port}")
    print(f"Debug: {debug}")

    # /��(
    app.run(
        host=host,
        port=port,
        debug=debug
    )

if __name__ == '__main__':
    main()