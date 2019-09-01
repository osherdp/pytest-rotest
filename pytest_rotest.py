# -*- coding: utf-8 -*-
import six
import sys
import json
import argparse
from itertools import chain

from attrdict import AttrDict
from rotest.common import core_log
from rotest.core.result.result import Result
from rotest.cli.discover import is_test_class
from rotest.core.models.run_data import RunData
from rotest.core.abstract_test import AbstractTest
from rotest.core.result.result import get_result_handlers
from rotest.core import TestSuite, TestCase, TestFlow, TestBlock
from rotest.management.client.manager import ClientResourceManager
from rotest.cli.client import parse_outputs_option, filter_valid_values
from rotest.core.runner import (DEFAULT_CONFIG_PATH, parse_config_file,
                                update_resource_requests,
                                parse_resource_identifiers)


class RotestRunContext(object):
    CONFIG = None
    RESULT = None
    RUN_DATA = None
    MAIN_TEST = None
    RESOURCE_MANAGER = None
    COLLECTED_CLASSES = []


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


def pytest_runtest_setup(item):
    RotestRunContext.RESULT.startTest(item)


def pytest_runtest_call(item):
    RotestRunContext.RESULT.setupFinished(item)


def pytest_runtest_teardown(item):
    RotestRunContext.RESULT.startTeardown(item)


def pytest_runtest_setup(item):
    if issubclass(item.parent.obj, AbstractTest):
        item.result = RotestRunContext.RESULT
        item._is_client_local = False
        item.resource_manager = item.session.rotest_manager


def pytest_collection_modifyitems(session, config, items):
    rotest_items = []
    for item in items[:]:
        if issubclass(item.parent.obj, (TestSuite, TestCase, TestFlow, TestBlock)):
            if is_test_class(item.parent.obj):
                import ipdb; ipdb.set_trace()
                rotest_items.append(item)

            else:
                items.remove(item)

    if rotest_items:
        RotestRunContext.CONFIG = AttrDict(chain(
            six.iteritems(parse_config_file(DEFAULT_CONFIG_PATH)),
            six.iteritems(parse_config_file(config.option.config_path)),
            filter_valid_values({'outputs': config.option.outputs})
            # filter_valid_values(vars(config)),
        ))

        RotestRunContext.RUN_DATA = RunData(
            config=json.dumps(RotestRunContext.CONFIG))
        RotestRunContext.RESOURCE_MANAGER = ClientResourceManager(logger=core_log)

        config.__dict__.update(RotestRunContext.CONFIG)

        class AlmightySuite(TestSuite):
            components = [TestCase]

        RotestRunContext.MAIN_TEST = AlmightySuite(
            run_data=RotestRunContext.RUN_DATA,
            config=config,
            skip_init=RotestRunContext.CONFIG.skip_init,
            save_state=RotestRunContext.CONFIG.save_state,
            enable_debug=RotestRunContext.CONFIG.debug,
            resource_manager=RotestRunContext.RESOURCE_MANAGER)

        RotestRunContext.MAIN_TEST._tests = rotest_items

        RotestRunContext.RUN_DATA.main_test = RotestRunContext.MAIN_TEST.data

        RotestRunContext.RESULT = Result(stream=sys.stdout,
                                         outputs=RotestRunContext.CONFIG.outputs,
                                         main_test=RotestRunContext.MAIN_TEST)

    import ipdb; ipdb.set_trace()
    RotestRunContext.RESULT.startTestRun()

def pytest_sessionfinish(session, exitstatus):
    """Finalize the test runner.

    * Removes duplicated test DB entries.
    """
    RotestRunContext.RESULT.stopTestRun()
    if RotestRunContext.RESOURCE_MANAGER is not None:
        core_log.debug("Closing the resource manager")
        RotestRunContext.RESOURCE_MANAGER.disconnect()
