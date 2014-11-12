#! /usr/bin/env python
#
# smadata2.db - Database for logging data from SMA inverters
# Copyright (C) 2014 David Gibson <david@gibson.dropbear.id.au>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

from __future__ import print_function

import sys
import time
import sqlite3
import datetime
import calendar


class Error(Exception):
    pass


class SMADatabase(object):
    def __init__(self, *args):
        self.conn = self.connect(*args)

        magic, version = self.get_magic()
        if (magic != self.DB_MAGIC) or (version != self.DB_VERSION):
            raise Error("Incorrect database version (0x%x, %d)"
                        % (magic, version))

    def connect(self):
        raise NotImplementedError

    def get_magic(self):
        raise NotImplementedError


class SMADatabaseSQLiteV0(SMADatabase):
    DB_MAGIC = 0x71534d41
    DB_VERSION = 0

    def connect(self, filename):
        return sqlite3.connect(filename)

    def get_magic(self):
        c = self.conn.cursor()
        c.execute("SELECT magic, version FROM schema;")
        r = c.fetchone()
        magic, version = r[0], r[1]
        if c.fetchone() is not None:
            if c.fetchone() is not None:
                raise Error("Bad version table")
        return magic, version

    def get_last_entry(self, serial):
        c = self.conn.cursor()
        c.execute("SELECT timestamp,total_yield "
                  "FROM generation "
                  "WHERE inverter_serial = ? "
                  "ORDER BY timestamp DESC LIMIT 1", (serial,))
        r = c.fetchone()
        return r

    # return midnights for each day in the database
    # @param serial the inverter seial number to retrieve midnights for
    # @return all midnights in database as datetime objects
    def midnights(self, serial):
        c = self.conn.cursor()
        c.execute("SELECT timestamp "
                  "FROM generation "
                  "WHERE inverter_serial = ? "
                  "AND timestamp % 86400 = 0 "
                  "ORDER BY timestamp ASC", (serial,))
        r = c.fetchall()
        r = map(lambda x: datetime.datetime.utcfromtimestamp(x[0]), r)
        return r

    # retrieve all entries for a day from the database
    # @note this seems to get timezone stuff right :-) "a day" is a "local" day
    # @param date a datetime object for midnight of the day you want
    def get_entries_for_day(self, serial, start_datetime):
        c = self.conn.cursor()
        before_datetime = start_datetime + datetime.timedelta(days=1)
        start_unixtime = time.mktime(start_datetime.timetuple())
        before_unixtime = time.mktime(before_datetime.timetuple())
        c.execute("SELECT timestamp,total_yield "
                  "FROM generation "
                  "WHERE inverter_serial = ? "
                  "AND timestamp >= ? and timestamp < ?"
                  "ORDER BY timestamp ASC", (serial, start_unixtime,
                                             before_unixtime))
        r = c.fetchall()
        return r

    # return last data for a particular day
    def get_last_entry_for_day(self, serial, date):
        c = self.conn.cursor()
        entries = self.get_entries_for_day(serial, date)
        if len(entries) == 0:
            return None
        return entries[len(entries)-1]

    def get_entry(self, serial, timestamp):
        c = self.conn.cursor()
        c.execute("SELECT timestamp,total_yield "
                  "FROM generation "
                  "WHERE inverter_serial = ? "
                  "AND timestamp = ? "
                  "ORDER BY timestamp DESC LIMIT ?", (serial, timestamp, 1))
        r = c.fetchall()
        if len(r) == 0:
            return None
        return r[0]

    def get_last_entries(self, serial, count):
        c = self.conn.cursor()
        c.execute("SELECT timestamp,total_yield "
                  "FROM generation "
                  "WHERE inverter_serial = ? "
                  "ORDER BY timestamp DESC LIMIT ?", (serial, str(count)))
        r = c.fetchall()
        return r

    def get_entries_younger_than(self, serial, entry):
        timestamp = entry[0]
        c = self.conn.cursor()
        c.execute("SELECT timestamp,total_yield "
                  "FROM generation "
                  "WHERE inverter_serial = ? AND "
                  " timestamp > ? "
                  "ORDER BY timestamp ASC", (serial, str(timestamp)))
        r = c.fetchall()
        return r

    def get_last_historic(self, serial):
        c = self.conn.cursor()
        c.execute("SELECT max(timestamp) FROM generation"
                  " WHERE inverter_serial = ?", (serial,))
        r = c.fetchone()
        return r[0]

    def pvoutput_get_hwm(self, serial):
        c = self.conn.cursor()
        c.execute("SELECT hwm "
                  "FROM pvoutput "
                  "WHERE inverter_serial = ?", (serial,))
        r = c.fetchone()
        if r is None:
            return None
        hwm_timestamp = r[0]
        if r[0] is None:
            return None
        return self.get_entry(serial, hwm_timestamp)

    def pvoutput_maybe_init(self, serial):
        c = self.conn.cursor()
        c.execute("SELECT * FROM pvoutput"
                  " WHERE inverter_serial = ?",
                  (serial,))
        r = c.fetchone()
        if r is None:
            c = self.conn.cursor()
            c.execute("INSERT INTO pvoutput(inverter_serial) "
                      "VALUES ( ? )",
                      (serial,))
            self.commit()

    def pvoutput_init_hwm(self, serial, value):
        c = self.conn.cursor()
        self.pvoutput_maybe_init(serial)
        c.execute("update pvoutput "
                  "SET hwm = ?"
                  "WHERE inverter_serial = ?", (value, serial))
        self.commit()

    def pvoutput_set_hwm(self, serial, new_hwm):
        c = self.conn.cursor()
        c.execute("UPDATE pvoutput "
                  "SET hwm = ?"
                  "WHERE inverter_serial = ?", (new_hwm, serial))
        self.commit()

    def get_one_historic(self, serial, timestamp):
        c = self.conn.cursor()
        c.execute("SELECT total_yield FROM generation"
                  " WHERE inverter_serial = ?"
                  " AND timestamp = ?", (serial, timestamp))
        r = c.fetchone()
        if r is not None:
            return r[0]

    def add_historic(self, serial, timestamp, total_yield):
        c = self.conn.cursor()
        c.execute("INSERT INTO generation"
                  + " (inverter_serial, timestamp, total_yield)"
                  + " VALUES (?, ?, ?);",
                  (serial, timestamp, total_yield))

    def commit(self):
        self.conn.commit()


if __name__ == '__main__':
    db = SMADatabaseSQLiteV0(sys.argv[1])