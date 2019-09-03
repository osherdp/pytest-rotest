# -*- coding: utf-8 -*-
import six
import sys
import json
import argparse
from itertools import chain, count

from _pytest.unittest import UnitTestCase, TestCaseFunction

from attrdict import AttrDict
from rotest.common import core_log
from rotest.core.result.result import Result
from rotest.cli.discover import is_test_class
from rotest.core.result.result import get_result_handlers
from rotest.core.models import CaseData, RunData, SuiteData
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
    INDEXER = count()
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
    group.addoption(
        '--ipdbugger',
        action='store_true',
        dest='ipdbugger',
        default=False,
        help="Enter ipdb debug mode upon any test exception, "
             "and enable entering debug mode on Ctrl-Pause "
             "(Windows) or Ctrl-Quit (Linux)."
    )


class RotestTestWrapper(UnitTestCase):
    def collect(self):
        for test_function in super(RotestTestWrapper, self).collect():
            test_wrapper = RotestMethodWrapper(test_function.name, self,
                                               test_function.obj)

            test_wrapper._testcase = self.obj(test_function.name,
                         parent=RotestRunContext.MAIN_TEST,
                         config=RotestRunContext.CONFIG,
                         indexer=RotestRunContext.INDEXER,
                         run_data=RotestRunContext.RUN_DATA,
                         skip_init=RotestRunContext.CONFIG.skip_init,
                         save_state=RotestRunContext.CONFIG.save_state,
                         enable_debug=RotestRunContext.CONFIG.debug,
                         base_work_dir=RotestRunContext.MAIN_TEST.work_dir,
                         resource_manager=RotestRunContext.RESOURCE_MANAGER)

            test_wrapper._testcase.result = RotestRunContext.RESULT

            yield test_wrapper


class RotestMethodWrapper(TestCaseFunction):
    def setup(self):
        self._fix_unittest_skip_decorator()
        self._obj = getattr(self._testcase, self.name)
        if hasattr(self._testcase, "setup_method"):
            self._testcase.setup_method(self._obj)

        if hasattr(self, "_request"):
            self._request._fillfixtures()

    def runtest(self):
        return self._testcase(result=RotestRunContext.RESULT)

    def startTest(self, testcase):
         RotestRunContext.RESULT.startTest(testcase)
         super(RotestMethodWrapper, self).startTest(testcase)

    def addError(self, testcase, rawexcinfo):
        RotestRunContext.RESULT.addError(testcase, rawexcinfo)
        super(RotestMethodWrapper, self).startError(testcase, rawexcinfo)

    def addFailure(self, testcase, rawexcinfo):
        RotestRunContext.RESULT.addFailure(testcase, rawexcinfo)
        super(RotestMethodWrapper, self).addFailure(testcase, rawexcinfo)

    def addSkip(self, testcase, reason):
        RotestRunContext.RESULT.addSkip(testcase, reason)
        super(RotestMethodWrapper, self).addSkip(testcase, reason)

    def addExpectedFailure(self, testcase, rawexcinfo, reason=""):
        RotestRunContext.RESULT.addExpectedFailure(testcase, rawexcinfo)
        super(RotestMethodWrapper, self).addExpectedFailure(testcase,
                                                            rawexcinfo)
        

def pytest_pycollect_makeitem(collector, name, obj):
    if isinstance(obj, type) and issubclass(obj, (TestSuite, TestCase, TestFlow, TestBlock)):
        if is_test_class(obj):
            return RotestTestWrapper(name, collector)

        else:
            return []


def pytest_sessionstart(session):
    config = session.config
    RotestRunContext.CONFIG = AttrDict(chain(
        six.iteritems(parse_config_file(DEFAULT_CONFIG_PATH)),
        six.iteritems(parse_config_file(config.option.config_path)),
        filter_valid_values({'outputs': config.option.outputs,
                             'debug': config.option.ipdbugger})
    ))

    RotestRunContext.RUN_DATA = RunData(
        config=json.dumps(RotestRunContext.CONFIG))
    RotestRunContext.RESOURCE_MANAGER = ClientResourceManager(logger=core_log)

    class AlmightySuite(TestSuite):
        components = [TestCase]

    main_test = AlmightySuite(
        run_data=RotestRunContext.RUN_DATA,
        config=config,
        indexer=RotestRunContext.INDEXER,
        skip_init=RotestRunContext.CONFIG.skip_init,
        save_state=RotestRunContext.CONFIG.save_state,
        enable_debug=RotestRunContext.CONFIG.debug,
        resource_manager=RotestRunContext.RESOURCE_MANAGER)

    RotestRunContext.MAIN_TEST = main_test
    main_test._tests = []
    main_test.name = main_test.get_name()
    main_test.data = SuiteData(name=main_test.name,
                               run_data=RotestRunContext.RUN_DATA)

    RotestRunContext.RUN_DATA.main_test = main_test.data

    RotestRunContext.RESULT = Result(stream=sys.stdout,
                                     outputs=RotestRunContext.CONFIG.outputs,
                                     main_test=main_test)


def pytest_collection_finish(session):
    if RotestRunContext.RESULT:
        RotestRunContext.RESULT.startTestRun()


def pytest_sessionfinish(session, exitstatus):
    if RotestRunContext.RESULT:
        RotestRunContext.RESULT.stopTestRun()

    if RotestRunContext.RESOURCE_MANAGER is not None:
        core_log.debug("Closing the resource manager")
        RotestRunContext.RESOURCE_MANAGER.disconnect()
