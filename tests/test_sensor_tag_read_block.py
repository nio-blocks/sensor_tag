from time import sleep
from collections import defaultdict
from ..sensor_tag_read_block import SensorTagRead, KeypressDelegate
from unittest.mock import MagicMock, patch
from nio.util.support.block_test_case import NIOBlockTestCase
from nio.common.signal.base import Signal


class SignalA(Signal):

    def __init__(self, a):
        super().__init__()
        self.a = a


@patch(SensorTagRead.__module__ + '.SensorTag')
class TestSensorTagRead(NIOBlockTestCase):

    def signals_notified(self, signals, output_id):
        self.signals[output_id].extend(signals)

    def setUp(self):
        super().setUp()
        self.signals = defaultdict(list)

    def test_template(self, mock_tag):
        """ Use this test as a templage for creating new ones """
        # wait for a notification but never actually handle one
        mock_tag.return_value.waitForNotifications = lambda x: sleep(10)
        blk = SensorTagRead()
        self.configure_block(blk, {
            'device_info': [
                {
                    'address': '12:34:56:78:12:34'
                }
            ],
            'log_level': 'DEBUG'
        })
        signals = [Signal()]
        blk.start()
        # wait for tag to connect and sensors to enable
        sleep(0.1)
        # process signals and assert here
        blk.stop()

    def test_status_signals(self, mock_tag):
        """ Use this test as a templage for creating new ones """
        # wait for a notification but never actually handle one
        mock_tag.return_value.waitForNotifications = lambda x: sleep(10)
        blk = SensorTagRead()
        addy = '12:34:56:78:12:34'
        self.configure_block(blk, {
            'device_info': [
                {
                    'address': addy,
                    'meta': {
                        'sensors': {'keypress': True,
                                    'IRtemperature': False}
                    }
                }
            ],
            'log_level': 'DEBUG'
        })
        signals = [Signal()]
        blk.start()
        # wait for tag to connect and sensors to enable
        sleep(0.1)
        # Connected status is emitted on successful start.
        self.assertEqual(3, len(self.signals['status']))
        self.assertEqual('SensorTag', self.signals['status'][0].name)
        self.assertEqual('Connecting', self.signals['status'][0].status)
        self.assertEqual('Enabling', self.signals['status'][1].status)
        self.assertEqual('Connected', self.signals['status'][2].status)
        self.assertEqual('12:34:56:78:12:34',
                         self.signals['status'][0].address)
        # Connected status is emitted on successful start.
        blk._reconnect_thread(addy, read_on_connect=False)
        sleep(0.1)
        self.assertEqual(7, len(self.signals['status']))
        self.assertEqual('Disconnected', self.signals['status'][3].status)
        self.assertEqual('Connecting', self.signals['status'][4].status)
        self.assertEqual('Enabling', self.signals['status'][5].status)
        self.assertEqual('Connected', self.signals['status'][6].status)
        blk.stop()
        # Should stop emit a disconnect signal? What if we aad a feature in
        # the future where block can stop without stopping the service?
        self.assertEqual(7, len(self.signals['status']))
        self.assertEqual(0, len(self.signals['default']))

    def test_keypress_delegate(self, mock_tag):
        # wait for a notification but never actually handle one
        mock_tag.return_value.waitForNotifications = lambda x: sleep(10)
        blk = SensorTagRead()
        self.configure_block(blk, {
            'device_info': [
                {
                    'address': '12:34:56:78:12:34',
                    'meta': {
                        'sensors': {'keypress': True,
                                    'IRtemperature': False}
                    }
                }
            ],
            'log_level': 'DEBUG'
        })
        signals = [Signal()]
        blk.start()
        # wait for tag to connect and sensors to enable
        sleep(0.1)
        delegate = KeypressDelegate(blk._logger, blk.notify_signals)
        delegate.onButtonDown(0x02)
        self.assertEqual(1, len(self.signals['keypress']))
        self.assertEqual('Left', self.signals['keypress'][0].button)
        self.assertEqual('Down', self.signals['keypress'][0].direction)
        delegate.onButtonUp(0x01)
        self.assertEqual(2, len(self.signals['keypress']))
        self.assertEqual('Right', self.signals['keypress'][1].button)
        self.assertEqual('Up', self.signals['keypress'][1].direction)
        delegate.onButtonUp(0x02|0x01)
        self.assertEqual(3, len(self.signals['keypress']))
        self.assertEqual('Both', self.signals['keypress'][2].button)
        self.assertEqual('Up', self.signals['keypress'][2].direction)
        # Make sure no signals notified from default output
        self.assertEqual(0, len(self.signals['default']))
