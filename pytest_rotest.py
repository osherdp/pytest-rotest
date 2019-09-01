# -*- coding: utf-8 -*-
import ipdb
import six
import sys
import argparse
from itertools import chain

import pytest
import pkg_resources
from attrdict import AttrDict
from rotest.common import core_log
from rotest.core.result.result import Result
from rotest.core.abstract_test import AbstractTest
from rotest.core.result.result import get_result_handlers
from rotest.core import TestSuite, TestCase, TestFlow, TestBlock
from rotest.management.client.manager import ClientResourceManager
from rotest.cli.client import parse_outputs_option, filter_valid_values
from rotest.core.runner import (DEFAULT_CONFIG_PATH, parse_config_file,
                                update_resource_requests,
                                parse_resource_identifiers)


class OutputHandlersParseAction(argparse.Action):
    """An action class to parse rotest output handlers."""
    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, parse_outputs_option(values))


def pytest_addoption(parser):
    group = parser.getgroup('rotest')

    group.addoption(
        '--config',
        action='store',
        dest='config_path',
        default=DEFAULT_CONFIG_PATH,
        help='Rotest run configuration file path.'
    )
    group.addoption(
        '--outputs',
        action=OutputHandlersParseAction,
        dest='outputs',
        default=None,
        help="Output handlers separated by comma. Options: {}".format(
            ", ".join(get_result_handlers()))
    )


def _pytest_configure(config):
    print('aaaaaaaaa')
    class AlmightySuite(TestSuite):
        components = []

    session.rotest_config = AttrDict(chain(
        six.iteritems(parse_config_file(DEFAULT_CONFIG_PATH)),
        six.iteritems(parse_config_file(config.option.config_path)),
        filter_valid_values({'outputs': config.option.outputs})
        #filter_valid_values(vars(config)),
    ))

    session.rotest_result = Result(stream=sys.stdout,
                                   outputs=session.rotest_config.outputs)
    session.rotest_manager = ClientResourceManager(logger=core_log)


def pytest_runtest_setup(item):
    if issubclass(item.parent._obj, AbstractTest):
        item._is_client_local = False
        if (item._is_client_local and
                item.resource_manager.is_connected()):
            item.resource_manager.disconnect()
        item.resource_manager = item.session.rotest_manager



def pytest_pycollect_makeitem(collector, name, obj):
    if isinstance(obj, type) and \
            issubclass(obj, (TestSuite, TestCase, TestFlow, TestBlock)):
        print(collector, name, obj)


def pytest_collection_modifyitems(session, config, items):
    for item in items[:]:
        if item.parent._obj in (TestSuite, TestCase, TestFlow, TestBlock):
            items.remove(item)

    import ipdb; ipdb.set_trace()
