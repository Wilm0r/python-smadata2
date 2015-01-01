#! /usr/bin/env python

import os
import datetime
import time

from nose.tools import *
from nose.plugins.attrib import attr

import smadata2.config
import smadata2.pvoutputorg


def test_parse_date():
    assert_equals(smadata2.pvoutputorg.parse_date("20130813"),
                  datetime.date(2013, 8, 13))


def test_parse_time():
    assert_equals(smadata2.pvoutputorg.parse_time("14:37"),
                  datetime.time(14, 37, 0))


def test_parse_datetime():
    assert_equals(smadata2.pvoutputorg.parse_datetime("20130813", "14:37"),
                  datetime.datetime(2013, 8, 13, 14, 37, 0))


def test_format_date():
    d = datetime.date(2013, 8, 13)
    assert_equals(smadata2.pvoutputorg.format_date(d), "20130813")


def test_format_time():
    t = datetime.time(14, 37)
    assert_equals(smadata2.pvoutputorg.format_time(t), "14:37")


def test_format_datetime():
    dt = datetime.datetime(2013, 8, 13, 14, 37, 0)
    assert_equals(smadata2.pvoutputorg.format_datetime(dt),
                  ("20130813", "14:37"))


def requestkey(script, args):
    return (script, frozenset(args.items()))


class MockAPI(smadata2.pvoutputorg.API):
    responsetable = {
        requestkey("/service/r2/getsystem.jsp", {"donations": 1}):
            "Mock System,1234,0000,39,250,Mock Panel Model,2,5000,\
Mock Inverter Model,NE,1.0,No,,0.000000,0.000000,5;;1"
    }

    def __init__(self):
        super(MockAPI, self).__init__("http://pvoutput.example.com",
                                      "MOCKAPIKEY", "MOCKSID")

    def _request(self, script, args):
        return self.responsetable[requestkey(script, args)]


class TestMockAPI(object):
    def __init__(self):
        self.api = MockAPI()

    def test_getsystem(self):
        assert_equals(self.api.name, "Mock System")
        assert_equals(self.api.system_size, 1234)
        assert_equals(self.api.donation_mode, True)


@attr("pvoutput.org")
class TestRealAPI(object):
    CONFIGFILE = "smadata2-test-pvoutput.json"

    def __init__(self):
        if not os.path.exists(self.CONFIGFILE):
            raise AssertionError("This test needs a special configuration")

        self.config = smadata2.config.SMAData2Config("smadata2-test-pvoutput.json")
        self.system = self.config.systems()[0]
        assert_equals(self.system.name, "test")

        self.date = datetime.date.today() - datetime.timedelta(days=1)

    def delay(self):
        time.sleep(5)

    def setUp(self):
        self.api = self.config.pvoutput_connect(self.system)

        # Make sure we have a blank slate
        self.api.deletestatus(self.date)
        self.delay()

    def tearDown(self):
        self.api.deletestatus(self.date)
        self.delay()
        
    def test_trivial(self):
        assert isinstance(self.api, smadata2.pvoutputorg.API)

    def test_blank(self):
        results = self.api.getstatus(self.date)
        assert results is None

    # The single addstatus interface doesn't seem to work as I expect
    def test_addsingle(self):
        dt0 = datetime.datetime.combine(self.date, datetime.time(12, 0, 0))
        dt1 = datetime.datetime.combine(self.date, datetime.time(12, 5, 0))

        self.api.addstatus(dt0, 1000)
        self.delay()
        self.api.addstatus(dt1, 1007)
        self.delay()

        results = self.api.getstatus(self.date)
        assert_equal(results, [(dt0, 0), (dt1, 7)])

    def test_addbatch(self):
        dt0 = datetime.datetime.combine(self.date, datetime.time(10, 0, 0))
        batch = []
        for i in range(25):
            dt = dt0 + datetime.timedelta(minutes=5*i)
            batch.append((dt, 1000 + i))

        self.api.addbatchstatus(batch)
        self.delay()

        results = self.api.getstatus(self.date)
        assert len(results) == 25
        for i in range(25):
            assert_equals(results[i][0], batch[i][0])
            assert_equals(results[i][1], i)


