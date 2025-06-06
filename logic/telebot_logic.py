# -*- coding: utf-8 -*-

"""
A module for sending messages via a Telegram bot.

Qudi is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Qudi is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Qudi. If not, see <http://www.gnu.org/licenses/>.

Copyright (c) the Qudi Developers. See the COPYRIGHT.txt file at the
top-level directory of this distribution and at <https://github.com/Ulm-IQO/qudi/>
"""

import numpy as np
from collections import OrderedDict
import datetime
from decimal import Decimal

from core.connector import Connector
from core.statusvariable import StatusVar
from core.configoption import ConfigOption
from core.util.mutex import Mutex
from logic.generic_logic import GenericLogic
from qtpy import QtCore
from telebot_router import TeleBot


class TeleBotLogic(GenericLogic):
    """ Logic module to monitor and control a PID process

    Example config:

    telebotlogic:
        module.Class: 'telebot_logic.TeleBotLogic'
        token: 'xxxxxxxx:enterYourBotKeyHereToTest'
        chat_ids: [xxxxxxxx, xxxxxxxx]
        check_period: 10

    """

    _token = ConfigOption('token', missing='error')
    _chat_ids = ConfigOption('chat_ids', missing='error')
    _check_period = ConfigOption('check_period', 10, missing='warn')

    sigStatusRequest = QtCore.Signal(object)
    sigScanRequest = QtCore.Signal(object)

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)

    def on_activate(self):
        """ Initialisation performed during activation of the module.
        """
        self.bot= TeleBot('Bot')
        self.bot.config['api_key'] = self._token

        self.ud = self.bot.get_updates(timeout=1)
        if not self.ud['result']:
            self.update_id = 0
        else:
            self.update_id = self.ud['result'][-1]['update_id']+1

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.check_for_commands)
        self.timer.start(self._check_period* 1000)

    def on_deactivate(self):
        """ Perform required deactivation. """
        self.timer.stop()

    def send_message(self, message, chat_ids = None):
        if chat_ids == None:
            chat_ids = self._chat_ids
        for id in chat_ids:
            self.bot.send_message(id, message)

    def check_for_commands(self):
        try:
            ud = self.bot.get_updates(timeout=1, offset = self.update_id)
            if ud['result']:
                update = ud['result']
                self.update_id = ud['result'][-1]['update_id']+1
                for message in update:
                    chat_id = message['message']['from']['id']
                    text = message['message']['text']
                    if 'Help' in text:
                        self.help_request(chat_id)
                    elif 'Status' in text:
                        self.sigStatusRequest.emit(chat_id)
                    elif 'Scan' in text:
                        self.sigScanRequest.emit(chat_id)
        except:
            pass

    def help_request(self, chat_id):
        msg = f'Following requests are supported: \
                \nStatus: Status info of cryostat \
                \nScan: Status of current QAFM scan'
        self.send_message(msg, [chat_id])


